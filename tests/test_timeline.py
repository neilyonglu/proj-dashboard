from datetime import date

from tests.test_ui import UiTestCase


class TimelineFilterTests(UiTestCase):
    def test_timeline_has_period_filter_and_escapes_names(self):
        from core.models import Project
        with self.app.app_context():
            self.db.session.add(Project(name='A<b>&"x', status='進行中', category='c', rep='r',
                                        start_date=date(2025, 3, 1), end_date=date(2025, 5, 31)))
            self.db.session.add(Project(name='open-ended', status='進行中', category='c', rep='r',
                                        start_date=date(2024, 1, 1)))
            self.db.session.commit()
        html = self.admin_client().get('/timeline').get_data(as_text=True)
        for marker in ('id="filter-gran"', 'id="filter-year"', 'id="filter-month"',
                       'id="filter-day"', 'mark.kw-hit', 'function periodOverlaps'):
            self.assertIn(marker, html)
        self.assertIn('data-end=""', html)  # ongoing project exposes empty end date
        self.assertIn('data-start="2025-03-01"', html)
        self.assertNotIn('A<b>&"x', html)  # name must be HTML-escaped
        self.assertIn('A&lt;b&gt;&amp;&#34;x', html)
