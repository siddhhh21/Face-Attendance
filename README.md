# 🎯 FaceAttend Pro
### Real-Time Facial Recognition Attendance System
> Final Year Engineering Project | Industry-Level AI Web Application

---

## 🚀 Quick Start (5 Minutes)

```bash
# 1. Navigate to project
cd face_attendance

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python app.py
```

Open your browser: **http://localhost:5000**

---

## 🔐 Admin Credentials

| Field    | Value   |
|----------|---------|
| Username | `siddhh` |
| Password | `2101`  |

Admin Portal: **http://localhost:5000/admin/login**

---

## 📁 Project Structure

```
face_attendance/
├── app.py                  ← Flask app factory & entry point
├── config.py               ← Configuration (DB, thresholds, etc.)
├── extensions.py           ← Flask extensions (db, login_manager)
├── requirements.txt        ← Python dependencies
│
├── models/                 ← Database models
│   ├── student.py          ← Student model (embeddings stored as JSON)
│   ├── attendance.py       ← Attendance model
│   └── admin.py            ← Admin model + Flask-Login loader
│
├── routes/                 ← Flask blueprints
│   ├── main.py             ← Student portal routes
│   ├── admin.py            ← Admin dashboard routes
│   └── api.py              ← REST API (face recognition, data)
│
├── utils/                  ← Business logic
│   ├── face_engine.py      ← Face detection + embedding + matching
│   └── attendance_service.py ← Attendance logic + CSV export
│
└── templates/              ← Jinja2 HTML templates
    ├── base.html           ← Base layout (navbar, styles, toasts)
    ├── student/
    │   └── index.html      ← Live face recognition portal
    └── admin/
        ├── login.html      ← Admin authentication
        ├── dashboard.html  ← Stats + charts + recent activity
        ├── students.html   ← Student list + search/filter
        ├── add_student.html ← Register student + webcam capture
        ├── edit_student.html ← Edit student info
        ├── attendance.html  ← Attendance report + filters
        └── manual_attendance.html ← Manual marking
```

---

## 🗄️ Database Schema

### SQLite (default, zero-config) → MySQL (production)

```sql
-- Students table
CREATE TABLE students (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    roll_number VARCHAR(50)  UNIQUE NOT NULL,
    department  VARCHAR(100) NOT NULL,
    email       VARCHAR(120),
    phone       VARCHAR(20),
    embedding_json TEXT,        -- JSON array of face embedding vectors
    face_image_b64 TEXT,        -- Base64 thumbnail (no raw images stored)
    registered_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active   BOOLEAN DEFAULT 1
);

-- Attendance table
CREATE TABLE attendance (
    id              INTEGER PRIMARY KEY,
    student_id      INTEGER REFERENCES students(id),
    date            DATE NOT NULL,
    time            TIME NOT NULL,
    status          VARCHAR(20) DEFAULT 'Present',  -- Present / Manual
    confidence_score REAL,
    marked_by       VARCHAR(50) DEFAULT 'System',
    reason          VARCHAR(255),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Admins table
CREATE TABLE admins (
    id            INTEGER PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(100),
    last_login    DATETIME,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🧠 Face Recognition Pipeline

```
Camera Frame
    │
    ▼
[Haar Cascade] ──► Face Detection ──► Bounding Box (x,y,w,h)
    │
    ▼
[HOG + LBP Block Histograms] ──► 1024-dim Feature Vector
    │
    ▼
[Cosine Similarity] ──► Compare vs all stored embeddings
    │
    ├── Score ≥ 0.75 ──► MATCH → Mark Attendance
    └── Score < 0.75 ──► UNKNOWN
```

### Upgrading to DeepFace / FaceNet (Production)

Replace `extract_face_embedding()` in `utils/face_engine.py`:

```python
# Using DeepFace (most accurate, easiest)
from deepface import DeepFace

def extract_face_embedding(frame, face_box):
    embedding = DeepFace.represent(
        img_path=frame,
        model_name='Facenet512',    # or 'ArcFace', 'VGG-Face'
        detector_backend='mtcnn',
        enforce_detection=False
    )
    return embedding[0]['embedding']
```

Install: `pip install deepface mtcnn tensorflow`

---

## ⚙️ Configuration

Edit `config.py`:

```python
# MySQL Database
SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://user:password@localhost/faceattend'

# Recognition threshold (higher = stricter matching)
FACE_MATCH_THRESHOLD = 0.75

# Prevent marking same student twice per session
ATTENDANCE_COOLDOWN_HOURS = 8
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/recognize` | Submit frame → get face match results |
| POST | `/api/students/register` | Register new student with face data |
| GET  | `/api/students` | List all students |
| GET  | `/api/attendance` | Get attendance with filters |
| GET  | `/api/dashboard/stats` | Dashboard statistics |

---

## 🌟 Features

- ✅ **Real-time face detection** via OpenCV Haar Cascade
- ✅ **Automatic attendance marking** with duplicate prevention
- ✅ **Admin portal** with full CRUD operations
- ✅ **Student registration** with webcam capture (5-10 samples)
- ✅ **Attendance reports** with multi-filter (date, department, roll)
- ✅ **CSV export** for attendance and full database
- ✅ **Manual attendance** with reason logging
- ✅ **7-day trend chart** on admin dashboard
- ✅ **Dark futuristic UI** with animated HUD overlays
- ✅ **SQLite by default** → MySQL-ready for production
- ✅ **Modular Flask blueprint** architecture

---

## 🚀 Production Deployment

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

With Nginx reverse proxy for production use.

---

## 📝 Notes

- The default face recognition uses OpenCV + HOG features for **zero-dependency** demo.
- For **higher accuracy** (95%+), swap to DeepFace/FaceNet (see above).
- Raw images are **never stored** — only mathematical embeddings.
- Attendance is **prevented from double-marking** on the same day.

---

*Built with ❤️ | Flask + OpenCV + SQLAlchemy*
