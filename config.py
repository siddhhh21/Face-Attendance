"""
Configuration settings for FaceAttend Pro
"""
import os
from datetime import timedelta

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'face-attend-secret-key-2024-ultra-secure')
    DEBUG = os.environ.get('DEBUG', 'True') == 'True'

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///faceattend.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True

    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

    # Face recognition
    FACE_MATCH_THRESHOLD = 0.75
    MIN_FACE_IMAGES = 3
    MAX_FACE_IMAGES = 10
    EMBEDDING_MODEL = 'opencv'

    # Anti-spoofing
    LIVENESS_CHECK = True
    BLINK_FRAMES_REQUIRED = 2

    # Attendance
    ATTENDANCE_COOLDOWN_HOURS = 8

    # ─── Email Notifications ─────────────────────────────────────────────────
    # Gmail requires a 16-character App Password (NOT your login password).
    # Steps to generate one:
    #   1. Go to your Google Account → Security → 2-Step Verification (must be ON)
    #   2. Search "App passwords" → Select app: Mail, device: Other → Generate
    #   3. Copy the 16-char code (e.g. "abcd efgh ijkl mnop") — spaces are fine
    #   4. Set env var:  MAIL_APP_PASSWORD=abcdefghijklmnop
    #      OR paste it directly as MAIL_SENDER_PASSWORD below (no spaces).
    # ─────────────────────────────────────────────────────────────────────────
    MAIL_ENABLED = os.environ.get('MAIL_ENABLED', 'True') == 'True'
    MAIL_SMTP_HOST = 'smtp.gmail.com'
    MAIL_SMTP_PORT = 587
    MAIL_SENDER_EMAIL = os.environ.get('MAIL_SENDER_EMAIL', 'quadsquad3467@gmail.com')
    # IMPORTANT: Must be a Gmail App Password (16 chars), NOT your Gmail login password.
    MAIL_SENDER_PASSWORD = os.environ.get('MAIL_APP_PASSWORD', 'nsib qzyh oydz hnqp')
    MAIL_SENDER_NAME = 'FaceAttend Pro'

    # Paths
    HAARCASCADE_PATH = os.path.join(
        os.path.dirname(__file__), 'models', 'haarcascade_frontalface_default.xml'
    )
    EYE_CASCADE_PATH = os.path.join(
        os.path.dirname(__file__), 'models', 'haarcascade_eye.xml'
    )

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///faceattend_prod.db')
