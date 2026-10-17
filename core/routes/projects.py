from collections import defaultdict
from datetime import datetime, date

from flask import render_template, request, redirect, url_for, flash, session
from ..extensions import db
from ..models import Project, Representative, Category
from ..activity_log import log_action


def register(app):

    @app.route('/project/<int:id>')
    def project_detail(id):
        proj = Project.query.get_or_404(id)

        person_map = defaultdict(lambda: {'days': 0.0, 'day_h': 0.0, 'ot_h': 0.0, 'night_h': 0.0, 'count': 0})
        for t in proj.tasks:
            ps = person_map[t.personnel]
            ps['days'] += t.work_days or 0
            ps['day_h'] += t.day_hours or 0
            ps['ot_h'] += t.overtime_hours or 0
            ps['night_h'] += t.night_hours or 0
            ps['count'] += 1

        person_stats = sorted(
            [{'name': k, **v} for k, v in person_map.items()],
            key=lambda x: x['days'], reverse=True
        )

        total_days = sum(p['days'] for p in person_stats)
        has_hours = any(p['day_h'] > 0 or p['ot_h'] > 0 or p['night_h'] > 0 for p in person_stats)
        today = date.today()
        end = proj.end_date if proj.end_date else today
        duration_days = max(0, (end - proj.start_date).days)
        tasks_sorted = sorted(proj.tasks, key=lambda t: t.date, reverse=True)

        return render_template('proj_detail.html',
            proj=proj,
            person_stats=person_stats,
            person_names=[p['name'] for p in person_stats],
            person_days=[p['days'] for p in person_stats],
            person_day_h=[p['day_h'] for p in person_stats],
            person_ot_h=[p['ot_h'] for p in person_stats],
            person_night_h=[p['night_h'] for p in person_stats],
            total_days=total_days,
            has_hours=has_hours,
            duration_days=duration_days,
            tasks_sorted=tasks_sorted)

    @app.route('/add-project', methods=['GET', 'POST'])
    def add_proj():
        if request.method == 'POST':
            name = request.form.get('name')
            status = request.form.get('status')
            category = request.form.get('category')
            rep = request.form.get('rep')
            equipment = request.form.get('equipment')
            description = request.form.get('description')
            notes = request.form.get('notes')
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')

            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
            except ValueError:
                flash('日期格式錯誤', 'error')
                return redirect(url_for('add_proj'))

            if not name or not status or not category or not rep or not start_date:
                flash('請填寫所有必填欄位', 'error')
                return redirect(url_for('add_proj'))

            new_project = Project(name=name, status=status, category=category, rep=rep,
                                  equipment=equipment, description=description,
                                  start_date=start_date, end_date=end_date, notes=notes)
            try:
                db.session.add(new_project)
                if rep and not Representative.query.filter_by(name=rep).first():
                    db.session.add(Representative(name=rep))
                if category and not Category.query.filter_by(name=category).first():
                    db.session.add(Category(name=category))
                db.session.commit()
                log_action(request.remote_addr, '新增專案',
                           f'name={name}, status={status}, rep={rep}')
                flash('✅ 專案已新增！', 'success')
                return redirect(url_for('proj_timeline'))
            except Exception as e:
                db.session.rollback()
                flash(f'發生錯誤：{str(e)}', 'error')

        reps = Representative.query.filter(Representative.resigned_date.is_(None)).order_by(Representative.name).all()
        categories = Category.query.order_by(Category.name).all()
        return render_template('add_proj.html', reps=reps, categories=categories)

    @app.route('/edit-project/<int:id>', methods=['GET', 'POST'])
    def edit_project(id):
        project = Project.query.get_or_404(id)
        if request.method == 'POST':
            project.name = request.form.get('name')
            project.status = request.form.get('status')
            project.category = request.form.get('category')
            project.rep = request.form.get('rep')
            project.equipment = request.form.get('equipment')
            project.description = request.form.get('description')
            project.notes = request.form.get('notes')
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')

            try:
                project.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
                project.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
            except ValueError:
                flash('日期格式錯誤', 'error')
                return redirect(url_for('edit_project', id=id))

            try:
                if project.rep and not Representative.query.filter_by(name=project.rep).first():
                    db.session.add(Representative(name=project.rep))
                if project.category and not Category.query.filter_by(name=project.category).first():
                    db.session.add(Category(name=project.category))
                db.session.commit()
                log_action(request.remote_addr, '編輯專案',
                           f'project_id={id}, name={project.name}, status={project.status}')
                flash('✅ 專案已更新！', 'success')
                return redirect(url_for('proj_timeline'))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗：{str(e)}', 'error')

        reps = Representative.query.order_by(Representative.name).all()
        categories = Category.query.order_by(Category.name).all()
        return render_template('edit_proj.html', project=project, reps=reps, categories=categories)

    @app.route('/delete-project/<int:id>', methods=['POST'])
    def delete_project(id):
        if not session.get('db_admin_auth'):
            log_action(request.remote_addr, '刪除專案（未授權）', f'project_id={id}')
            flash('僅管理者可刪除專案', 'error')
            return redirect(url_for('manage_db'))
        project = Project.query.get_or_404(id)
        try:
            detail = f'project_id={id}, name={project.name}'
            db.session.delete(project)
            db.session.commit()
            log_action(request.remote_addr, '刪除專案', detail)
            flash('✅ 專案已刪除！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'刪除失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))
