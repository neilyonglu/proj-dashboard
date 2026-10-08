# ARCHITECTURE — proj_dashboard (reference)

Extracted from the old CLAUDE.md on 2026-07-06; updated for v1.4.3 on 2026-10-08. This is a convenience map — the code
is the source of truth. If this file disagrees with the code, fix this file
(see global `40-maintenance.md`).

## Directory layout

```
app.py              entry point (Flask init, config, startup, APP_VERSION)
core/
  extensions.py       db = SQLAlchemy()  (avoids circular imports)
  models.py           DB models
  helpers.py          utilities (backup + daily scheduler, migration, form parsing,
                      compute_back_url)
  routes/
    __init__.py       register_routes(app) — mounts all route modules
    main.py           dashboard, timeline, employee page, overtime stats
    projects.py       project CRUD
    tasks.py          task (work-hours) CRUD
    admin.py          admin login, backup API, CSV export/import
    manage.py         personnel / representative / category management
templates/          Jinja2 templates (base.html = shared document, styles and scripts)
static/
  css/style.css, js/main.js, js/tailwind-config.js, avatars/
instance/app.db     SQLite DB (not in VCS); backups in instance/backups/, logs in instance/logs/
.env                SECRET_KEY, DB_ADMIN_PASSWORD (both required)
Dockerfile          python:3.12-slim image, non-root, waitress on :5001
docker-compose.yml  build args UID/GID + bind mounts for instance/ and avatars/
requirements.txt    pinned runtime deps
```

## Models (core/models.py)

| Model | Purpose |
|---|---|
| `Representative` | sales representative |
| `Personnel` | employee (avatar path, display name) |
| `Category` | project category |
| `Project` | project (dates, status, equipment, description) |
| `Task` | work-hours record, FK to Project; person, work days, day/overtime/night hours |

- Deleting a `Project` cascades to its `Task`s.
- `Task.day_hours` / `overtime_hours` / `night_hours` are optional and coexist with
  `work_days`. Old DBs get missing columns via `ensure_task_columns()` (ALTER TABLE
  at startup, defined in `core/helpers.py`).
- First startup seeds 3 representatives, 5 categories, 6 personnel (end of `app.py`).

## Routes

Public (`core/routes/main.py`, `projects.py`, `tasks.py`):

| Route | Purpose |
|---|---|
| `GET /` | dashboard |
| `GET/POST /add-project`, `/edit-project/<id>`; `POST /delete-project/<id>` | project CRUD |
| `GET/POST /add-task`, `/edit-task/<id>`; `POST /delete-task/<id>` | task CRUD |
| `GET /timeline` | Gantt chart (month/quarter/year zoom) |
| `GET /project/<id>` | project detail page |
| `GET /employee-case` | per-employee dashboard |
| `GET /overtime-stats` | overtime statistics |

Admin, session-gated (`admin.py`, `manage.py`):

| Route | Purpose |
|---|---|
| `GET/POST /manage-db-login`; `GET /manage-db` | admin login / home |
| `GET/POST /manage-personnel`, `/manage-reps`, `/manage-categories` | entity management |
| `/api/export-db`, `/api/import-db` | projects CSV |
| `/api/export-tasks`, `/api/import-tasks` | tasks CSV |
| `/api/export-reps`, `/api/import-reps` | representatives CSV |
| `/api/export-personnel`, `/api/import-personnel` | personnel CSV |
| `/api/export-categories`, `/api/import-categories` | categories CSV |
| `GET /api/export-all` | whole DB as one .xlsx, one sheet per table (admin-auth gated) |
| `POST /api/import-all` | whole DB from that .xlsx: imports sheets in order (reps → categories → personnel → projects → tasks) so name references resolve; `skip`/`overwrite` mode, optional wipe-all-tables-first (auto-backs up) |
| `GET /api/backup-download`; `POST /api/backup-now`, `/api/backup-restore` | DB backup |

## Design decisions that are NOT obvious from a quick read

- Route modules expose `def register(app):` and are mounted by `register_routes(app)`
  — deliberately NOT Blueprints, to keep `url_for` names stable. Do not convert.
- Renaming a Personnel code updates all `Task.personnel`; renaming a Category or
  Representative updates matching `Project` fields (`core/routes/manage.py`).
  Preserve this propagation when touching those routes.
