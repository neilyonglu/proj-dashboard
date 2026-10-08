import os

from flask import render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from ..extensions import db
from ..models import Representative, Personnel, Category, Task, Project
from ..helpers import compute_back_url, allowed_file
from ..activity_log import log_action
from .admin import _require_auth


def register(app):

    @app.route('/manage-reps', methods=['GET', 'POST'])
    def manage_reps():
        # 名單管理僅限已輸入 DB 管理密碼的管理者
        guard = _require_auth()
        if guard:
            return guard
        if request.method == 'POST':
            action = request.form.get('action')
            rep_id = request.form.get('rep_id')
            rep_name = request.form.get('rep_name')

            if action == 'add' and rep_name:
                if not Representative.query.filter_by(name=rep_name).first():
                    db.session.add(Representative(name=rep_name))
                    db.session.commit()
                    log_action(request.remote_addr, '新增業務代表', rep_name)
                    flash('✅ 業務代表已新增！', 'success')
                else:
                    flash('該業務代表已經存在！', 'error')
            elif action == 'edit' and rep_id and rep_name:
                rep = Representative.query.get(rep_id)
                if rep:
                    old_name = rep.name
                    dup = Representative.query.filter(
                        Representative.name == rep_name, Representative.id != rep.id).first()
                    if dup:
                        flash('該業務代表名稱已存在！', 'error')
                    else:
                        rep.name = rep_name
                        Project.query.filter_by(rep=old_name).update({'rep': rep_name})
                        db.session.commit()
                        log_action(request.remote_addr, '編輯業務代表', f'{old_name} → {rep_name}')
                        flash('✅ 業務代表已更新！', 'success')
            elif action == 'delete' and rep_id:
                rep = Representative.query.get(rep_id)
                if rep:
                    name = rep.name
                    db.session.delete(rep)
                    db.session.commit()
                    log_action(request.remote_addr, '刪除業務代表', name)
                    flash('✅ 業務代表已刪除！', 'success')

            return redirect(url_for('manage_reps'))

        reps = Representative.query.order_by(Representative.name).all()
        return render_template('manage_reps.html', reps=reps, back_url=compute_back_url('add_proj'))

    @app.route('/manage-personnel', methods=['GET', 'POST'])
    def manage_personnel():
        # 名單管理僅限已輸入 DB 管理密碼的管理者
        guard = _require_auth()
        if guard:
            return guard
        if request.method == 'POST':
            action = request.form.get('action')
            p_id = request.form.get('id')
            name = request.form.get('name')
            display_name = request.form.get('display_name')

            if action == 'add' and name:
                if not Personnel.query.filter_by(name=name).first():
                    new_p = Personnel(name=name, display_name=display_name)
                    file = request.files.get('avatar')
                    if file and file.filename != '' and allowed_file(file.filename):
                        filename = secure_filename(f"avatar_{name}_{file.filename}")
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        new_p.avatar_filename = filename
                    db.session.add(new_p)
                    db.session.commit()
                    log_action(request.remote_addr, '新增人員', f'name={name}, display={display_name}')
                    flash('✅ 人員已新增！', 'success')
                else:
                    flash('該人員已經存在！', 'error')

            elif action == 'edit' and p_id and name:
                p = Personnel.query.get(p_id)
                if p:
                    old_name = p.name
                    dup = Personnel.query.filter(Personnel.name == name, Personnel.id != p.id).first()
                    if dup:
                        flash('該系統代號已被其他人員使用！', 'error')
                        return redirect(url_for('manage_personnel'))
                    p.name = name
                    p.display_name = display_name
                    resigned_raw = (request.form.get('resigned_date') or '').strip()
                    if resigned_raw:
                        from datetime import datetime
                        try:
                            p.resigned_date = datetime.strptime(resigned_raw, '%Y-%m-%d').date()
                        except ValueError:
                            flash('辭職日期格式錯誤，已略過該欄位', 'error')
                    else:
                        p.resigned_date = None
                    if old_name != name:
                        Task.query.filter_by(personnel=old_name).update({'personnel': name})
                    file = request.files.get('avatar')
                    if file and file.filename != '' and allowed_file(file.filename):
                        filename = secure_filename(f"avatar_{p.id}_{file.filename}")
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        p.avatar_filename = filename
                    db.session.commit()
                    log_action(request.remote_addr, '編輯人員',
                               f'{old_name} → {name}, display={display_name}')
                    flash('✅ 人員資料已更新！（相關工作紀錄已同步更新）', 'success')

            elif action == 'delete' and p_id:
                p = Personnel.query.get(p_id)
                if p:
                    if p.avatar_filename:
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], p.avatar_filename)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    pname = p.name
                    db.session.delete(p)
                    db.session.commit()
                    log_action(request.remote_addr, '刪除人員', pname)
                    flash('✅ 人員已刪除！', 'success')

            return redirect(url_for('manage_personnel'))

        personnel_list = Personnel.query.order_by(Personnel.name).all()
        return render_template('manage_personnel.html', personnel_list=personnel_list,
                               back_url=compute_back_url('manage_db'))

    @app.route('/manage-categories', methods=['GET', 'POST'])
    def manage_categories():
        # 名單管理僅限已輸入 DB 管理密碼的管理者
        guard = _require_auth()
        if guard:
            return guard
        if request.method == 'POST':
            action = request.form.get('action')
            cat_id = request.form.get('cat_id')
            cat_name = request.form.get('cat_name')

            if action == 'add' and cat_name:
                if not Category.query.filter_by(name=cat_name).first():
                    db.session.add(Category(name=cat_name))
                    db.session.commit()
                    log_action(request.remote_addr, '新增專案種類', cat_name)
                    flash('✅ 專案種類已新增！', 'success')
                else:
                    flash('該種類已經存在！', 'error')
            elif action == 'edit' and cat_id and cat_name:
                cat = Category.query.get(cat_id)
                if cat:
                    old_name = cat.name
                    dup = Category.query.filter(
                        Category.name == cat_name, Category.id != cat.id).first()
                    if dup:
                        flash('該種類名稱已存在！', 'error')
                    else:
                        cat.name = cat_name
                        Project.query.filter_by(category=old_name).update({'category': cat_name})
                        db.session.commit()
                        log_action(request.remote_addr, '編輯專案種類', f'{old_name} → {cat_name}')
                        flash('✅ 專案種類已更新！', 'success')
            elif action == 'delete' and cat_id:
                cat = Category.query.get(cat_id)
                if cat:
                    name = cat.name
                    db.session.delete(cat)
                    db.session.commit()
                    log_action(request.remote_addr, '刪除專案種類', name)
                    flash('✅ 專案種類已刪除！', 'success')

            return redirect(url_for('manage_categories'))

        categories = Category.query.order_by(Category.name).all()
        return render_template('manage_categories.html', categories=categories,
                               back_url=compute_back_url('manage_db'))