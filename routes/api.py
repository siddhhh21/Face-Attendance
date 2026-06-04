"""
API Blueprint - Face Recognition & Data Endpoints
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required
import json, logging
from datetime import date

from models.student import Student
from models.attendance import Attendance
from extensions import db
from utils.face_engine import (
    decode_image, detect_faces, extract_face_embedding,
    match_face, frame_to_thumbnail
)
from utils.attendance_service import (
    mark_attendance, get_attendance_report, get_dashboard_stats
)

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)

# ─── In-memory student embedding cache ───────────────────────────────────────
_student_cache = None
_cache_timestamp = None


def _get_student_embeddings():
    """Load all student embeddings from DB (cached)."""
    global _student_cache, _cache_timestamp
    from datetime import datetime
    now = datetime.utcnow()
    if _student_cache is None or (_cache_timestamp and (now - _cache_timestamp).seconds > 60):
        students = Student.query.filter_by(is_active=True).all()
        _student_cache = []
        for s in students:
            embs = s.get_embeddings()
            if embs:
                _student_cache.append({
                    'id': s.id,
                    'name': s.name,
                    'roll_number': s.roll_number,
                    'department': s.department,
                    'embeddings': embs
                })
        _cache_timestamp = now
    return _student_cache


def _invalidate_cache():
    global _student_cache
    _student_cache = None


# ─── Face Recognition Endpoint ────────────────────────────────────────────────

@api_bp.route('/recognize', methods=['POST'])
def recognize():
    """
    Receive a base64 frame, detect & recognize faces.
    Returns detection results and auto-marks attendance on match.
    """
    data = request.get_json()
    if not data or 'frame' not in data:
        return jsonify({'error': 'No frame data'}), 400

    frame = decode_image(data['frame'])
    if frame is None:
        return jsonify({'error': 'Failed to decode image'}), 400

    faces = detect_faces(frame)
    results = []

    students_data = _get_student_embeddings()

    for face_box in faces:
        embedding = extract_face_embedding(frame, tuple(face_box))
        x, y, w, h = face_box
        face_result = {
            'bbox': {'x': x, 'y': y, 'w': w, 'h': h},
            'matched': False,
            'name': 'Unknown',
            'roll_number': '',
            'department': '',
            'confidence': 0.0,
            'attendance_marked': False,
            'attendance_message': ''
        }

        if embedding and students_data:
            match = match_face(embedding, students_data, threshold=0.72)
            if match:
                student_info = match['student']
                confidence = match['confidence']
                face_result.update({
                    'matched': True,
                    'name': student_info['name'],
                    'roll_number': student_info['roll_number'],
                    'department': student_info['department'],
                    'confidence': round(confidence, 4),
                    'student_id': student_info['id']
                })

                # Auto-mark attendance
                att_result = mark_attendance(
                    student_id=student_info['id'],
                    confidence=confidence
                )
                face_result['attendance_marked'] = att_result['success']
                face_result['attendance_message'] = att_result['message']

        results.append(face_result)

    return jsonify({
        'faces_detected': len(faces),
        'results': results
    })


# ─── Student Registration ─────────────────────────────────────────────────────

@api_bp.route('/students/register', methods=['POST'])
@login_required
def register_student():
    """Register a new student with face embeddings."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    name = data.get('name', '').strip()
    roll_number = data.get('roll_number', '').strip()
    department = data.get('department', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    frames_b64 = data.get('frames', [])  # List of base64 image strings

    if not name or not roll_number or not department:
        return jsonify({'success': False, 'message': 'Name, Roll Number, and Department are required'}), 400

    if len(frames_b64) < 3:
        return jsonify({'success': False, 'message': 'Please capture at least 3 face images'}), 400

    # Check duplicate roll number
    existing = Student.query.filter_by(roll_number=roll_number).first()
    if existing:
        return jsonify({'success': False, 'message': f'Roll number {roll_number} already registered'}), 400

    # Generate embeddings from captured frames
    embeddings = []
    thumbnail_b64 = None
    frames_decoded = 0
    faces_found = 0

    for frame_data in frames_b64[:10]:
        frame = decode_image(frame_data)
        if frame is None:
            continue
        frames_decoded += 1

        faces = detect_faces(frame)

        if faces:
            faces_found += 1
            largest_face = max(faces, key=lambda f: f[2] * f[3])
            emb = extract_face_embedding(frame, tuple(largest_face))
            if emb:
                embeddings.append(emb)
                if thumbnail_b64 is None:
                    thumbnail_b64 = frame_to_thumbnail(frame)
        else:
            # Fallback: treat entire frame centre as face region and embed anyway
            # This handles cases where Haar cascade misses a valid face
            h, w = frame.shape[:2]
            margin_x, margin_y = int(w * 0.15), int(h * 0.1)
            centre_box = (margin_x, margin_y, w - 2*margin_x, h - 2*margin_y)
            emb = extract_face_embedding(frame, centre_box)
            if emb:
                embeddings.append(emb)
                if thumbnail_b64 is None:
                    thumbnail_b64 = frame_to_thumbnail(frame)

    if len(embeddings) < 1:
        return jsonify({
            'success': False,
            'message': f'Could not extract face features from images (decoded={frames_decoded}, faces_detected={faces_found}). Try better lighting and face the camera directly.'
        }), 400

    try:
        student = Student(
            name=name,
            roll_number=roll_number,
            department=department,
            email=email if email else None,
            phone=phone if phone else None,
            face_image_b64=thumbnail_b64
        )
        student.set_embeddings(embeddings)
        db.session.add(student)
        db.session.commit()
        _invalidate_cache()

        return jsonify({
            'success': True,
            'message': f'Student {name} registered successfully with {len(embeddings)} face samples',
            'student': student.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Register student error: {e}")
        return jsonify({'success': False, 'message': 'Database error: ' + str(e)}), 500


# ─── Data API ─────────────────────────────────────────────────────────────────

@api_bp.route('/students', methods=['GET'])
@login_required
def list_students():
    students = Student.query.filter_by(is_active=True).order_by(Student.name).all()
    return jsonify({'students': [s.to_dict() for s in students]})


@api_bp.route('/students/<int:student_id>', methods=['DELETE'])
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_active = False
    db.session.commit()
    _invalidate_cache()
    return jsonify({'success': True})


@api_bp.route('/attendance', methods=['GET'])
@login_required
def get_attendance():
    filters = {}
    for key in ['date_from', 'date_to', 'department', 'roll_number']:
        val = request.args.get(key)
        if val:
            filters[key] = val
    records = get_attendance_report(filters)
    return jsonify({'records': records, 'count': len(records)})


@api_bp.route('/dashboard/stats', methods=['GET'])
@login_required
def dashboard_stats():
    stats = get_dashboard_stats()
    return jsonify(stats)


@api_bp.route('/students/<int:student_id>/update', methods=['POST'])
@login_required
def update_student_api(student_id):
    """Update student info and optionally re-register embeddings."""
    student = Student.query.get_or_404(student_id)
    data = request.get_json()

    student.name = data.get('name', student.name)
    student.roll_number = data.get('roll_number', student.roll_number)
    student.department = data.get('department', student.department)
    student.email = data.get('email', student.email)
    student.phone = data.get('phone', student.phone)

    frames_b64 = data.get('frames', [])
    if frames_b64:
        embeddings = []
        for frame_data in frames_b64[:10]:
            frame = decode_image(frame_data)
            if frame is None: continue
            faces = detect_faces(frame)
            if faces:
                largest_face = max(faces, key=lambda f: f[2]*f[3])
                emb = extract_face_embedding(frame, tuple(largest_face))
            else:
                # Fallback: use centre region of frame
                h, w = frame.shape[:2]
                mx, my = int(w*0.15), int(h*0.1)
                emb = extract_face_embedding(frame, (mx, my, w-2*mx, h-2*my))
            if emb:
                embeddings.append(emb)
        if embeddings:
            student.set_embeddings(embeddings)
            frame = decode_image(frames_b64[0])
            if frame is not None:
                student.face_image_b64 = frame_to_thumbnail(frame)

    try:
        db.session.commit()
        _invalidate_cache()
        return jsonify({'success': True, 'message': 'Student updated', 'student': student.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ─── Email Routes ─────────────────────────────────────────────────────────────

@api_bp.route('/email/send-absences', methods=['POST'])
@login_required
def send_absence_emails_route():
    """Send absence emails to all students who didn't attend today."""
    from utils.email_service import send_absence_emails
    from models.student import Student
    from models.attendance import Attendance
    from datetime import date

    today = date.today()
    # Get all active students
    all_students = Student.query.filter_by(is_active=True).all()
    # Get IDs of students present today
    present_ids = {r.student_id for r in Attendance.query.filter_by(date=today).all()}
    # Filter absent students
    absent_students = [s for s in all_students if s.id not in present_ids]

    if not absent_students:
        return jsonify({'success': True, 'message': 'No absent students today!',
                        'sent': [], 'failed': [], 'no_email': []})

    result = send_absence_emails(absent_students)
    return jsonify({
        'success': True,
        'absent_count': len(absent_students),
        'sent_count': len(result['sent']),
        'failed_count': len(result['failed']),
        'no_email_count': len(result['no_email']),
        'sent': result['sent'],
        'failed': result['failed'],
        'no_email': result['no_email'],
        'message': f"Emails sent: {len(result['sent'])}, Failed: {len(result['failed'])}, No email on file: {len(result['no_email'])}"
    })


@api_bp.route('/email/status', methods=['GET'])
@login_required
def email_status_route():
    """Check if absence emails were sent today."""
    from utils.email_service import get_email_status
    from models.student import Student
    from models.attendance import Attendance
    from datetime import date

    today = date.today()
    status = get_email_status()

    all_students = Student.query.filter_by(is_active=True).count()
    present_ids = {r.student_id for r in Attendance.query.filter_by(date=today).all()}
    absent_count = all_students - len(present_ids)

    return jsonify({
        'emails_sent_today': bool(status.get('timestamp')),
        'sent_at': status.get('timestamp'),
        'sent': status.get('sent', []),
        'failed': status.get('failed', []),
        'no_email': status.get('no_email', []),
        'absent_count': absent_count,
        'date': today.strftime('%Y-%m-%d')
    })


@api_bp.route('/email/send-manual', methods=['POST'])
@login_required
def send_manual_email_route():
    """Send absence email to a specific student by roll number."""
    from utils.email_service import send_manual_absence_email
    from models.student import Student

    data = request.get_json()
    roll_number = (data.get('roll_number') or '').strip()
    if not roll_number:
        return jsonify({'success': False, 'message': 'Roll number is required'}), 400

    student = Student.query.filter(
        Student.roll_number.ilike(roll_number),
        Student.is_active == True
    ).first()

    if not student:
        return jsonify({'success': False, 'message': f'No student found with roll number: {roll_number}'}), 404

    result = send_manual_absence_email(student)
    return jsonify(result)
