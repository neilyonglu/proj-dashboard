from datetime import date

from tests.test_ui import UiTestCase


class ProjectDeleteTests(UiTestCase):
    def seed(self, tasks):
        from core.models import Project, Task
        with self.app.app_context():
            p = Project(name='P', status='進行中', category='c', rep='r', start_date=date(2026, 1, 1))
            self.db.session.add(p)
            self.db.session.flush()
            for i in range(tasks):
                self.db.session.add(Task(personnel='A', project_id=p.id, date=date(2026, 1, 1 + i),
                                         day_hours=8, description=f'work {i}'))
            self.db.session.commit()
            return p.id

    def counts(self):
        from core.models import Project, Task
        with self.app.app_context():
            return Project.query.count(), Task.query.count()

    def test_project_with_tasks_needs_force(self):
        pid = self.seed(2)
        c = self.admin_client()
        c.post(f'/delete-project/{pid}')
        self.assertEqual(self.counts(), (1, 2))
        c.post(f'/delete-project/{pid}', data={'force': '1'})
        self.assertEqual(self.counts(), (0, 0))

    def test_project_without_tasks_deletes_directly(self):
        pid = self.seed(0)
        self.admin_client().post(f'/delete-project/{pid}')
        self.assertEqual(self.counts(), (0, 0))

    def test_manage_db_lists_tasks_in_warning(self):
        self.seed(2)
        html = self.admin_client().get('/manage-db').get_data(as_text=True)
        self.assertIn('data-proj-delete="P"', html)
        self.assertIn('work 1', html)
        self.assertIn('id="proj-delete-dialog"', html)