- Manage pages' "back" buttons use server-side `back_url` from `compute_back_url()`
  (`core/helpers.py`) — `history.back()` was removed because bfcache served stale
  pages. Do not reintroduce it.
- Frontend dates are parsed with `parseLocalDate()` — defined inline in
  `templates/proj_timeline.html` (~line 402), NOT in `static/js/main.js` (that file
  is combobox code). `new Date('YYYY-MM-DD')` is treated as UTC and shifts months
  (April bled into May).
- `Project.status` holds a single value, one of 進行中/等待中/暫緩中/已結案, set via
  a dropdown in the add/edit forms. The project list/timeline/manage-DB table
  status filters are multi-select (any-of match against each row's single value)
  — that multi-select lives only in those table filters, not in the project's
  own status field.
- `Personnel.resigned_date` (nullable `Date`) marks former employees; `NULL` =
  active. `/employee-case`'s personnel dropdown filters to active only
  (`core/routes/main.py`), and so does `/add-task`; `/edit-task/<id>` lists active
  personnel plus the task's current person (even if resigned) so the combobox
  still resolves its value (`core/routes/tasks.py`). A resigned person is still reachable by direct
  link (e.g. from the timeline's 離職 badge) since that lookup isn't filtered.
- CSV import auto-detects UTF-8 / UTF-8-BOM / BIG5 (Excel compatibility); import
  modes are `skip` (skip duplicates) or `overwrite`.
- `import_all` (whole-DB `.xlsx` import) reuses the same per-table skip/overwrite
  logic as the individual CSV importers, just reading from workbook sheets
  (`_sheet_rows()`) instead of `csv.DictReader`. Sheet order matters: reps and
  categories first, then personnel, then projects (auto-creates any missing
  rep/category, same as `import_db`), then tasks last since each task row
  resolves its project by name.
- Dashboard: four public feature cards. The top-right link shows 「管理者登入」
  when logged out and 「資料庫管理」 when authenticated; there is no DB card.
  `POST /manage-db-login` validates the configured password, sets
  `session['db_admin_auth'] = True`, and redirects directly to `/manage-db`.
  A wrong password redirects back to login without granting access.
- `/manage-personnel`, `/manage-reps`, `/manage-categories` are admin-gated
  (`_require_auth()` from `admin.py`, redirects to `/manage-db-login`). The
  「管理名單／管理種類」links on the add/edit project forms are wrapped in
  `{% if session.get('db_admin_auth') %}` so normal users never see them.
  Task forms have no personnel-management link, even for admins; the entry is
  「參與人員 → 管理參與人員」 in `/manage-db`. The server-side guard enforces access
  independently of link visibility, including direct requests to admin URLs.
- Avatar upload: PNG/JPG/GIF/WebP only, max 5 MB.
- Admin auth: `session['db_admin_auth']`; password from `DB_ADMIN_PASSWORD`.
  `SECRET_KEY` and `DB_ADMIN_PASSWORD` have NO defaults — `app.py` raises at
  import time if either is unset, so a container can never boot with a known
  password. `.env` uses `setdefault`, so real environment variables win over the
  file (needed for `docker compose` overrides).
- DB backup: once per day, checked at startup AND hourly via a background thread
  (`start_daily_backup_scheduler`, `core/helpers.py`) so a server left running for
  days without restart still gets a daily backup — startup-only used to mean no
  backup ever happened again until the next restart. Backs up to
  `instance/backups/`, keep `BACKUP_KEEP=10`. Paths come from
  `current_app.config['DB_FILE_PATH']` / `['DB_INSTANCE_DIR']`.
- Deployment is Docker-only (Linux). There is no PyInstaller exe, no in-app
  self-update and no `.bat` tooling — updating means `git pull` +
  `docker compose up -d --build`. `instance/` and `static/avatars/` are bind
  mounts, so rebuilding the image never touches the DB, backups, logs or
  avatars. The container runs as UID/GID passed at build time so those mounts
  stay writable and host-owned.
- Compose publishes host port `5001` to container port `5001` on all interfaces.
  For access only through an SSH tunnel, change the mapping to
  `127.0.0.1:5001:5001`; this restriction is not the default.
- Timezone: the image sets `TZ=Asia/Taipei`; without it `datetime.now()` in
  backup filenames and `instance/logs/` would be UTC (8 hours off).
- `PYTHONUNBUFFERED=1` is required for `docker logs` to show the app's `print()`
  output; backup/startup messages use `flush=True` as well.
