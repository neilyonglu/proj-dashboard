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
            for who, d, days in (('A', today, 2), ('B', today, 1), ('A', prev, 1)):
                self.db.session.add(Task(personnel=who, project_id=late.id, date=d,
                                         work_days=days, description='x'))
            self.db.session.commit()
        html = self.app.test_client().get('/').get_data(as_text=True)
        self.assertIn('1 案已逾期', html)       # closed project not counted
        self.assertIn('較上月 +2 天', html)     # 3 this month - 1 last month
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
                db.session.add(Task(project_id=proj.id, personnel='PerX', date=date(2026, 1, 2), work_days=1,
                                    description='d'))
            db.session.commit()
        c = self.admin_client()
        self.assertIn('關聯工作紀錄 3 筆', c.get('/manage-personnel').get_data(as_text=True))
        self.assertIn('關聯專案 1 個', c.get('/manage-categories').get_data(as_text=True))
        self.assertIn('關聯專案 1 個', c.get('/manage-reps').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
