# ARCHITECTURE — proj-dashboard (reference)

Extracted from the old CLAUDE.md on 2026-07-06; updated for v2.1.0 on 2026-10-19. This is a convenience map — the code
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
templates/          Jinja2 templates; base.html = shared document, theme tokens, component CSS, motion CSS
  _header.html        shared header (nav, theme toggle, admin entry, version chip)
  _flash.html         shared flash messages
  _confirm.html       shared <dialog> confirm
static/
  css/style.css, js/main.js, js/tailwind-config.js, avatars/
instance/app.db     SQLite DB (not in VCS); backups in instance/backups/, logs in instance/logs/
.env                SECRET_KEY, DB_ADMIN_PASSWORD (both required)
Dockerfile          python:3.12-slim image, non-root, waitress on :5001
docker-compose.yml  build args UID/GID + bind mounts for instance/ and avatars/
pyproject.toml      uv application metadata and pinned direct dependencies
uv.lock             cross-platform dependency lockfile
.python-version     Python 3.12 for local uv runs
requirements.txt    exported from uv.lock for Docker
AGENTS.md           agent change, teaching, version and release rules
.github/workflows/deploy.yml  hosted CI followed by self-hosted deployment
scripts/deploy.sh   exact-commit deployment and conflict guards
tests/              stdlib application and Linux deployment checks; tests/test_ui.py = rendered-page checks for the v2 UI
docs/MAINTAINERS.md development, deployment and server migration instructions
```

## Models (core/models.py)

| Model | Purpose |
|---|---|
| `Representative` | sales representative (nullable resigned_date) |
| `Personnel` | employee (avatar path, display name, nullable resigned_date). No upload -> DiceBear avatar (`avatar_url()` in `core/helpers.py`, template global `avatar_src`) |
| `Category` | project category |
| `Project` | project (dates, status, equipment, description) |
| `Task` | work-hours record, FK to Project; person, day/overtime/night hours (`total_hours` property) |

- Deleting a `Project` cascades to its `Task`s.
- Work time is recorded in hours only: `Task.day_hours` / `overtime_hours` / `night_hours`
  (NULL counts as 0; forms require at least one > 0, checked by `hours_valid()`). The old
  `work_days` column no longer exists. Old DBs get missing columns via `ensure_task_columns()`
  (ALTER TABLE at startup, defined in `core/helpers.py`).
- `migrate_work_days_to_hours()` (same file; runs at startup and after a DB restore) converts
  legacy rows: if all three hour fields are NULL, `day_hours = work_days * 8` (1 day = 8h);
  then drops `work_days` (`ALTER TABLE ... DROP COLUMN`, table rebuild on SQLite < 3.35). It
  backs up the DB first (`pre_drop_work_days`) and is a no-op once the column is gone.
- CSV/Excel exports have no days column. Task imports still accept an old 工作天數 column:
  a row with no hour values becomes `day_hours = days * 8`, otherwise the days are ignored.
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
| `GET /employee-case` | per-employee dashboard; `?view=overview[&month=YYYY-MM]` = month calendar of every employee's records (grid and dots rendered server-side by `build_overview()` in `core/routes/main.py`, day popover is a `<dialog>` fed by inline JSON). Task table shows 20 rows at a time (client-side 「載入更多」). |
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
  `templates/proj_timeline.html`, NOT in `static/js/main.js`. `new Date('YYYY-MM-DD')` is treated as UTC and shifts months
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
- Dashboard: four public feature cards and three stat cards with chips (month-over-month
  work days, overdue = status not 已結案 and `end_date` before today, personnel who
  reported this month). The admin link lives in the shared header on every page:
  「管理者登入」 when logged out, 「資料庫管理」 when authenticated; there is no DB card.
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
- DB personnel and representative tables show all records, with active/resigned
  status and resignation dates. `Representative.resigned_date` follows the same
  NULL = active convention as Personnel; it is editable in `/manage-reps`.
  This does not filter representative options in project forms.
- `ensure_people_columns()` adds missing resignation columns to both tables at
  startup and immediately after restoring an old SQLite backup. Existing rows
  default to NULL; startup takes a backup before migration.
- Personnel and representative CSV/Excel exports include `離職日期` (ISO date).
  Imports accept YYYY-MM-DD or YYYY/MM/DD; overwrite mode updates a supplied
  date, blank clears it, and a missing column preserves existing dates. Invalid
  dates follow the import error/rollback path; representative form validation
  rejects the update before changing its name or linked projects.
- Frontend structure (v2 "Obsidian Precision" UI; Tailwind Play CDN, no build step):
  - `base.html` includes `_header.html`, `_flash.html` and
    `_confirm.html` (blocks `site_header` and `flash` are overridable). Header nav
    highlighting comes from `request.endpoint` (`nav_items` in `_header.html`).
  - Theme: an inline script in `<head>` reads `localStorage.theme`
    (`light` | `dark` | `system`, default `dark`) and toggles `.dark` on `<html>` before
    first paint; the header button (`[data-theme-toggle]`, `main.js`) cycles modes.
  - Colors are CSS variables in `base.html` (`:root` light, `.dark` dark: `--surface`,
    `--surface-muted`, `--line`, `--ink`, `--ink-muted`, `--st-*` status colors).
    `static/js/tailwind-config.js` remaps the slate/blue palettes and exposes them as
    semantic utilities (`bg-surface`, `text-ink`, `border-line`, `status-*`). Prefer the
    tokens over raw `slate-*`.
  - Component classes in `base.html` (`type="text/tailwindcss"` so `@apply` works):
    `.btn` (+ `-primary/-secondary/-ghost/-danger`), `.input`, `.panel`, `.num`.
  - Motion CSS in `base.html`: `anim-pop`, `anim-dropdown`, `anim-rise`, `num-pop`
    (stagger via `--i`), `shake`, `.interactive`, `[data-tabs]` + `.tab-indicator`,
    `:user-invalid` red border; all disabled under `prefers-reduced-motion`.
  - `static/js/main.js` helpers: `initCombobox`, `confirmDialog(msg, {title, confirmText})`
    -> Promise<boolean> (fails closed), `<form|a data-confirm="...">` auto-confirm,
    theme toggle, flash dismiss (success auto-hides after 4 s, errors stay),
    `downloadCsv(filename, rows)` (UTF-8 BOM, formula-injection guard),
    `filterRows(input, rowSelector, noMatchId, extraTest)`, `[data-hours-total]` /
    `[data-hours]` / `[data-char-count]` auto-binding on task forms, `invalid` shake,
    and the `[data-tabs]` sliding indicator.
  - `tests/test_ui.py` renders pages with the Flask test client (temporary instance dir)
    and asserts the v2 behaviors (e.g. dashboard metrics).
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
- Local development: `uv sync --locked`, set development environment variables
  (including `HOST=127.0.0.1`), then `uv run app.py`. See `docs/MAINTAINERS.md`;
  production `.env` stays on the server. Python 3.12 and runtime dependencies
  are managed in `.venv`; no package build or custom launcher is needed. Local
  data uses `instance/` and `static/avatars/`, both ignored by Git.
- Dependency source: `pyproject.toml` and `uv.lock`. Export `requirements.txt`
  with `uv export --locked --no-hashes --no-header --no-annotate --no-emit-project --output-file requirements.txt`
  after dependency changes, so Docker and local uv runs use the same resolved versions.
- Production deployment uses Docker (Linux). There is no PyInstaller exe, no in-app
  self-update and no `.bat` tooling. The workflow draft tests the triggering main
  commit on GitHub-hosted CI, then the dedicated self-hosted runner fast-forwards
  server main to that exact SHA and runs `docker compose build` followed by
  `docker compose up --detach --remove-orphans --wait --wait-timeout 120`.
  It is not enabled until authorized push, runner setup and server migration.
  `instance/` and `static/avatars/` are bind
  mounts, so rebuilding the image never touches the DB, backups, logs or
  avatars. The container runs as UID/GID passed at build time so those mounts
  stay writable and host-owned.
- Compose project name comes from `COMPOSE_PROJECT_NAME=proj-dashboard`;
  `DASHBOARD_PORT=5001` publishes host port 5001 to container port 5001. The
  renamed deployment root is `/home/genton/Proj/proj-dashboard`; migration of
  the running old project is documented in `docs/MAINTAINERS.md`.
  For access only through an SSH tunnel, change the mapping to
  `127.0.0.1:5001:5001`; this restriction is not the default.
- Timezone: the image sets `TZ=Asia/Taipei`; without it `datetime.now()` in
  backup filenames and `instance/logs/` would be UTC (8 hours off).
- `PYTHONUNBUFFERED=1` is required for `docker logs` to show the app's `print()`
  output; backup/startup messages use `flush=True` as well.
