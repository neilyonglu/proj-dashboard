import os
import unittest
from datetime import date
from tempfile import TemporaryDirectory


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance = TemporaryDirectory()
        os.environ.update(INSTANCE_DIR=cls.instance.name, SECRET_KEY='test-only',
                          DB_ADMIN_PASSWORD='test-only')
        from app import app, db
        cls.app, cls.db = app, db
        app.config['TESTING'] = True
        with app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.session.remove()
            cls.db.engine.dispose()
        cls.instance.cleanup()

    def test_home_and_admin_auth(self):
        client = self.app.test_client()
        self.assertEqual(client.get('/').status_code, 200)
        for path in ('/manage-db', '/manage-personnel', '/manage-reps'):
            self.assertEqual(client.get(path).status_code, 302)
        client.post('/manage-db-login', data={'password': 'wrong'})
        with client.session_transaction() as session:
            self.assertFalse(session.get('db_admin_auth'))
        client.post('/manage-db-login', data={'password': 'test-only'})
        self.assertEqual(client.get('/manage-db').status_code, 200)
        for path in ('/add-task', '/employee-case', '/timeline', '/overtime-stats'):
            self.assertEqual(client.get(path).status_code, 200, path)

    def test_legacy_migration_preserves_representatives(self):
        from core.helpers import ensure_people_columns
        from core.models import Representative
        with self.app.app_context():
            self.db.session.execute(self.db.text('DROP TABLE representative'))
            self.db.session.execute(self.db.text('CREATE TABLE representative (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)'))
            self.db.session.execute(self.db.text("INSERT INTO representative (name) VALUES ('Legacy')"))
            self.db.session.commit()
            ensure_people_columns()
            ensure_people_columns()
            self.assertIsNone(Representative.query.filter_by(name='Legacy').one().resigned_date)

    def test_resignation_date_validation(self):
        from core.helpers import parse_resigned_date
        self.assertIsNone(parse_resigned_date(''))
        self.assertEqual(parse_resigned_date('2026/09/30'), date(2026, 9, 30))
        with self.assertRaises(ValueError):
            parse_resigned_date('2026-02-30')


if __name__ == '__main__':
    unittest.main()
