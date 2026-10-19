import json
import os
import re
import shutil
import unittest
from datetime import date

from test_ui import UiTestCase


class EmployeePageTests(UiTestCase):
    def seed(self, extra_tasks=0):
        from core.models import Personnel, Project, Task
        with self.app.app_context():
            proj = Project(name='P1', status='進行中', category='c', rep='r', start_date=date(2026, 1, 1))
            self.db.session.add(proj)
            self.db.session.add_all([
                Personnel(name='Alice', display_name='小愛'),
                Personnel(name='Bob'),
                Personnel(name='Carol', resigned_date=date(2026, 11, 1), avatar_filename='carol.png'),
            ])
            self.db.session.flush()
            for who, d in (('Alice', date(2026, 10, 5)), ('Bob', date(2026, 10, 5)), ('Carol', date(2026, 10, 6))):
                self.db.session.add(Task(personnel=who, project_id=proj.id, date=d, day_hours=8,
                                         overtime_hours=2, description=f'work by {who}'))
            for i in range(extra_tasks):
                self.db.session.add(Task(personnel='Alice', project_id=proj.id, date=date(2026, 9, 1 + i % 28),
                                         day_hours=1, description=f'extra {i}'))
            self.db.session.commit()

    def get(self, url):
        resp = self.app.test_client().get(url)
        self.assertEqual(resp.status_code, 200)
        return resp.get_data(as_text=True)

    def test_overview_calendar_and_dots(self):
        self.seed()
        html = self.get('/employee-case?view=overview&month=2026-10')
        self.assertIn('data-calendar="overview"', html)
        self.assertIn('2026 年 10 月', html)
        self.assertEqual(len(re.findall(r'class="cal-cell', html)), 35)   # Oct 2026 = 5 weeks
        cell = re.search(r'data-date="2026-10-05".*?</button>', html, re.S).group(0)
        self.assertIn('title="小愛"', cell)      # Alice's dot (display name)
        self.assertIn('title="Bob"', cell)
        self.assertNotIn('title="Carol"', cell)
        self.assertIn('title="Carol"', re.search(r'data-date="2026-10-06".*?</button>', html, re.S).group(0))
        # legend lists resigned employees too, as color dot + name only (no avatars anywhere)
        self.assertIn('（已離職）', html)
        self.assertNotIn('dicebear', html)
        self.assertNotIn('/static/avatars/', html)
        self.assertNotIn('avatar', re.search(r'id="overview-data"[^>]*>(.*?)</script>', html, re.S).group(1))

    def test_overview_other_month_and_bad_month(self):
        self.seed()
        html = self.get('/employee-case?view=overview&month=2026-02')   # starts on Sunday -> 4 weeks
        self.assertEqual(len(re.findall(r'class="cal-cell', html)), 28)
        self.assertIn('本月沒有任何工作紀錄', html)
        self.assertNotIn('title="Bob"', html)
        self.assertIn('data-calendar="overview"', self.get('/employee-case?view=overview&month=garbage'))

    def test_person_page_dicebear_and_load_more(self):
        self.seed(extra_tasks=24)   # Alice: 1 + 24 = 25 rows
        html = self.get('/employee-case?person=Alice')
        self.assertIn('id="load-more-btn"', html)
        self.assertIn('載入更多', html)
        self.assertIn('顯示 20 / 共 25 筆', html)
        self.assertIn('seed=Alice&amp;backgroundColor=b6e3f4', html)
        self.assertIn('總覽', html)
        few = self.get('/employee-case?person=Bob')
        self.assertNotIn('id="load-more-btn"', few)
        self.assertIn('顯示 1 / 共 1 筆', few)

    def test_person_page_first_batch_and_full_aggregates(self):
        self.seed(extra_tasks=44)   # Alice: 45 tasks, 8+2 hours + 44 x 1 hour
        html = self.get('/employee-case?person=Alice')
        self.assertEqual(len(re.findall(r'<tr class="hover:bg-surface-muted[^>]*data-date=', html)), 20)
        self.assertIn('顯示 20 / 共 45 筆', html)
        self.assertIn('>54 小時<', html)            # 總工時 over all 45 rows, not the 20 rendered
        self.assertIn('>45 筆<', html)
        agg = json.loads(re.search(r'const TASK_AGG = (\[.*?\]);\n', html, re.S).group(1))
        self.assertEqual(sum(a[2] for a in agg), 45)
        self.assertEqual(sum(a[3] for a in agg), 54)

    def test_load_more_endpoint_slices(self):
        self.seed(extra_tasks=44)
        first = re.findall(r'data-date="([\d-]+)"', self.get('/employee-case?person=Alice'))
        got = list(first)
        for off in (20, 40):
            data = json.loads(self.get(f'/employee-case/tasks?person=Alice&offset={off}&limit=20'))
            self.assertEqual(data['total'], 45)
            self.assertEqual(data['offset'], off)
            self.assertEqual(data['count'], 20 if off == 20 else 5)
            self.assertEqual(data['next_offset'], off + data['count'])
            got += re.findall(r'data-date="([\d-]+)"', data['html'])
        self.assertEqual(len(got), 45)
        self.assertEqual(got, sorted(got, reverse=True))
        self.assertEqual(json.loads(self.get('/employee-case/tasks?person=Alice&offset=45'))['count'], 0)
        # same set of ids as an unpaged read: no overlap, no gaps
        with self.app.app_context():
            from core.models import Task
            all_ids = [t.id for t in Task.query.filter_by(personnel='Alice').order_by(Task.date.desc(), Task.id.desc())]
        ids = []
        for off in (0, 20, 40):
            h = json.loads(self.get(f'/employee-case/tasks?person=Alice&offset={off}'))['html']
            ids += [int(i) for i in re.findall(r'/edit-task/(\d+)', h)]
        self.assertEqual(ids, all_ids)
        self.assertEqual(self.app.test_client().get('/employee-case/tasks?person=Nobody').status_code, 404)

    def test_load_more_respects_project_id_and_delete_admin_only(self):
        from core.models import Project, Task
        self.seed(extra_tasks=24)
        with self.app.app_context():
            p2 = Project(name='P2', status='進行中', category='c', rep='r', start_date=date(2026, 1, 1))
            self.db.session.add(p2)
            self.db.session.flush()
            for i in range(25):
                self.db.session.add(Task(personnel='Alice', project_id=p2.id, date=date(2026, 8, 1 + i),
                                         day_hours=2, description=f'p2 {i}'))
            self.db.session.commit()
            pid = p2.id
        html = self.get(f'/employee-case?person=Alice&project_id={pid}')
        self.assertIn('顯示 20 / 共 25 筆', html)
        self.assertIn('>50 小時<', html)
        data = json.loads(self.get(f'/employee-case/tasks?person=Alice&project_id={pid}&offset=20&limit=20'))
        self.assertEqual((data['total'], data['count']), (25, 5))
        self.assertNotIn('work by', data['html'])
        self.assertNotIn('extra', data['html'])
        self.assertNotIn('delete_task', data['html'])
        self.assertNotIn('data-confirm', data['html'])   # anonymous: no delete form

    def test_header_backup_chip(self):
        backups = os.path.join(self.app.config['DB_INSTANCE_DIR'], 'backups')
        shutil.rmtree(backups, ignore_errors=True)
        self.assertIn('尚無備份', self.get('/'))
        os.makedirs(backups)
        for name in ('app_daily_20260101_123000.db', 'app_startup_20260315_081500.db', 'note.txt'):
            open(os.path.join(backups, name), 'w').close()
        html = self.get('/')
        self.assertIn('上次自動備份：2026/03/15 08:15', html)
        shutil.rmtree(backups, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
