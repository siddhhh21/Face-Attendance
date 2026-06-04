"""
Student Model
"""
from extensions import db
from datetime import datetime
import json

class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), unique=True, nullable=False)
    department = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    embedding_json = db.Column(db.Text, nullable=True)   # JSON array of embedding vectors
    face_image_b64 = db.Column(db.Text, nullable=True)   # Base64 thumbnail for display
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    attendance_records = db.relationship('Attendance', backref='student',
                                          lazy='dynamic', cascade='all, delete-orphan')

    def set_embeddings(self, embeddings_list):
        """Store list of embedding vectors as JSON."""
        self.embedding_json = json.dumps(embeddings_list)

    def get_embeddings(self):
        """Retrieve list of embedding vectors."""
        if self.embedding_json:
            return json.loads(self.embedding_json)
        return []

    @property
    def embedding_count(self):
        """Return number of stored face embeddings."""
        return len(self.get_embeddings())

    @property
    def face_available(self):
        """True only when 3 or more face captures are stored."""
        return self.embedding_count >= 3

    def to_dict(self):
        count = self.embedding_count
        return {
            'id': self.id,
            'name': self.name,
            'roll_number': self.roll_number,
            'department': self.department,
            'email': self.email,
            'phone': self.phone,
            'registered_at': self.registered_at.strftime('%Y-%m-%d %H:%M'),
            'is_active': self.is_active,
            'has_embedding': bool(self.embedding_json),
            'face_available': count >= 3,
            'embedding_count': count,
            'face_image': self.face_image_b64
        }

    def __repr__(self):
        return f'<Student {self.roll_number}: {self.name}>'
