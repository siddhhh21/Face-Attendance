"""
Admin Blueprint - Admin Portal
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, jsonify, send_file
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
import io

from models.admin import Admin
from models.student import Student
from models.attendance import Attendance
from extensions import db
from utils.attendance_service import (
    get_dashboard_stats, get_attendance_report,
    export_attendance_csv, mark_attendance
)

admin_bp = Blueprint('admin', __name__)


# ─── Auth ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        data = request.get_json() or request.form
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin, remember=True)
            admin.last_login = datetime.utcnow()
            db.session.commit()
            if request.is_json:
                return jsonify({'success': True, 'redirect': url_for('admin.dashboard')})
            return redirect(url_for('admin.dashboard'))

        if request.is_json:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        flash('Invalid credentials', 'danger')

    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    stats = get_dashboard_stats()
    return render_template('admin/dashboard.html', stats=stats)


# ─── Students ─────────────────────────────────────────────────────────────────

@admin_bp.route('/students')
@login_required
def students():
    all_students = Student.query.filter_by(is_active=True).order_by(Student.registered_at.desc()).all()
    return render_template('admin/students.html', students=all_students)


@admin_bp.route('/students/add')
@login_required
def add_student():
    return render_template('admin/add_student.html')


@admin_bp.route('/students/edit/<int:student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        data = request.get_json() or request.form
        student.name = data.get('name', student.name)
        student.roll_number = data.get('roll_number', student.roll_number)
        student.department = data.get('department', student.department)
        student.email = data.get('email', student.email)
        student.phone = data.get('phone', student.phone)
        try:
            db.session.commit()
            return jsonify({'success': True, 'message': 'Student updated successfully'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    return render_template('admin/edit_student.html', student=student)


@admin_bp.route('/students/delete/<int:student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    include_attendance = request.json.get('include_attendance', True)
    try:
        if not include_attendance:
            Attendance.query.filter_by(student_id=student_id).delete()
        student.is_active = False  # Soft delete
        db.session.commit()
        return jsonify({'success': True, 'message': f'Student {student.name} removed'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ─── Attendance ───────────────────────────────────────────────────────────────

@admin_bp.route('/attendance')
@login_required
def attendance():
    departments = db.session.execute(
        db.text("SELECT DISTINCT department FROM students WHERE is_active = 1")
    ).fetchall()
    dept_list = [r[0] for r in departments]
    return render_template('admin/attendance.html', departments=dept_list)


@admin_bp.route('/attendance/manual', methods=['GET', 'POST'])
@login_required
def manual_attendance():
    if request.method == 'POST':
        data = request.get_json()
        student_id = data.get('student_id')
        reason = data.get('reason', 'Official Duty')

        result = mark_attendance(
            student_id=student_id,
            confidence=1.0,
            marked_by=current_user.username,
            reason=reason,
            status='Manual'
        )
        return jsonify(result)

    students = Student.query.filter_by(is_active=True).order_by(Student.name).all()
    return render_template('admin/manual_attendance.html', students=students)


@admin_bp.route('/attendance/export')
@login_required
def export_attendance():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    department = request.args.get('department')
    roll_number = request.args.get('roll_number')

    filters = {}
    if date_from: filters['date_from'] = date_from
    if date_to: filters['date_to'] = date_to
    if department: filters['department'] = department
    if roll_number: filters['roll_number'] = roll_number

    csv_data = export_attendance_csv(filters)
    return send_file(
        io.BytesIO(csv_data.encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_report_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    )




# ─── Mail Parents ─────────────────────────────────────────────────────────────

@admin_bp.route('/mail-parents')
@login_required
def mail_parents():
    """Mail parents/guardian - absence notification page."""
    from models.attendance import Attendance
    from datetime import date as _date

    today = _date.today()
    all_students = Student.query.filter_by(is_active=True).order_by(Student.name).all()
    present_ids = {r.student_id for r in Attendance.query.filter_by(date=today).all()}
    absent_students = [s for s in all_students if s.id not in present_ids]
    no_email_count = sum(1 for s in absent_students if not s.email)

    stats = {
        'total_students': len(all_students),
        'present_today': len(present_ids),
        'absent_today': len(absent_students),
        'no_email_count': no_email_count,
    }

    from flask import current_app
    mail_configured = bool(current_app.config.get('MAIL_SENDER_PASSWORD', ''))
    return render_template('admin/mail_parents.html',
                           students=all_students,
                           absent_students=absent_students,
                           stats=stats,
                           mail_configured=mail_configured)

@admin_bp.route('/database/export')
@login_required
def export_database():
    """Export all students and attendance as CSV."""
    students = Student.query.all()
    output = io.StringIO()
    import csv
    writer = csv.writer(output)
    writer.writerow(['=== STUDENTS ==='])
    writer.writerow(['ID', 'Name', 'Roll No', 'Department', 'Email', 'Phone', 'Registered At', 'Active'])
    for s in students:
        writer.writerow([s.id, s.name, s.roll_number, s.department,
                         s.email or '', s.phone or '', s.registered_at, s.is_active])

    writer.writerow([])
    writer.writerow(['=== ATTENDANCE ==='])
    writer.writerow(['ID', 'Student ID', 'Name', 'Roll No', 'Date', 'Time', 'Status', 'Confidence', 'Marked By', 'Reason'])
    records = Attendance.query.all()
    for r in records:
        d = r.to_dict()
        writer.writerow([r.id, r.student_id, d['student_name'], d['roll_number'],
                         d['date'], d['time'], d['status'], d['confidence_score'],
                         d['marked_by'], d['reason']])

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'faceattend_database_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@admin_bp.route('/attendance/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_attendance(record_id):
    """Delete a single attendance record."""
    record = Attendance.query.get_or_404(record_id)
    try:
        student_name = record.student.name if record.student else 'Unknown'
        db.session.delete(record)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Attendance record for {student_name} on {record.date} removed'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
