"""
FaceAttend Pro - Real-Time Facial Recognition Attendance System
Main Flask Application Entry Point
"""

from flask import Flask
from config import Config
from extensions import db, login_manager
from routes.main import main_bp
from routes.admin import admin_bp
from routes.api import api_bp
import os

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login'

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')

    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
        _seed_admin(app)

    return app

def _seed_admin(app):
    """Create default admin account if not exists."""
    from models.admin import Admin
    from werkzeug.security import generate_password_hash
    with app.app_context():
        if not Admin.query.filter_by(username='siddhh').first():
            admin = Admin(
                username='siddhh',
                password_hash=generate_password_hash('2101'),
                full_name='Administrator'
            )
            db.session.add(admin)
            db.session.commit()

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
