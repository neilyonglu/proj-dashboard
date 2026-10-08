"""Run with python smoke_admin.py; database and log files are temporary."""
import os
from datetime import date
from tempfile import TemporaryDirectory


def main():
    with TemporaryDirectory() as instance:
        os.environ.update(INSTANCE_DIR=instance, SECRET_KEY='smoke-only',
                          DB_ADMIN_PASSWORD='smoke-password')
        from app import app, db
        from core.models import Personnel, Project, Task

        app.config['TESTING'] = True
        with app.app_context():
            db.create_all()
            db.session.add(Personnel(name='Smoke'))
            project = Project(name='Smoke', status='進行中', rep='Smoke',
                              category='Smoke', start_date=date.today())
            db.session.add(project)
            db.session.flush()
            task = Task(personnel='Smoke', project_id=project.id, date=date.today(),
                        work_days=1, description='Smoke')
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        client = app.test_client()
        home = client.get('/').get_data(as_text=True)
        assert '管理者登入' in home and '資料庫管理' not in home
        for path in ('/manage-db', '/manage-personnel'):
            response = client.get(path)
            assert response.status_code == 302
            assert response.location.endswith('/manage-db-login')
        response = client.post('/manage-db-login', data={'password': 'wrong'})
        assert response.location.endswith('/manage-db-login')
        with client.session_transaction() as session:
            assert not session.get('db_admin_auth')
        response = client.post('/manage-db-login', data={'password': 'smoke-password'})
        assert response.location.endswith('/manage-db')
        with client.session_transaction() as session:
            assert session.get('db_admin_auth') is True
        home = client.get('/').get_data(as_text=True)
        assert '資料庫管理' in home and '管理者登入' not in home
        assert 'manage-db' not in home.split('<main', 1)[1]
        response = client.get('/manage-db')
        assert response.status_code == 200
        assert '/manage-personnel' in response.get_data(as_text=True)
        assert client.get('/manage-personnel').status_code == 200
        for path in ('/add-task', f'/edit-task/{task_id}'):
            response = client.get(path)
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert '管理名單' not in html and '/manage-personnel' not in html
            assert 'name="personnel"' in html and 'Smoke' in html
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
    print('Admin login and personnel entry smoke checks passed.')


if __name__ == '__main__':
    main()
