from datetime import date, timedelta
from zlib import crc32

from flask import render_template, request, session, url_for
from sqlalchemy import func
from ..extensions import db
from ..helpers import avatar_url
from ..models import Project, Task, Personnel

# Overview calendar: one stable colour per employee (rank by Personnel.id, so it is the
# same in every month), picked from this palette; no database column needed.
OVERVIEW_PALETTE = [
    '#6872e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#84cc16', '#8b5cf6',
    '#f97316', '#14b8a6', '#3b82f6', '#eab308', '#d946ef', '#22c55e', '#0ea5e9', '#f43f5e',
]

MAX_DOTS = 10  # dots per day cell before collapsing into "+N"


def _parse_month(raw, today):
    try:
        y, m = (raw or '').split('-')
        y, m = int(y), int(m)
        date(y, m, 1)
        return y, m
    except (ValueError, TypeError):
        return today.year, today.month


def build_overview(month_raw):
    """Data for the month-calendar overview of every employee's task records."""
    today = date.today()
    y, m = _parse_month(month_raw, today)
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    tasks = Task.query.filter(Task.date >= start, Task.date < end).order_by(Task.date, Task.id).all()
    people = Personnel.query.order_by(Personnel.id).all()
    by_name = {p.name: p for p in people}
    color_of = {p.name: OVERVIEW_PALETTE[i % len(OVERVIEW_PALETTE)] for i, p in enumerate(people)}

    employees, seen, days = [], set(), {}
    for t in tasks:
        if t.personnel not in seen:
            seen.add(t.personnel)
            p = by_name.get(t.personnel)
            employees.append({
                'name': t.personnel,
                'display': (p.display_name or p.name) if p else t.personnel,
                'color': color_of.get(t.personnel) or OVERVIEW_PALETTE[crc32(t.personnel.encode('utf-8')) % len(OVERVIEW_PALETTE)],
                'avatar': avatar_url(t.personnel, p.avatar_filename if p else None),
                'resigned': bool(p and p.resigned_date),
            })
        days.setdefault(t.date.isoformat(), []).append({
            'p': t.personnel,
            'project': t.project.name if t.project else 'N/A',
            'url': url_for('project_detail', id=t.project_id) if t.project else '',
            'desc': t.description or '',
            'day': t.day_hours or 0, 'ot': t.overtime_hours or 0, 'night': t.night_hours or 0,
            'total': t.total_hours,
        })
    employees.sort(key=lambda e: e['display'])

    # 7-column grid, Sunday first; leading/trailing days of adjacent months are dimmed
    # and carry no dots (only the visible month is queried).
    first_wd = (start.weekday() + 1) % 7
    grid_start = start - timedelta(days=first_wd)
    rows = -(-(first_wd + (end - start).days) // 7)
    emp_by_name = {e['name']: e for e in employees}
    cells = []
    for i in range(rows * 7):
        d = grid_start + timedelta(days=i)
        in_month = (d.year, d.month) == (y, m)
        recs = days.get(d.isoformat(), []) if in_month else []
        names = sorted({r['p'] for r in recs}, key=lambda n: emp_by_name[n]['display'])
        cells.append({
            'iso': d.isoformat(), 'day': d.day, 'in_month': in_month,
            'today': d == today, 'weekend': i % 7 in (0, 6), 'count': len(recs),
            'dots': [emp_by_name[n] for n in names[:MAX_DOTS]],
            'more': max(0, len(names) - MAX_DOTS),
        })

    years = [d for (d,) in db.session.query(func.strftime('%Y', Task.date)).distinct()]
    year_nums = [int(v) for v in years if v] + [today.year, y]
    prev_y, prev_m = (y - 1, 12) if m == 1 else (y, m - 1)
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
    return {
        'year': y, 'month': m, 'employees': employees, 'days': days, 'cells': cells,
        'years': list(range(min(year_nums), max(year_nums) + 2)),
        'prev': f'{prev_y:04d}-{prev_m:02d}', 'next': f'{next_y:04d}-{next_m:02d}',
        'is_current': (y, m) == (today.year, today.month),
    }


def register(app):

    @app.route('/')
    def index():
        active_projects_count = Project.query.filter_by(status='進行中').count()
        total_personnel = Personnel.query.count()
        today = date.today()
        start_of_month = date(today.year, today.month, 1)
        end_of_month = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
        tasks_this_month = Task.query.filter(Task.date >= start_of_month, Task.date < end_of_month).all()
        monthly_hours = sum(t.total_hours for t in tasks_this_month)
        start_of_prev = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
        prev_hours = (db.session.query(func.coalesce(func.sum(
                          func.coalesce(Task.day_hours, 0) + func.coalesce(Task.overtime_hours, 0)
                          + func.coalesce(Task.night_hours, 0)), 0))
                      .filter(Task.date >= start_of_prev, Task.date < start_of_month).scalar())
        # overdue = project not closed (已結案) whose end_date is set and already past
        overdue_projects = Project.query.filter(Project.status != '已結案', Project.end_date < today).count()
        reported_count = len({t.personnel for t in tasks_this_month})
        return render_template('index.html',
                               hours_diff=monthly_hours - prev_hours,
                               overdue_projects=overdue_projects,
                               reported_count=reported_count,
                               active_projects=active_projects_count,
                               total_personnel=total_personnel,
                               monthly_hours=monthly_hours)

    @app.route('/employee-case')
    def employee_case():
        if request.args.get('view') == 'overview':
            personnel_list = [(p.name, p.display_name or p.name) for p in
                              Personnel.query.filter(Personnel.resigned_date.is_(None)).order_by(Personnel.name)]
            return render_template('employee_case.html', view='overview', personnel_list=personnel_list,
                                   selected=None, overview=build_overview(request.args.get('month')))
        personnel_all = Personnel.query.filter(Personnel.resigned_date.is_(None)).order_by(Personnel.name).all()
        if not personnel_all:
            return render_template('employee_case.html', view='person',
                                   personnel_list=[], selected=None, display_name='',
                                   avatar_filename=None, tasks=[], total_hours=0,
                                   project_count=0, filter_project=None)
        personnel_list = [(p.name, p.display_name or p.name) for p in personnel_all]
        selected = request.args.get('person', personnel_list[0][0])
        selected_p = Personnel.query.filter_by(name=selected).first()
        if not selected_p:
            selected_p = personnel_all[0]
            selected = selected_p.name

        project_id = request.args.get('project_id', type=int)
        filter_project = None
        if project_id:
            tasks = Task.query.filter_by(personnel=selected, project_id=project_id).order_by(Task.date.desc()).all()
            filter_project = Project.query.get(project_id)
        else:
            tasks = Task.query.filter_by(personnel=selected).order_by(Task.date.desc()).all()

        return render_template('employee_case.html',
                               view='person',
                               personnel_list=personnel_list,
                               selected=selected,
                               display_name=selected_p.display_name or selected_p.name,
                               avatar_filename=selected_p.avatar_filename,
                               tasks=tasks,
                               total_hours=sum(t.total_hours for t in tasks),
                               project_count=len(set(t.project_id for t in tasks)),
                               filter_project=filter_project,
                               is_admin=bool(session.get('db_admin_auth')))

    @app.route('/overtime-stats')
    def overtime_stats():
        today = date.today()
        granularity = request.args.get('granularity', 'month')
        if granularity not in ('day', 'month', 'year', 'range'):
            granularity = 'month'
        period = (request.args.get('period') or '').strip()

        period_value = prev_value = next_value = ''
        range_start_value = range_end_value = ''

        if granularity == 'day':
            try:
                d = date.fromisoformat(period)
            except ValueError:
                d = today
            start, end = d, d + timedelta(days=1)
            period_value = d.strftime('%Y-%m-%d')
            period_label = d.strftime('%Y/%m/%d')
            prev_value = (d - timedelta(days=1)).strftime('%Y-%m-%d')
            next_value = (d + timedelta(days=1)).strftime('%Y-%m-%d')
        elif granularity == 'year':
            try:
                y = int(period)
            except (ValueError, TypeError):
                y = today.year
            start, end = date(y, 1, 1), date(y + 1, 1, 1)
            period_value = str(y)
            period_label = f'{y} 年'
            prev_value = str(y - 1)
            next_value = str(y + 1)
        elif granularity == 'range':
            def _parse(s, fallback):
                try:
                    return date.fromisoformat(s)
                except (ValueError, TypeError):
                    return fallback
            rs = _parse((request.args.get('start') or '').strip(), date(today.year, today.month, 1))
            re_ = _parse((request.args.get('end') or '').strip(), today)
            if re_ < rs:
                rs, re_ = re_, rs
            start, end = rs, re_ + timedelta(days=1)
            range_start_value = rs.strftime('%Y-%m-%d')
            range_end_value = re_.strftime('%Y-%m-%d')
            period_label = f'{rs.strftime("%Y/%m/%d")} ~ {re_.strftime("%Y/%m/%d")}'
        else:  # month
            try:
                yy, mm = period.split('-')
                y, m = int(yy), int(mm)
                date(y, m, 1)
            except (ValueError, TypeError):
                y, m = today.year, today.month
            start = date(y, m, 1)
            end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            period_value = f'{y:04d}-{m:02d}'
            period_label = f'{y}/{m:02d}'
            pm_y, pm_m = (y - 1, 12) if m == 1 else (y, m - 1)
            nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
            prev_value = f'{pm_y:04d}-{pm_m:02d}'
            next_value = f'{nm_y:04d}-{nm_m:02d}'

        tasks = Task.query.filter(Task.date >= start, Task.date < end).all()
        name_map = {p.name: (p.display_name or p.name) for p in Personnel.query.all()}

        by_personnel = {}
        by_project = {}
        total_day = total_overtime = total_night = 0.0
        record_count = 0

        for t in tasks:
            dh = t.day_hours or 0
            ot = t.overtime_hours or 0
            nt = t.night_hours or 0
            if dh == 0 and ot == 0 and nt == 0:
                continue
            total_day += dh
            total_overtime += ot
            total_night += nt
            record_count += 1

            prec = by_personnel.setdefault(t.personnel, {
                'name': t.personnel,
                'display_name': name_map.get(t.personnel, t.personnel),
                'day': 0.0, 'overtime': 0.0, 'night': 0.0, 'count': 0})
            prec['day'] += dh
            prec['overtime'] += ot
            prec['night'] += nt
            prec['count'] += 1

            pname = t.project.name if t.project else '（未知專案）'
            jrec = by_project.setdefault(pname, {
                'name': pname, 'day': 0.0, 'overtime': 0.0, 'night': 0.0, 'count': 0})
            jrec['day'] += dh
            jrec['overtime'] += ot
            jrec['night'] += nt
            jrec['count'] += 1

        sort_key = lambda r: (r['overtime'], r['night'], r['day'])
        return render_template('overtime_stats.html',
                               granularity=granularity,
                               period_value=period_value,
                               period_label=period_label,
                               prev_value=prev_value,
                               next_value=next_value,
                               range_start_value=range_start_value,
                               range_end_value=range_end_value,
                               personnel_stats=sorted(by_personnel.values(), key=sort_key, reverse=True),
                               project_stats=sorted(by_project.values(), key=sort_key, reverse=True),
                               total_day=total_day,
                               total_overtime=total_overtime,
                               total_night=total_night,
                               record_count=record_count)

    @app.route('/timeline')
    def proj_timeline():
        projects = Project.query.order_by(Project.start_date.desc()).all()
        today = date.today()

        if today.month <= 1:
            default_start = date(today.year - 1, 12, 1)
        else:
            default_start = date(today.year, today.month - 1, 1)
        if today.month >= 11:
            default_end = date(today.year + 1, (today.month + 2) - 12, 1)
        else:
            default_end = date(today.year, today.month + 2, 1)

        if not projects:
            timeline_start, timeline_end = default_start, default_end
        else:
            proj_start = min(p.start_date for p in projects)
            proj_end = max((p.end_date or p.start_date) for p in projects)
            timeline_start = min(default_start, proj_start)
            timeline_end = max(default_end, proj_end)

        total_days = max(1, (timeline_end - timeline_start).days)
        default_left_pct = ((default_start - timeline_start).days / total_days) * 100
        default_width_pct = ((default_end - default_start).days / total_days) * 100
        today_pct = ((today - timeline_start).days / total_days) * 100

        STATUS_COLORS = {
            '進行中': 'bg-amber-700/80',
            '暫緩中': 'bg-blue-600/80',
            '等待中': 'bg-pink-700/80',
            '已結案': 'bg-green-700/80',
        }

        timeline_data = []
        for p in projects:
            offset_days = (p.start_date - timeline_start).days
            left_percent = max(0, (offset_days / total_days) * 100)
            end_d = p.end_date if p.end_date else max(today, p.start_date + timedelta(days=1))
            duration_days = max(1, (end_d - p.start_date).days)
            width_percent = min(100 - left_percent, (duration_days / total_days) * 100)

            segments = []
            for t in p.tasks:
                if not t.date:
                    continue
                task_days = max(1, int(t.total_hours // 8))
                task_end = t.date + timedelta(days=task_days)
                t_offset = (t.date - timeline_start).days
                t_left = max(0, (t_offset / total_days) * 100)
                t_width = min(100 - t_left, (max(1, (task_end - t.date).days) / total_days) * 100)
                segments.append({
                    'left': t_left, 'width': t_width,
                    'personnel': t.personnel, 'total_hours': t.total_hours,
                    'date': t.date.strftime('%Y/%m/%d') if t.date else '',
                    'day_hours': t.day_hours, 'overtime_hours': t.overtime_hours,
                    'night_hours': t.night_hours, 'desc': t.description
                })

            timeline_data.append({
                'proj': p, 'left': left_percent, 'width': width_percent,
                'tag_class': STATUS_COLORS.get(p.status, 'bg-slate-500'),
                'segments': segments
            })

        # Build time axis markers
        time_markers = []
        scale = 'year' if total_days > 365 * 3 else ('quarter' if total_days > 365 else 'month')
        if scale == 'year':
            cur = date(timeline_start.year, 1, 1)
        elif scale == 'quarter':
            qm = ((timeline_start.month - 1) // 3) * 3 + 1
            cur = date(timeline_start.year, qm, 1)
        else:
            cur = date(timeline_start.year, timeline_start.month, 1)

        while cur < timeline_end:
            if scale == 'month':
                label = cur.strftime('%Y/%m')
                nm = cur.month + 1 if cur.month < 12 else 1
                ny = cur.year + 1 if cur.month == 12 else cur.year
                nxt = date(ny, nm, 1)
            elif scale == 'quarter':
                label = f"{cur.year} Q{(cur.month - 1) // 3 + 1}"
                nm = cur.month + 3
                ny = cur.year + (1 if nm > 12 else 0)
                nxt = date(ny, nm - 12 if nm > 12 else nm, 1)
            else:
                label = str(cur.year)
                nxt = date(cur.year + 1, 1, 1)

            marker_days = (min(nxt, timeline_end) - max(cur, timeline_start)).days
            if marker_days > 0:
                time_markers.append({'label': label, 'width_percent': (marker_days / total_days) * 100})
            cur = nxt

        resigned_map = {p.name: p.resigned_date.strftime('%Y/%m/%d')
                        for p in Personnel.query.filter(Personnel.resigned_date.isnot(None)).all()}

        return render_template('proj_timeline.html',
                               projects=projects, timeline_data=timeline_data,
                               time_markers=time_markers, resigned_map=resigned_map,
                               timeline_start=timeline_start, timeline_end=timeline_end,
                               default_left_pct=default_left_pct,
                               default_width_pct=default_width_pct,
                               today_pct=today_pct)
