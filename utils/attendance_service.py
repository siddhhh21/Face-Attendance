"""
Attendance Service - Business logic for attendance marking
"""
from datetime import datetime, date, timedelta
from extensions import db
from models.attendance import Attendance
from models.student import Student
import csv
import io
import logging
import threading

logger = logging.getLogger(__name__)


def _send_email_async(app, student, record):
    """Send email in background thread so it doesn't block the response."""
    from utils.email_service import send_attendance_email
    with app.app_context():
        send_attendance_email(
            student_name=student.name,
            roll_number=student.roll_number,
            department=student.department,
            student_email=student.email,
            time_str=record.time.strftime('%H:%M:%S'),
            confidence=record.confidence_score,
            status=record.status
        )

logger = logging.getLogger(__name__)


def mark_attendance(student_id: int, confidence: float,
                    marked_by: str = 'System',
                    reason: str = None,
                    status: str = 'Present') -> dict:
    """
    Mark attendance for a student with duplicate prevention.
    Returns: {'success': bool, 'message': str, 'record': dict or None}
    """
    today = date.today()
    now = datetime.now()

    # Check duplicate for today (same student, same day)
    existing = Attendance.query.filter_by(
        student_id=student_id,
        date=today
    ).first()

    if existing and status != 'Manual':
        return {
            'success': False,
            'message': f'Attendance already marked at {existing.time.strftime("%H:%M")}',
            'record': existing.to_dict()
        }

    try:
        record = Attendance(
            student_id=student_id,
            date=today,
            time=now.time(),
            status=status,
            confidence_score=confidence,
            marked_by=marked_by,
            reason=reason
        )
        db.session.add(record)
        db.session.commit()

        logger.info(f"Attendance marked: student_id={student_id}, status={status}")

        # Send email notification in background (non-blocking)
        student = Student.query.get(student_id)
        if student and student.email:
            from flask import current_app
            app = current_app._get_current_object()
            thread = threading.Thread(
                target=_send_email_async,
                args=(app, student, record),
                daemon=True
            )
            thread.start()

        return {
            'success': True,
            'message': 'Attendance marked successfully',
            'record': record.to_dict()
        }
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marking attendance: {e}")
        return {
            'success': False,
            'message': 'Database error while marking attendance',
            'record': None
        }


def get_attendance_report(filters: dict = None) -> list:
    """
    Get attendance records with optional filters.
    Filters: date_from, date_to, department, roll_number, student_id
    """
    query = Attendance.query.join(Student)

    if filters:
        if filters.get('date_from'):
            query = query.filter(Attendance.date >= filters['date_from'])
        if filters.get('date_to'):
            query = query.filter(Attendance.date <= filters['date_to'])
        if filters.get('department'):
            query = query.filter(Student.department == filters['department'])
        if filters.get('roll_number'):
            query = query.filter(Student.roll_number.ilike(f"%{filters['roll_number']}%"))
        if filters.get('student_id'):
            query = query.filter(Attendance.student_id == filters['student_id'])

    records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
    return [r.to_dict() for r in records]


def export_attendance_csv(filters: dict = None) -> str:
    """Export attendance records as CSV string."""
    records = get_attendance_report(filters)

    output = io.StringIO()
    fieldnames = ['ID', 'Name', 'Roll Number', 'Department', 'Date', 'Time',
                  'Status', 'Confidence %', 'Marked By', 'Reason']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for r in records:
        writer.writerow({
            'ID': r['id'],
            'Name': r['student_name'],
            'Roll Number': r['roll_number'],
            'Department': r['department'],
            'Date': r['date'],
            'Time': r['time'],
            'Status': r['status'],
            'Confidence %': r['confidence_score'] or 'N/A',
            'Marked By': r['marked_by'],
            'Reason': r['reason'] or ''
        })

    return output.getvalue()


def get_dashboard_stats() -> dict:
    """Get summary statistics for admin dashboard."""
    today = date.today()
    total_students = Student.query.filter_by(is_active=True).count()
    today_count = Attendance.query.filter_by(date=today).count()

    # Last 7 days attendance trend
    trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = Attendance.query.filter_by(date=d).count()
        trend.append({'date': d.strftime('%b %d'), 'count': count})

    attendance_pct = round((today_count / total_students * 100), 1) if total_students > 0 else 0

    # Department-wise stats
    dept_stats = db.session.execute(
        db.text("""
            SELECT s.department, COUNT(a.id) as count
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.date = :today
            GROUP BY s.department
        """), {'today': today}
    ).fetchall()

    return {
        'total_students': total_students,
        'today_count': today_count,
        'attendance_pct': attendance_pct,
        'trend': trend,
        'dept_stats': [{'dept': row[0], 'count': row[1]} for row in dept_stats]
    }
