import os
import shutil
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

from flask import request, url_for, current_app
from .extensions import db

BACKUP_KEEP = 10
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_task_columns():
    """Add new Task columns to an existing SQLite DB if they don't exist."""
    from sqlalchemy import text
    new_columns = {
        'day_hours': 'FLOAT',
        'overtime_hours': 'FLOAT',
        'night_hours': 'FLOAT',
    }
    with db.engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text('PRAGMA table_info(task)'))}
        for col, col_type in new_columns.items():
            if col not in existing:
                conn.execute(text(f'ALTER TABLE task ADD COLUMN {col} {col_type}'))
        conn.commit()


def ensure_people_columns():
    """Add resignation dates to existing personnel and representative tables."""
    from sqlalchemy import text
    new_columns = {
        'resigned_date': 'DATE',
    }
    with db.engine.connect() as conn:
        for table in ('personnel', 'representative'):
            existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info({table})'))}
            for col, col_type in new_columns.items():
                if col not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
        conn.commit()


def parse_resigned_date(raw):
    value = (raw or '').strip().replace('/', '-')
    return datetime.strptime(value, '%Y-%m-%d').date() if value else None


def compute_back_url(default_endpoint='manage_db'):
    """Return safe 'back' URL from HTTP referrer to avoid stale bfcache."""
    fallback = url_for(default_endpoint)
    ref = request.referrer
    if not ref:
        return fallback
    ref_path = urlparse(ref).path
    if not ref_path or ref_path == request.path:
        return fallback
    return ref


def parse_shift_hours(form):
    """Parse optional shift-hour fields. Returns (day, overtime, night); blank -> None."""
    def _num(key):
        raw = (form.get(key) or '').strip()
        if raw == '':
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None
    return _num('day_hours'), _num('overtime_hours'), _num('night_hours')


def backup_database(reason='auto', once_per_day=False):
    """Copy the SQLite DB into instance/backups/ and prune old copies."""
    db_file_path = current_app.config['DB_FILE_PATH']
    instance_dir = current_app.config['DB_INSTANCE_DIR']
    if not os.path.exists(db_file_path):
        return None
    backups_dir = os.path.join(instance_dir, 'backups')
    os.makedirs(backups_dir, exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    if once_per_day:
        already = [f for f in os.listdir(backups_dir) if f.endswith('.db') and today in f]
        if already:
            print('今日已有備份，略過本次備份。', flush=True)
            return None
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(backups_dir, f'app_{reason}_{timestamp}.db')
    try:
        shutil.copy2(db_file_path, dest)
    except Exception as e:
        print(f'備份失敗：{e}', flush=True)
        return None
    try:
        backups = sorted(
            [f for f in os.listdir(backups_dir) if f.endswith('.db')],
            key=lambda f: os.path.getmtime(os.path.join(backups_dir, f)),
            reverse=True
        )
        for old in backups[BACKUP_KEEP:]:
            os.remove(os.path.join(backups_dir, old))
    except Exception as e:
        print(f'清理舊備份失敗：{e}', flush=True)
    return dest


def start_daily_backup_scheduler(app, check_interval_seconds=3600):
    """Background thread: re-check once per hour so a long-running server
    (never restarted) still gets a daily backup, not just one at startup."""
    def loop():
        while True:
            time.sleep(check_interval_seconds)
            with app.app_context():
                backup_database(reason='daily', once_per_day=True)
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
