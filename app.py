import os

from flask import Flask

APP_VERSION = '1.4.3'

application_path = os.path.dirname(os.path.abspath(__file__))

# ── Load .env (existing environment variables always win) ─────────────────────
env_path = os.path.join(application_path, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── Required secrets ──────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY')
DB_ADMIN_PASSWORD = os.environ.get('DB_ADMIN_PASSWORD')
if not SECRET_KEY or not DB_ADMIN_PASSWORD:
    raise RuntimeError(
        'SECRET_KEY 與 DB_ADMIN_PASSWORD 為必填，請在 .env 或容器環境變數中設定。'
    )

# ── Paths ─────────────────────────────────────────────────────────────────────
instance_dir = os.environ.get('INSTANCE_DIR', os.path.join(application_path, 'instance'))
os.makedirs(instance_dir, exist_ok=True)
db_file_path = os.path.join(instance_dir, 'app.db')

upload_path = os.path.join(application_path, 'static', 'avatars')
os.makedirs(upload_path, exist_ok=True)

# ── Flask app setup ───────────────────────────────────────────────────────────
app = Flask(__name__,
            template_folder=os.path.join(application_path, 'templates'),
            static_folder=os.path.join(application_path, 'static'))

app.secret_key = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_file_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = upload_path
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['DB_FILE_PATH'] = db_file_path
app.config['DB_INSTANCE_DIR'] = instance_dir
app.config['DB_ADMIN_PASSWORD'] = DB_ADMIN_PASSWORD
app.config['APP_VERSION'] = APP_VERSION

from core.extensions import db
db.init_app(app)


@app.context_processor
def inject_app_version():
    return {'app_version': APP_VERSION}


# ── Register all routes ───────────────────────────────────────────────────────
from core.routes import register_routes
register_routes(app)


def bootstrap():
    """Create/migrate the DB and seed defaults. Safe to call more than once."""
    from core.helpers import (backup_database, ensure_task_columns,
                              ensure_personnel_columns, start_daily_backup_scheduler)
    from core.models import Representative, Category, Personnel, Task

    with app.app_context():
        backup_database(reason='startup', once_per_day=True)
        db.create_all()
        ensure_task_columns()
        ensure_personnel_columns()

        if not Representative.query.first():
            for name in ["Leo/許仁豪", "Polly/林惠文", "Hannah/陳胤琦"]:
                db.session.add(Representative(name=name))
            db.session.commit()

        if not Category.query.first():
            for name in ["admin", "admin_reform", "project", "testing", "support"]:
                db.session.add(Category(name=name))
            db.session.commit()

        if not Personnel.query.first():
            for p in [
                {"name": "Jasper", "display_name": "Jasper"},
                {"name": "SeanDu", "display_name": "SeanDu"},
                {"name": "CingYang", "display_name": "Cing Yang"},
                {"name": "Alice", "display_name": "Alice"},
                {"name": "SeanC", "display_name": "SeanC"},
                {"name": "William", "display_name": "William"},
            ]:
                if not Personnel.query.filter_by(name=p['name']).first():
                    db.session.add(Personnel(**p))
            for (name,) in db.session.query(Task.personnel).distinct().all():
                if not Personnel.query.filter_by(name=name).first():
                    db.session.add(Personnel(name=name, display_name=name))
            db.session.commit()

    start_daily_backup_scheduler(app)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    bootstrap()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5001'))
    print(f'系統已啟動：http://{host}:{port}', flush=True)
    from waitress import serve
    serve(app, host=host, port=port)
