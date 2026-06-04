"""
Attendance Model
"""
from extensions import db
from datetime import datetime, date

class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='Present')  # Present, Manual, Late
    confidence_score = db.Column(db.Float, nullable=True)
    marked_by = db.Column(db.String(50), default='System')  # 'System' or admin username
    reason = db.Column(db.String(255), nullable=True)       # For manual attendance
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else 'Unknown',
            'roll_number': self.student.roll_number if self.student else '',
            'department': self.student.department if self.student else '',
            'date': self.date.strftime('%Y-%m-%d'),
            'time': self.time.strftime('%H:%M:%S'),
            'status': self.status,
            'confidence_score': round(self.confidence_score * 100, 2) if self.confidence_score else None,
            'marked_by': self.marked_by,
            'reason': self.reason
        }

    def __repr__(self):
        return f'<Attendance {self.student_id} on {self.date}>'
