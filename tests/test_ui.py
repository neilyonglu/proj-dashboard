import os
import shutil
import unittest
from datetime import date, timedelta
from tempfile import TemporaryDirectory


class UiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance = TemporaryDirectory()
        os.environ.update(INSTANCE_DIR=cls.instance.name, SECRET_KEY='test-only',
                          DB_ADMIN_PASSWORD='test-only')
        from app import app, db
        cls.app, cls.db = app, db
        app.config['TESTING'] = True
        # app is imported once per process; an earlier test module may have deleted its instance dir
        os.makedirs(app.config['DB_INSTANCE_DIR'], exist_ok=True)
        with app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.session.remove()
            cls.db.engine.dispose()
        shutil.rmtree(cls.app.config['DB_INSTANCE_DIR'], ignore_errors=True)
        cls.instance.cleanup()

    def tearDown(self):
        with self.app.app_context():
            for table in reversed(self.db.metadata.sorted_tables):
                self.db.session.execute(table.delete())
            self.db.session.commit()

    def admin_client(self):
        c = self.app.test_client()
        c.post('/manage-db-login', data={'password': 'test-only'})
        return c


class UiTests(UiTestCase):
    def test_index_real_metrics(self):
        from core.models import Project, Task
        today = date.today()
        prev = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        with self.app.app_context():
            late = Project(name='late', status='進行中', category='c', rep='r',
                           start_date=today - timedelta(days=30), end_date=today - timedelta(days=1))
            closed = Project(name='done', status='已結案', category='c', rep='r',
                             start_date=today - timedelta(days=30), end_date=today - timedelta(days=1))
            self.db.session.add_all([late, closed])
            self.db.session.flush()
            for who, d, hours in (('A', today, 16), ('B', today, 8), ('A', prev, 8)):
                self.db.session.add(Task(personnel=who, project_id=late.id, date=d,
                                         day_hours=hours, description='x'))
            self.db.session.commit()
        html = self.app.test_client().get('/').get_data(as_text=True)
        self.assertIn('1 案已逾期', html)       # closed project not counted
        self.assertIn('較上月 +16 小時', html)  # 24h this month - 8h last month
        self.assertIn('本月已填報 2 人', html)

    def test_add_proj_hides_resigned_rep_edit_keeps_it(self):
        from core.models import Project, Representative
        with self.app.app_context():
            self.db.session.add_all([Representative(name='Active'),
                                     Representative(name='Gone', resigned_date=date(2026, 1, 1))])
            p = Project(name='p', status='進行中', category='c', rep='Gone', start_date=date.today())
            self.db.session.add(p)
            self.db.session.commit()
            pid = p.id
        c = self.app.test_client()
        add = c.get('/add-project').get_data(as_text=True)
        self.assertIn('value="Active"', add)
        self.assertNotIn('value="Gone"', add)
        edit = c.get(f'/edit-project/{pid}').get_data(as_text=True)
        self.assertIn('value="Gone"', edit)

    def test_add_rep_with_resigned_date(self):
        from core.models import Representative
        c = self.admin_client()
        c.post('/manage-reps', data={'action': 'add', 'rep_name': 'Gone', 'resigned_date': '2026/03/31'})
        c.post('/manage-reps', data={'action': 'add', 'rep_name': 'Here', 'resigned_date': ''})
        c.post('/manage-reps', data={'action': 'add', 'rep_name': 'Bad', 'resigned_date': '2026-02-30'})
        with self.app.app_context():
            self.assertEqual(Representative.query.filter_by(name='Gone').one().resigned_date, date(2026, 3, 31))
            self.assertIsNone(Representative.query.filter_by(name='Here').one().resigned_date)
            self.assertIsNone(Representative.query.filter_by(name='Bad').first())

    def test_related_counts_rendered(self):
        from core.models import Category, Personnel, Project, Representative, Task
        with self.app.app_context():
            db = self.db
            db.session.add_all([Category(name='CatX'), Personnel(name='PerX'), Representative(name='RepX')])
            proj = Project(name='P1', status='進行中', rep='RepX', category='CatX', start_date=date(2026, 1, 1))
            db.session.add(proj)
            db.session.flush()
            for _ in range(3):
                db.session.add(Task(project_id=proj.id, personnel='PerX', date=date(2026, 1, 2), day_hours=8,
                                    description='d'))
            db.session.commit()
        c = self.admin_client()
        self.assertIn('關聯工作紀錄 3 筆', c.get('/manage-personnel').get_data(as_text=True))
        self.assertIn('關聯專案 1 個', c.get('/manage-categories').get_data(as_text=True))
        self.assertIn('關聯專案 1 個', c.get('/manage-reps').get_data(as_text=True))


OLD_TASK_DDL = (
    'CREATE TABLE task (id INTEGER PRIMARY KEY, personnel VARCHAR(50) NOT NULL, date DATE NOT NULL, '
    'work_days FLOAT NOT NULL, day_hours FLOAT, overtime_hours FLOAT, night_hours FLOAT, '
    'description TEXT NOT NULL, notes TEXT, project_id INTEGER NOT NULL)')


