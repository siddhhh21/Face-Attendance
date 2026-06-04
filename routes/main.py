"""
Main Blueprint - Student Portal (Landing Page)
"""
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Student portal - main landing page with live face recognition."""
    return render_template('student/index.html')
