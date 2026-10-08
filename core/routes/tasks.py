from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, session
from ..extensions import db
from ..models import Task, Project, Personnel
from ..helpers import parse_shift_hours
from ..activity_log import log_action


def register(app):

    @app.route('/add-task', methods=['GET', 'POST'])
    def add_task():
        if request.method == 'POST':
            personnel = request.form.get('personnel')
            project_id = request.form.get('project_id')
            date_str = request.form.get('date')
            work_days_str = request.form.get('work_days')
            description = request.form.get('description')
            notes = request.form.get('notes')

            try:
                task_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            except ValueError:
                flash('日期格式錯誤', 'error')
                return redirect(url_for('add_task'))

            if not personnel or not project_id or not task_date or not description or not work_days_str:
                flash('請填寫所有必填欄位', 'error')
                return redirect(url_for('add_task'))

            try:
                work_days = float(work_days_str)
            except (ValueError, TypeError):
                flash('工作天數格式錯誤', 'error')
                return redirect(url_for('add_task'))

            day_hours, overtime_hours, night_hours = parse_shift_hours(request.form)
            new_task = Task(personnel=personnel, project_id=int(project_id), date=task_date,
                            work_days=work_days, day_hours=day_hours, overtime_hours=overtime_hours,
                            night_hours=night_hours, description=description, notes=notes)
            try:
                db.session.add(new_task)
                db.session.commit()
                proj = Project.query.get(int(project_id))
                proj_name = proj.name if proj else project_id
                log_action(request.remote_addr, '新增工作紀錄',
                           f'personnel={personnel}, project={proj_name}, date={date_str}, days={work_days}')
                flash('✅ 工作紀錄已新增！', 'success')
                return redirect(url_for('employee_case', person=personnel))
            except Exception as e:
                db.session.rollback()
                flash(f'發生錯誤：{str(e)}', 'error')

        projects = Project.query.order_by(Project.name).all()
        # 新增工作紀錄只列在職人員（resigned_date 為 NULL）
        personnel_list = (Personnel.query
                          .filter(Personnel.resigned_date.is_(None))
                          .order_by(Personnel.name).all())
        prefill_person = request.args.get('person', '')
        return render_template('add_task.html', projects=projects, personnel_list=personnel_list,
                               prefill_person=prefill_person)

    @app.route('/edit-task/<int:id>', methods=['GET', 'POST'])
    def edit_task(id):
        task = Task.query.get_or_404(id)
        redirect_to = request.args.get('redirect_to', url_for('manage_db'))

        if request.method == 'POST':
            task.personnel = request.form.get('personnel')
            task.project_id = int(request.form.get('project_id'))
            task.description = request.form.get('description')
            task.notes = request.form.get('notes')
            redirect_to = request.form.get('redirect_to', url_for('manage_db'))
            date_str = request.form.get('date')
            work_days_str = request.form.get('work_days')

            try:
                task.date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            except ValueError:
                flash('日期格式錯誤', 'error')
                return redirect(url_for('edit_task', id=id, redirect_to=redirect_to))

            try:
                task.work_days = float(work_days_str)
            except (ValueError, TypeError):
                flash('工作天數格式錯誤', 'error')
                return redirect(url_for('edit_task', id=id, redirect_to=redirect_to))

            task.day_hours, task.overtime_hours, task.night_hours = parse_shift_hours(request.form)
            try:
                db.session.commit()
                log_action(request.remote_addr, '編輯工作紀錄',
                           f'task_id={id}, personnel={task.personnel}, date={date_str}')
                flash('✅ 工作紀錄已更新！', 'success')
                return redirect(redirect_to)
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗：{str(e)}', 'error')

        projects = Project.query.order_by(Project.name).all()
        # 只列在職人員，但保留這筆紀錄目前的人員（即使已離職），
        # 否則 combobox 找不到對應選項，欄位會變空白而無法儲存
        personnel_list = (Personnel.query
                          .filter(db.or_(Personnel.resigned_date.is_(None),
                                         Personnel.name == task.personnel))
                          .order_by(Personnel.name).all())
        return render_template('edit_task.html', task=task, projects=projects,
                               personnel_list=personnel_list, redirect_to=redirect_to)

    @app.route('/delete-task/<int:id>', methods=['POST'])
    def delete_task(id):
        if not session.get('db_admin_auth'):
            log_action(request.remote_addr, '刪除工作紀錄（未授權）', f'task_id={id}')
            flash('僅管理者可刪除工作紀錄', 'error')
            redirect_to = request.form.get('redirect_to', url_for('manage_db'))
            return redirect(redirect_to)
        task = Task.query.get_or_404(id)
        redirect_to = request.form.get('redirect_to', url_for('manage_db'))
        try:
            detail = f'task_id={id}, personnel={task.personnel}, date={task.date}'
            db.session.delete(task)
            db.session.commit()
            log_action(request.remote_addr, '刪除工作紀錄', detail)
            flash('✅ 工作紀錄已刪除！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'刪除失敗：{str(e)}', 'error')
        return redirect(redirect_to)