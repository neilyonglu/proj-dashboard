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
        # legend lists resigned employees too; DiceBear fallback only without an upload
        self.assertIn('（已離職）', html)
        self.assertIn('api.dicebear.com/9.x/avataaars/svg?seed=Alice&amp;backgroundColor=b6e3f4', html)
        self.assertIn('/static/avatars/carol.png', html)
        self.assertNotIn('seed=Carol', html)

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
