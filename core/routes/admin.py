import csv
import io
import os
import shutil
from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, session, send_file, Response
from openpyxl import Workbook, load_workbook
from ..extensions import db
from ..models import Project, Task, Personnel, Representative, Category
from ..helpers import (backup_database, ensure_task_columns, ensure_people_columns,
                       parse_resigned_date, BACKUP_KEEP)
from ..activity_log import log_action


def _require_auth():
    """Return a redirect if the admin session is not authenticated, else None."""
    if not session.get('db_admin_auth'):
        return redirect(url_for('manage_db_login'))
    return None


def register(app):
    DB_ADMIN_PASSWORD = app.config['DB_ADMIN_PASSWORD']

    # ── Auth ──────────────────────────────────────────────────────────────────

    @app.route('/manage-db-login', methods=['GET', 'POST'])
    def manage_db_login():
        if request.method == 'POST':
            if request.form.get('password', '') == DB_ADMIN_PASSWORD:
                session['db_admin_auth'] = True
                log_action(request.remote_addr, '管理者登入成功')
                return redirect(url_for('manage_db'))
            log_action(request.remote_addr, '管理者登入失敗（密碼錯誤）')
            flash('密碼錯誤，請重新輸入', 'error')
            return redirect(url_for('manage_db_login'))
        return render_template('manage_db_login.html')

    @app.route('/manage-db')
    def manage_db():
        if not session.get('db_admin_auth'):
            return redirect(url_for('manage_db_login'))
        projects = Project.query.order_by(Project.id.desc()).all()
        tasks = Task.query.order_by(Task.id.desc()).all()
        reps = Representative.query.order_by(Representative.name).all()
        personnel_list = Personnel.query.order_by(Personnel.name).all()
        categories = Category.query.order_by(Category.name).all()
        return render_template('manage_db.html', projects=projects, tasks=tasks,
                               reps=reps, personnel=personnel_list, categories=categories)

    # ── Backup / Restore ──────────────────────────────────────────────────────

    @app.route('/api/backup-download')
    def backup_download():
        guard = _require_auth()
        if guard:
            return guard
        db_file_path = app.config['DB_FILE_PATH']
        if not os.path.exists(db_file_path):
            flash('找不到資料庫檔案', 'error')
            return redirect(url_for('manage_db'))
        download_name = f"app_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        return send_file(db_file_path, as_attachment=True, download_name=download_name)

    @app.route('/api/backup-now', methods=['POST'])
    def backup_now():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))
        path = backup_database(reason='manual')
        if path:
            log_action(request.remote_addr, '手動備份資料庫', os.path.basename(path))
            flash(f'✅ 已建立備份：{os.path.basename(path)}（最多保留 {BACKUP_KEEP} 份）', 'success')
        else:
            flash('備份失敗，找不到資料庫檔案', 'error')
        return redirect(url_for('manage_db'))

    @app.route('/api/backup-restore', methods=['POST'])
    def backup_restore():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))

        file = request.files.get('db_file')
        if not file or file.filename == '':
            flash('請選擇備份檔案 (.db)', 'error')
            return redirect(url_for('manage_db'))
        if not file.filename.lower().endswith('.db'):
            flash('檔案格式錯誤，請上傳 .db 備份檔', 'error')
            return redirect(url_for('manage_db'))

        header = file.read(16)
        file.seek(0)
        if not header.startswith(b'SQLite format 3'):
            flash('這不是有效的 SQLite 資料庫檔案', 'error')
            return redirect(url_for('manage_db'))

        backup_database(reason='pre_restore')
        db_file_path = app.config['DB_FILE_PATH']
        try:
            db.session.remove()
            db.engine.dispose()
            tmp_path = db_file_path + '.incoming'
            file.save(tmp_path)
            shutil.move(tmp_path, db_file_path)
            ensure_task_columns()
            ensure_people_columns()
            log_action(request.remote_addr, '還原資料庫', f'file={file.filename}')
            flash('✅ 已從備份還原資料庫！（還原前的資料已另存為 pre_restore 備份）', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'還原失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))

    # ── CSV helpers ───────────────────────────────────────────────────────────

    def _csv_response(rows, headers, filename):
        output = io.StringIO()
        output.write('﻿')
        writer = csv.writer(output)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
        return Response(output.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment;filename={filename}'})

    def _read_csv(file):
        """Decode an uploaded CSV. Excel on zh-TW Windows writes CP950/BIG5,
        so fall back to it before giving up."""
        raw = file.read()
        for enc in ('utf-8-sig', 'cp950', 'big5'):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            content = raw.decode('utf-8', errors='replace')
        return csv.DictReader(io.StringIO(content))

    # ── Full DB export (single .xlsx, one sheet per table) ──────────────────────

    @app.route('/api/export-all')
    def export_all():
        guard = _require_auth()
        if guard:
            return guard

        projects = Project.query.order_by(Project.start_date.desc()).all()
        tasks = Task.query.order_by(Task.id).all()
        reps = Representative.query.order_by(Representative.name).all()
        personnel = Personnel.query.order_by(Personnel.name).all()
        categories = Category.query.order_by(Category.name).all()

        wb = Workbook()
        wb.remove(wb.active)

        def _sheet(title, headers, rows):
            ws = wb.create_sheet(title)
            ws.append(headers)
            for row in rows:
                ws.append(row)

        _sheet('專案', ['專案名稱', '狀態', '業務代表', '設備', '專案種類', '內容敘述', '起始日', '結束日', '參與人員', '備註'],
               [[p.name, p.status, p.rep, p.equipment, p.category, p.description,
                 p.start_date.strftime('%Y/%m/%d') if p.start_date else '',
                 p.end_date.strftime('%Y/%m/%d') if p.end_date else '',
                 ', '.join(set(t.personnel for t in p.tasks)), p.notes] for p in projects])

        _sheet('工作紀錄', ['所屬專案', '人員', '日期', '工作天數', '日班時數', '加班時數', '夜班時數', '工作描述', '備註'],
               [[t.project.name if t.project else '', t.personnel,
                 t.date.strftime('%Y/%m/%d') if t.date else '', t.work_days,
                 t.day_hours if t.day_hours is not None else '',
                 t.overtime_hours if t.overtime_hours is not None else '',
                 t.night_hours if t.night_hours is not None else '',
                 t.description, t.notes or ''] for t in tasks])

        _sheet('業務代表', ['名稱', '離職日期'],
               [[r.name, r.resigned_date.isoformat() if r.resigned_date else ''] for r in reps])
        _sheet('參與人員', ['系統代號', '顯示名稱', '離職日期'],
               [[p.name, p.display_name or '', p.resigned_date.isoformat() if p.resigned_date else '']
                for p in personnel])
        _sheet('專案種類', ['種類名稱'], [[c.name] for c in categories])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f"proj-dashboard-export-{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(buf, as_attachment=True, download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/api/import-all', methods=['POST'])
    def import_all():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))

        file = request.files.get('xlsx_file')
        if not file or file.filename == '':
            flash('請選擇 Excel 檔案 (.xlsx)', 'error')
            return redirect(url_for('manage_db'))
        if not file.filename.lower().endswith('.xlsx'):
            flash('檔案格式錯誤，請上傳「全部匯出」產生的 .xlsx 檔', 'error')
            return redirect(url_for('manage_db'))

        mode = request.form.get('import_mode', 'skip')
        wipe_before_import = request.form.get('wipe_before_import') == '1'

        try:
            wb = load_workbook(file, data_only=True)
        except Exception as e:
            flash(f'無法讀取 Excel 檔案：{str(e)}', 'error')
            return redirect(url_for('manage_db'))

        def _sheet_rows(title):
            if title not in wb.sheetnames:
                return []
            rows = list(wb[title].iter_rows(values_only=True))
            if not rows:
                return []
            headers = [str(h).strip() if h is not None else '' for h in rows[0]]
            result = []
            for row in rows[1:]:
                if row is None or all(c is None for c in row):
                    continue
                result.append({headers[i]: ('' if row[i] is None else str(row[i]).strip())
                               for i in range(len(headers)) if i < len(row)})
            return result

        def _opt_float(s):
            s = (s or '').strip()
            try:
                return float(s) if s else None
            except ValueError:
                return None

        try:
            if wipe_before_import:
                backup_database(reason='pre_full_wipe')
                Task.query.delete()
                Project.query.delete()
                Representative.query.delete()
                Personnel.query.delete()
                Category.query.delete()
                db.session.commit()
                log_action(request.remote_addr, '全部匯入前清空整個資料庫')

            counts = {}
            errors = []

            # 1. Representatives
            n_add = n_skip = 0
            for row in _sheet_rows('業務代表'):
                name = row.get('名稱', '').strip()
                if not name:
                    continue
                resigned_date = parse_resigned_date(row.get('離職日期'))
                existing = Representative.query.filter_by(name=name).first()
                if existing:
                    if mode == 'overwrite' and '離職日期' in row:
                        existing.resigned_date = resigned_date
                        n_add += 1
                    else:
                        n_skip += 1
                else:
                    db.session.add(Representative(name=name, resigned_date=resigned_date))
                    n_add += 1
            db.session.commit()
            counts['業務代表'] = (n_add, n_skip)

            # 2. Categories
            n_add = n_skip = 0
            for row in _sheet_rows('專案種類'):
                name = row.get('種類名稱', '').strip()
                if not name:
                    continue
                if Category.query.filter_by(name=name).first():
                    n_skip += 1
                else:
                    db.session.add(Category(name=name))
                    n_add += 1
            db.session.commit()
            counts['專案種類'] = (n_add, n_skip)

            # 3. Personnel
            n_add = n_skip = 0
            for row in _sheet_rows('參與人員'):
                name = row.get('系統代號', '').strip()
                if not name:
                    continue
                display_name = row.get('顯示名稱', '').strip() or None
                resigned_date = parse_resigned_date(row.get('離職日期'))
                existing = Personnel.query.filter_by(name=name).first()
                if existing:
                    if mode == 'overwrite':
                        existing.display_name = display_name
                        if '離職日期' in row:
                            existing.resigned_date = resigned_date
                        n_add += 1
                    else:
                        n_skip += 1
                else:
                    db.session.add(Personnel(name=name, display_name=display_name,
                                             resigned_date=resigned_date))
                    n_add += 1
            db.session.commit()
            counts['參與人員'] = (n_add, n_skip)

            # 4. Projects
            n_add = n_skip = 0
            for i, row in enumerate(_sheet_rows('專案'), start=2):
                name = row.get('專案名稱', '').strip()
                if not name:
                    continue
                status = row.get('狀態', '').strip()
                rep = row.get('業務代表', '').strip()
                equipment = row.get('設備', '').strip() or None
                category = row.get('專案種類', '').strip()
                description = row.get('內容敘述', '').strip() or None
                notes = row.get('備註', '').strip() or None
                start_str = row.get('起始日', '').strip()
                end_str = row.get('結束日', '').strip()

                try:
                    start_date = datetime.strptime(start_str, '%Y/%m/%d').date() if start_str else None
                    end_date = datetime.strptime(end_str, '%Y/%m/%d').date() if end_str else None
                except ValueError:
                    errors.append(f'專案表第 {i} 行「{name}」日期格式錯誤（需為 YYYY/MM/DD）')
                    continue

                if not start_date:
                    errors.append(f'專案表第 {i} 行「{name}」缺少起始日，已略過')
                    continue

                existing = Project.query.filter_by(name=name).first()
                if existing:
                    if mode == 'skip':
                        n_skip += 1
                        continue
                    existing.status = status
                    existing.rep = rep
                    existing.equipment = equipment
                    existing.category = category
                    existing.description = description
                    existing.start_date = start_date
                    existing.end_date = end_date
                    existing.notes = notes
                    n_add += 1
                else:
                    db.session.add(Project(name=name, status=status, rep=rep, equipment=equipment,
                                           category=category, description=description,
                                           start_date=start_date, end_date=end_date, notes=notes))
                    n_add += 1

                if rep and not Representative.query.filter_by(name=rep).first():
                    db.session.add(Representative(name=rep))
                if category and not Category.query.filter_by(name=category).first():
                    db.session.add(Category(name=category))
            db.session.commit()
            counts['專案'] = (n_add, n_skip)

            # 5. Tasks (must run after projects so project names resolve)
            n_add = n_skip = 0
            seen = set(
                (t.project_id, t.personnel, t.date, t.work_days, t.day_hours,
                 t.overtime_hours, t.night_hours, t.description, t.notes)
                for t in Task.query.all())
            for i, row in enumerate(_sheet_rows('工作紀錄'), start=2):
                proj_name = row.get('所屬專案', '').strip()
                personnel = row.get('人員', '').strip()
                description = row.get('工作描述', '').strip()
                notes = row.get('備註', '').strip() or None
                if not proj_name or not personnel or not description:
                    errors.append(f'工作紀錄表第 {i} 行缺少必填欄位，已略過')
                    continue
                project = Project.query.filter_by(name=proj_name).first()
                if not project:
                    errors.append(f'工作紀錄表第 {i} 行找不到專案「{proj_name}」，已略過')
                    continue
                date_str = row.get('日期', '').strip()
                work_days_s = row.get('工作天數', '').strip()
                try:
                    task_date = datetime.strptime(date_str, '%Y/%m/%d').date() if date_str else None
                    work_days = float(work_days_s) if work_days_s else 0.0
                except ValueError:
                    errors.append(f'工作紀錄表第 {i} 行日期或工作天數格式錯誤，已略過')
                    continue
                day_hours = _opt_float(row.get('日班時數', ''))
                overtime_hours = _opt_float(row.get('加班時數', ''))
                night_hours = _opt_float(row.get('夜班時數', ''))
                sig = (project.id, personnel, task_date, work_days, day_hours,
                       overtime_hours, night_hours, description, notes)
                if sig in seen:
                    n_skip += 1
                    continue
                seen.add(sig)
                db.session.add(Task(project_id=project.id, personnel=personnel, date=task_date,
                                    work_days=work_days, day_hours=day_hours,
                                    overtime_hours=overtime_hours, night_hours=night_hours,
                                    description=description, notes=notes))
                n_add += 1
            db.session.commit()
            counts['工作紀錄'] = (n_add, n_skip)

            summary = '、'.join(f'{k} +{v[0]}/略過{v[1]}' for k, v in counts.items())
            msg = f'✅ 全部匯入完成！{summary}'
            if errors:
                msg += f'（{len(errors)} 筆錯誤）'
            log_action(request.remote_addr, '全部匯入 Excel',
                       f'mode={mode}, wipe={wipe_before_import}, ' +
                       '; '.join(f'{k}={v[0]}/{v[1]}' for k, v in counts.items()))
            flash(msg, 'success')
            for err in errors[:5]:
                flash(err, 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'匯入失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))

    # ── Projects CSV ──────────────────────────────────────────────────────────

    @app.route('/api/export-db')
    def export_db():
        projects = Project.query.order_by(Project.start_date.desc()).all()
        rows = []
        for p in projects:
            task_personnel = ', '.join(set(t.personnel for t in p.tasks))
            rows.append([p.name, p.status, p.rep, p.equipment, p.category, p.description,
                         p.start_date.strftime('%Y/%m/%d') if p.start_date else '',
                         p.end_date.strftime('%Y/%m/%d') if p.end_date else '',
                         task_personnel, p.notes])
        return _csv_response(rows,
                             ['專案名稱', '狀態', '業務代表', '設備', '專案種類', '內容敘述', '起始日', '結束日', '參與人員', '備註'],
                             'projects_export.csv')

    @app.route('/api/import-db', methods=['POST'])
    def import_db():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))

        file = request.files.get('csv_file')
        if not file or file.filename == '':
            flash('請選擇 CSV 檔案', 'error')
            return redirect(url_for('manage_db'))

        mode = request.form.get('import_mode', 'skip')
        try:
            reader = _read_csv(file)
            imported = skipped = 0
            error_list = []

            for i, row in enumerate(reader, start=2):
                name = row.get('專案名稱', '').strip()
                if not name:
                    continue
                status = row.get('狀態', '').strip()
                rep = row.get('業務代表', '').strip()
                equipment = row.get('設備', '').strip() or None
                category = row.get('專案種類', '').strip()
                description = row.get('內容敘述', '').strip() or None
                notes = row.get('備註', '').strip() or None
                start_str = row.get('起始日', '').strip()
                end_str = row.get('結束日', '').strip()

                try:
                    start_date = datetime.strptime(start_str, '%Y/%m/%d').date() if start_str else None
                    end_date = datetime.strptime(end_str, '%Y/%m/%d').date() if end_str else None
                except ValueError:
                    error_list.append(f'第 {i} 行「{name}」日期格式錯誤（需為 YYYY/MM/DD）')
                    continue

                if not start_date:
                    error_list.append(f'第 {i} 行「{name}」缺少起始日，已略過')
                    continue

                existing = Project.query.filter_by(name=name).first()
                if existing:
                    if mode == 'skip':
                        skipped += 1
                        continue
                    existing.status = status
                    existing.rep = rep
                    existing.equipment = equipment
                    existing.category = category
                    existing.description = description
                    existing.start_date = start_date
                    existing.end_date = end_date
                    existing.notes = notes
                    imported += 1
                else:
                    db.session.add(Project(name=name, status=status, rep=rep, equipment=equipment,
                                           category=category, description=description,
                                           start_date=start_date, end_date=end_date, notes=notes))
                    imported += 1

                if rep and not Representative.query.filter_by(name=rep).first():
                    db.session.add(Representative(name=rep))
                if category and not Category.query.filter_by(name=category).first():
                    db.session.add(Category(name=category))

            db.session.commit()
            action_label = '更新' if mode == 'overwrite' else '新增'
            msg = f'✅ 匯入完成！{action_label} {imported} 筆，略過重複 {skipped} 筆。'
            if error_list:
                msg += f'（{len(error_list)} 筆錯誤）'
            log_action(request.remote_addr, '匯入專案 CSV',
                       f'mode={mode}, imported={imported}, skipped={skipped}')
            flash(msg, 'success')
            for err in error_list[:5]:
                flash(err, 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'匯入失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))

    # ── Tasks CSV ─────────────────────────────────────────────────────────────

    @app.route('/api/export-tasks')
    def export_tasks():
        guard = _require_auth()
        if guard:
            return guard
        tasks = Task.query.order_by(Task.id).all()
        rows = [[t.project.name if t.project else '', t.personnel,
                 t.date.strftime('%Y/%m/%d') if t.date else '', t.work_days,
                 t.day_hours if t.day_hours is not None else '',
                 t.overtime_hours if t.overtime_hours is not None else '',
                 t.night_hours if t.night_hours is not None else '',
                 t.description, t.notes or ''] for t in tasks]
        return _csv_response(rows,
                             ['所屬專案', '人員', '日期', '工作天數', '日班時數', '加班時數', '夜班時數', '工作描述', '備註'],
                             'tasks_export.csv')

    @app.route('/api/import-tasks', methods=['POST'])
    def import_tasks():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))

        file = request.files.get('csv_file')
        if not file or file.filename == '':
            flash('請選擇 CSV 檔案', 'error')
            return redirect(url_for('manage_db'))

        wipe_before_import = request.form.get('wipe_before_import') == '1'

        def _opt_hours(row, key):
            raw = row.get(key, '').strip()
            try:
                return float(raw) if raw else None
            except ValueError:
                return None

        try:
            if wipe_before_import:
                backup_database(reason='pre_task_wipe')
                deleted = Task.query.delete()
                db.session.commit()
                log_action(request.remote_addr, '匯入前清空工作紀錄', f'deleted={deleted}')

            reader = _read_csv(file)
            imported = skipped = 0
            error_list = []
            seen = set(
                (t.project_id, t.personnel, t.date, t.work_days, t.day_hours,
                 t.overtime_hours, t.night_hours, t.description, t.notes)
                for t in Task.query.all())
            for i, row in enumerate(reader, start=2):
                proj_name = row.get('所屬專案', '').strip()
                personnel = row.get('人員', '').strip()
                date_str = row.get('日期', '').strip()
                work_days_s = row.get('工作天數', '').strip()
                description = row.get('工作描述', '').strip()
                notes = row.get('備註', '').strip() or None
                if not proj_name or not personnel or not description:
                    error_list.append(f'第 {i} 行缺少必填欄位，已略過')
                    continue
                project = Project.query.filter_by(name=proj_name).first()
                if not project:
                    error_list.append(f'第 {i} 行找不到專案「{proj_name}」，已略過')
                    continue
                try:
                    task_date = datetime.strptime(date_str, '%Y/%m/%d').date() if date_str else None
                    work_days = float(work_days_s) if work_days_s else 0.0
                except ValueError:
                    error_list.append(f'第 {i} 行日期或工作天數格式錯誤，已略過')
                    continue
                day_hours = _opt_hours(row, '日班時數')
                overtime_hours = _opt_hours(row, '加班時數')
                night_hours = _opt_hours(row, '夜班時數')
                sig = (project.id, personnel, task_date, work_days, day_hours,
                       overtime_hours, night_hours, description, notes)
                if sig in seen:
                    skipped += 1
                    continue
                seen.add(sig)
                db.session.add(Task(project_id=project.id, personnel=personnel, date=task_date,
                                    work_days=work_days, day_hours=day_hours,
                                    overtime_hours=overtime_hours,
                                    night_hours=night_hours,
                                    description=description, notes=notes))
                imported += 1
            db.session.commit()
            msg = f'✅ 工作紀錄匯入完成！新增 {imported} 筆，略過重複 {skipped} 筆。'
            if error_list:
                msg += f'（{len(error_list)} 筆錯誤）'
            log_action(request.remote_addr, '匯入工時 CSV', f'imported={imported}, skipped={skipped}')
            flash(msg, 'success')
            for err in error_list[:5]:
                flash(err, 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'匯入失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))

    # ── Representatives CSV ───────────────────────────────────────────────────

    @app.route('/api/export-reps')
    def export_reps():
        guard = _require_auth()
        if guard:
            return guard
        reps = Representative.query.order_by(Representative.name).all()
        return _csv_response([[r.name, r.resigned_date.isoformat() if r.resigned_date else '']
                              for r in reps], ['名稱', '離職日期'], 'representatives_export.csv')

    @app.route('/api/import-reps', methods=['POST'])
    def import_reps():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))

        file = request.files.get('csv_file')
        if not file or file.filename == '':
            flash('請選擇 CSV 檔案', 'error')
            return redirect(url_for('manage_db'))
        try:
            mode = request.form.get('import_mode', 'skip')
            imported = skipped = 0
            for row in _read_csv(file):
                name = row.get('名稱', '').strip()
                if not name:
                    continue
                resigned_date = parse_resigned_date(row.get('離職日期'))
                existing = Representative.query.filter_by(name=name).first()
                if existing:
                    if mode == 'overwrite' and '離職日期' in row:
                        existing.resigned_date = resigned_date
                        imported += 1
                    else:
                        skipped += 1
                else:
                    db.session.add(Representative(name=name, resigned_date=resigned_date))
                    imported += 1
            db.session.commit()
            log_action(request.remote_addr, '匯入業務代表 CSV',
                       f'imported={imported}, skipped={skipped}')
            flash(f'✅ 業務代表匯入完成！新增/更新 {imported} 筆，略過重複 {skipped} 筆。', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'匯入失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))

    # ── Personnel CSV ─────────────────────────────────────────────────────────

    @app.route('/api/export-personnel')
    def export_personnel():
        guard = _require_auth()
        if guard:
            return guard
        personnel = Personnel.query.order_by(Personnel.name).all()
        return _csv_response([[p.name, p.display_name or '',
                               p.resigned_date.isoformat() if p.resigned_date else ''] for p in personnel],
                             ['系統代號', '顯示名稱', '離職日期'], 'personnel_export.csv')

    @app.route('/api/import-personnel', methods=['POST'])
    def import_personnel():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))

        file = request.files.get('csv_file')
        if not file or file.filename == '':
            flash('請選擇 CSV 檔案', 'error')
            return redirect(url_for('manage_db'))
        mode = request.form.get('import_mode', 'skip')
        try:
            imported = skipped = 0
            for row in _read_csv(file):
                name = row.get('系統代號', '').strip()
                display_name = row.get('顯示名稱', '').strip() or None
                if not name:
                    continue
                resigned_date = parse_resigned_date(row.get('離職日期'))
                existing = Personnel.query.filter_by(name=name).first()
                if existing:
                    if mode == 'overwrite':
                        existing.display_name = display_name
                        if '離職日期' in row:
                            existing.resigned_date = resigned_date
                        imported += 1
                    else:
                        skipped += 1
                else:
                    db.session.add(Personnel(name=name, display_name=display_name,
                                             resigned_date=resigned_date))
                    imported += 1
            db.session.commit()
            action_label = '新增/更新' if mode == 'overwrite' else '新增'
            log_action(request.remote_addr, '匯入人員 CSV',
                       f'mode={mode}, imported={imported}, skipped={skipped}')
            flash(f'✅ 參與人員匯入完成！{action_label} {imported} 筆，略過重複 {skipped} 筆。', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'匯入失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))

    # ── Categories CSV ────────────────────────────────────────────────────────

    @app.route('/api/export-categories')
    def export_categories():
        guard = _require_auth()
        if guard:
            return guard
        categories = Category.query.order_by(Category.name).all()
        return _csv_response([[c.name] for c in categories], ['種類名稱'], 'categories_export.csv')

    @app.route('/api/import-categories', methods=['POST'])
    def import_categories():
        guard = _require_auth()
        if guard:
            flash('未授權，請先登入', 'error')
            return redirect(url_for('manage_db_login'))

        file = request.files.get('csv_file')
        if not file or file.filename == '':
            flash('請選擇 CSV 檔案', 'error')
            return redirect(url_for('manage_db'))
        try:
            imported = skipped = 0
            for row in _read_csv(file):
                name = row.get('種類名稱', '').strip()
                if not name:
                    continue
                if Category.query.filter_by(name=name).first():
                    skipped += 1
                else:
                    db.session.add(Category(name=name))
                    imported += 1
            db.session.commit()
            log_action(request.remote_addr, '匯入專案種類 CSV',
                       f'imported={imported}, skipped={skipped}')
            flash(f'✅ 專案種類匯入完成！新增 {imported} 筆，略過重複 {skipped} 筆。', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'匯入失敗：{str(e)}', 'error')
        return redirect(url_for('manage_db'))