class WorkHoursTests(UiTestCase):
    def _task_cols(self):
        from sqlalchemy import text
        return {r[1] for r in self.db.session.execute(text('PRAGMA table_info(task)'))}

    def test_migration_converts_days_and_drops_column(self):
        from sqlalchemy import text
        from core.helpers import migrate_work_days_to_hours
        with self.app.app_context():
            self.db.session.remove()
            with self.db.engine.begin() as conn:
                conn.execute(text('DROP TABLE task'))
                conn.execute(text(OLD_TASK_DDL))
                conn.execute(text(
                    "INSERT INTO task (id, personnel, date, work_days, day_hours, overtime_hours, night_hours, "
                    "description, project_id) VALUES "
                    "(1, 'A', '2026-01-01', 1.5, NULL, NULL, NULL, 'd', 1), "
                    "(2, 'A', '2026-01-02', 3, NULL, 2, NULL, 'd', 1)"))
            self.assertTrue(migrate_work_days_to_hours())
            self.assertNotIn('work_days', self._task_cols())
            rows = self.db.session.execute(text(
                'SELECT id, day_hours, overtime_hours FROM task ORDER BY id')).fetchall()
            self.assertEqual([tuple(r) for r in rows], [(1, 12.0, None), (2, None, 2.0)])
            self.assertFalse(migrate_work_days_to_hours())  # idempotent no-op
            self.assertEqual(len(self.db.session.execute(text('SELECT id FROM task')).fetchall()), 2)

    def test_task_form_requires_positive_hours(self):
        from core.models import Project, Task
        with self.app.app_context():
            p = Project(name='P', status='進行中', category='c', rep='r', start_date=date(2026, 1, 1))
            self.db.session.add(p)
            self.db.session.commit()
            pid = p.id
        c = self.app.test_client()
        form = {'personnel': 'A', 'project_id': str(pid), 'date': '2026-01-05', 'description': 'x'}
        c.post('/add-task', data={**form, 'day_hours': '0'})
        c.post('/add-task', data=form)
        with self.app.app_context():
            self.assertEqual(Task.query.count(), 0)
        c.post('/add-task', data={**form, 'overtime_hours': '2'})
        with self.app.app_context():
            t = Task.query.one()
            self.assertEqual(t.total_hours, 2)
            tid = t.id
        c.post(f'/edit-task/{tid}', data={**form, 'overtime_hours': '0'})
        with self.app.app_context():
            self.assertEqual(self.db.session.get(Task, tid).total_hours, 2)  # rejected, unchanged

    def test_import_old_csv_with_days_only(self):
        import io
        from core.models import Project, Task
        with self.app.app_context():
            self.db.session.add(Project(name='P', status='進行中', category='c', rep='r',
                                        start_date=date(2026, 1, 1)))
            self.db.session.commit()
        csv = ('所屬專案,人員,日期,工作天數,日班時數,加班時數,夜班時數,工作描述,備註\n'
               'P,A,2026/01/05,1.5,,,,only days,\n'
               'P,A,2026/01/06,3,,2,,has hours,\n')
        c = self.admin_client()
        c.post('/api/import-tasks', data={'csv_file': (io.BytesIO(csv.encode('utf-8-sig')), 'old.csv')},
               content_type='multipart/form-data')
        with self.app.app_context():
            by_desc = {t.description: t for t in Task.query.all()}
            self.assertEqual(by_desc['only days'].day_hours, 12.0)
            self.assertIsNone(by_desc['has hours'].day_hours)
            self.assertEqual(by_desc['has hours'].total_hours, 2)




class SecurityTests(UiTestCase):
    def setUp(self):
        from core.routes import admin
        admin._login_failures.clear()

    def test_login_locks_after_repeated_failures(self):
        c = self.app.test_client()
        for _ in range(5):
            c.post('/manage-db-login', data={'password': 'wrong'})
        c.post('/manage-db-login', data={'password': 'test-only'})
        with c.session_transaction() as sess:
            self.assertFalse(sess.get('db_admin_auth'))

    def test_login_succeeds_with_correct_password(self):
        c = self.admin_client()
        with c.session_transaction() as sess:
            self.assertTrue(sess.get('db_admin_auth'))

    def test_redirect_to_rejects_external_urls(self):
        from core.routes.tasks import _safe_redirect_target
        with self.app.test_request_context():
            self.assertEqual(_safe_redirect_target('/employee-case?person=A'), '/employee-case?person=A')
            for evil in ('https://evil.example', '//evil.example', r'/\evil.example', None, ''):
                self.assertEqual(_safe_redirect_target(evil), '/manage-db')

    def test_session_cookie_is_samesite_lax(self):
        self.assertEqual(self.app.config['SESSION_COOKIE_SAMESITE'], 'Lax')

if __name__ == '__main__':
    unittest.main()
