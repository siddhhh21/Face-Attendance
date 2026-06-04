"""
Email Notification Service
Sends attendance confirmation and absence alert emails.
Uses Gmail SMTP with App Password (2FA required).
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
from flask import current_app

logger = logging.getLogger(__name__)


# ─── Track email send status per session (in-memory) ─────────────────────────
# Structure: { 'YYYY-MM-DD': {'sent': [roll_numbers], 'failed': [roll_numbers], 'timestamp': str} }
_email_log = {}


def get_email_status(for_date: str = None) -> dict:
    """Return today's (or specified date's) absence email status."""
    key = for_date or date.today().strftime('%Y-%m-%d')
    return _email_log.get(key, {'sent': [], 'failed': [], 'timestamp': None})


def send_attendance_email(student_name: str, roll_number: str,
                           department: str, student_email: str,
                           time_str: str, confidence: float,
                           status: str = 'Present') -> bool:
    """
    Send attendance confirmation email to a student.
    Returns True on success, False on failure.
    """
    if not current_app.config.get('MAIL_ENABLED'):
        return False
    if not student_email:
        logger.info(f"No email for student {roll_number}, skipping notification")
        return False

    try:
        subject, html_body = _build_present_email(
            student_name, roll_number, department, time_str, confidence, status
        )
        _send(student_email, subject, html_body)
        logger.info(f"Attendance email sent to {student_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {student_email}: {e}")
        return False


def send_absence_emails(absent_students: list) -> dict:
    """
    Send absence notification emails to a list of absent students.
    absent_students: list of Student model objects
    Returns: {'sent': [...], 'failed': [...], 'no_email': [...]}
    """
    sent, failed, no_email = [], [], []
    today_str = date.today().strftime('%Y-%m-%d')

    for student in absent_students:
        if not student.email:
            no_email.append(student.roll_number)
            continue
        try:
            subject, html_body = _build_absent_email(
                student.name, student.roll_number, student.department
            )
            _send(student.email, subject, html_body)
            sent.append(student.roll_number)
            logger.info(f"Absence email sent to {student.email}")
        except Exception as e:
            failed.append(student.roll_number)
            logger.error(f"Failed to send absence email to {student.email}: {e}")

    # Log the result
    _email_log[today_str] = {
        'sent': sent,
        'failed': failed,
        'no_email': no_email,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }

    return {'sent': sent, 'failed': failed, 'no_email': no_email}


def send_manual_absence_email(student) -> dict:
    """Send an absence email for a single student by roll number lookup."""
    if not student.email:
        return {'success': False, 'message': f'No email registered for {student.roll_number}'}
    try:
        subject, html_body = _build_absent_email(
            student.name, student.roll_number, student.department
        )
        _send(student.email, subject, html_body)
        return {'success': True, 'message': f'Absence email sent to {student.email}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def _send(to_email: str, subject: str, html_body: str):
    """Send email via SMTP with helpful error messages."""
    cfg = current_app.config

    sender_email = cfg.get('MAIL_SENDER_EMAIL', '')
    sender_password = cfg.get('MAIL_SENDER_PASSWORD', '')

    if not sender_password:
        raise Exception(
            "Email not configured: MAIL_APP_PASSWORD is empty. "
            "Generate a Gmail App Password at myaccount.google.com/apppasswords "
            "(2-Step Verification must be enabled), then set the env var MAIL_APP_PASSWORD."
        )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"{cfg['MAIL_SENDER_NAME']} <{sender_email}>"
    msg['To']      = to_email

    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(cfg['MAIL_SMTP_HOST'], cfg['MAIL_SMTP_PORT']) as server:
            server.ehlo()
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise Exception(
            "Gmail authentication failed (535 BadCredentials). "
            "Your password is WRONG — Gmail requires a 16-character App Password, "
            "NOT your normal Gmail login password. "
            "Go to myaccount.google.com/apppasswords, generate an App Password, "
            "and set MAIL_APP_PASSWORD env var to that 16-char code."
        )
    except smtplib.SMTPException as e:
        raise Exception(f"SMTP error: {e}")


def _build_present_email(name, roll, dept, time_str, confidence, status):
    """Build the HTML email for attendance marked (present/manual)."""
    today = datetime.now().strftime('%A, %d %B %Y')
    conf_pct = f"{round(confidence * 100, 1)}%" if confidence else "Manual"
    color = '#00ff88' if status == 'Present' else '#ffcc00'
    icon  = '✅' if status == 'Present' else '✍️'
    status_label = 'AUTO-DETECTED' if status == 'Present' else 'MANUALLY MARKED'

    subject = f"{icon} Attendance Marked – {name} | {today}"

    html = f"""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body{{margin:0;padding:0;background:#030711;font-family:'Segoe UI',Arial,sans-serif}}
  .wrapper{{max-width:520px;margin:30px auto;background:#070e1a;border:1px solid #0f2040;border-radius:12px;overflow:hidden}}
  .header{{background:linear-gradient(135deg,#001a33,#070e1a);padding:30px;text-align:center;border-bottom:1px solid #0f2040}}
  .logo{{font-size:13px;letter-spacing:4px;color:#00f5ff;font-weight:700;margin-bottom:6px}}
  .header h1{{color:#fff;font-size:20px;margin:0;font-weight:300;letter-spacing:1px}}
  .status-badge{{display:inline-block;background:rgba(0,255,136,0.1);border:1px solid {color};color:{color};padding:5px 18px;border-radius:20px;font-size:11px;letter-spacing:2px;margin-top:14px;font-weight:600}}
  .body{{padding:30px}}
  .greeting{{color:#a0c4d8;font-size:15px;margin-bottom:20px}}
  .info-card{{background:rgba(0,245,255,0.04);border:1px solid #0f2040;border-radius:8px;padding:20px;margin-bottom:20px}}
  .info-row{{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid #0f2040}}
  .info-row:last-child{{border-bottom:none}}
  .info-label{{color:#4a7090;font-size:11px;letter-spacing:1.5px;text-transform:uppercase}}
  .info-value{{color:#e0f4ff;font-size:14px;font-weight:600}}
  .info-value.hl{{color:{color}}}
  .conf-bar{{height:3px;background:#0f2040;border-radius:2px;margin-top:6px}}
  .conf-fill{{height:100%;width:{conf_pct};background:linear-gradient(90deg,#00f5ff,#00ff88);border-radius:2px}}
  .footer{{background:#030711;padding:16px 30px;text-align:center;border-top:1px solid #0f2040}}
  .footer p{{color:#2a4060;font-size:11px;margin:4px 0}}
  .note{{background:rgba(255,204,0,0.06);border-left:3px solid #ffcc00;padding:10px 14px;border-radius:4px;font-size:12px;color:#a09060;margin-top:16px}}
</style></head><body>
<div class="wrapper">
  <div class="header">
    <div class="logo">👁 FACEATTEND PRO</div>
    <h1>Attendance Confirmation</h1>
    <div class="status-badge">{icon} {status_label}</div>
  </div>
  <div class="body">
    <p class="greeting">Hello <strong style="color:#e0f4ff">{name}</strong>,<br>Your attendance has been successfully recorded for today.</p>
    <div class="info-card">
      <div class="info-row"><span class="info-label">Name</span><span class="info-value">{name}</span></div>
      <div class="info-row"><span class="info-label">Roll Number</span><span class="info-value">{roll}</span></div>
      <div class="info-row"><span class="info-label">Department</span><span class="info-value">{dept}</span></div>
      <div class="info-row"><span class="info-label">Date</span><span class="info-value">{today}</span></div>
      <div class="info-row"><span class="info-label">Time</span><span class="info-value hl">{time_str}</span></div>
      <div class="info-row"><span class="info-label">Status</span><span class="info-value hl">{status}</span></div>
      <div class="info-row">
        <span class="info-label">Match Confidence</span>
        <div><span class="info-value">{conf_pct}</span>
        <div class="conf-bar"><div class="conf-fill"></div></div></div>
      </div>
    </div>
    <div class="note">💡 If you did not attend today or believe this is an error, please contact your administrator immediately.</div>
  </div>
  <div class="footer">
    <p>This is an automated notification from FaceAttend Pro</p>
    <p>© {datetime.now().year} FaceAttend Pro · Do not reply to this email</p>
  </div>
</div></body></html>"""
    return subject, html


def _build_absent_email(name, roll, dept):
    """Build the HTML email for absent students."""
    today = datetime.now().strftime('%A, %d %B %Y')
    subject = f"⚠️ Absence Alert – {name} | {today}"

    html = f"""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body{{margin:0;padding:0;background:#030711;font-family:'Segoe UI',Arial,sans-serif}}
  .wrapper{{max-width:520px;margin:30px auto;background:#070e1a;border:1px solid #2a0a0a;border-radius:12px;overflow:hidden}}
  .header{{background:linear-gradient(135deg,#1a0000,#070e1a);padding:30px;text-align:center;border-bottom:1px solid #2a0a0a}}
  .logo{{font-size:13px;letter-spacing:4px;color:#ff6b6b;font-weight:700;margin-bottom:6px}}
  .header h1{{color:#fff;font-size:20px;margin:0;font-weight:300;letter-spacing:1px}}
  .status-badge{{display:inline-block;background:rgba(248,113,113,0.1);border:1px solid #f87171;color:#f87171;padding:5px 18px;border-radius:20px;font-size:11px;letter-spacing:2px;margin-top:14px;font-weight:600}}
  .body{{padding:30px}}
  .greeting{{color:#a0c4d8;font-size:15px;margin-bottom:20px}}
  .info-card{{background:rgba(248,113,113,0.04);border:1px solid #2a0a0a;border-radius:8px;padding:20px;margin-bottom:20px}}
  .info-row{{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid #1a0a0a}}
  .info-row:last-child{{border-bottom:none}}
  .info-label{{color:#7a4040;font-size:11px;letter-spacing:1.5px;text-transform:uppercase}}
  .info-value{{color:#e0f4ff;font-size:14px;font-weight:600}}
  .info-value.hl{{color:#f87171}}
  .alert-box{{background:rgba(248,113,113,0.08);border-left:3px solid #f87171;padding:14px 16px;border-radius:4px;font-size:13px;color:#e0a0a0;margin-top:16px;line-height:1.6}}
  .footer{{background:#030711;padding:16px 30px;text-align:center;border-top:1px solid #2a0a0a}}
  .footer p{{color:#2a4060;font-size:11px;margin:4px 0}}
</style></head><body>
<div class="wrapper">
  <div class="header">
    <div class="logo">👁 FACEATTEND PRO</div>
    <h1>Absence Notification</h1>
    <div class="status-badge">⚠️ ABSENT TODAY</div>
  </div>
  <div class="body">
    <p class="greeting">Hello <strong style="color:#e0f4ff">{name}</strong>,<br>You have been marked <strong style="color:#f87171">absent</strong> for today's session.</p>
    <div class="info-card">
      <div class="info-row"><span class="info-label">Name</span><span class="info-value">{name}</span></div>
      <div class="info-row"><span class="info-label">Roll Number</span><span class="info-value">{roll}</span></div>
      <div class="info-row"><span class="info-label">Department</span><span class="info-value">{dept}</span></div>
      <div class="info-row"><span class="info-label">Date</span><span class="info-value">{today}</span></div>
      <div class="info-row"><span class="info-label">Status</span><span class="info-value hl">ABSENT</span></div>
    </div>
    <div class="alert-box">
      ⚠️ If you were present and this notification is an error, please contact your administrator with proof of attendance.<br><br>
      Repeated absences may affect your academic record. Please ensure timely attendance.
    </div>
  </div>
  <div class="footer">
    <p>This is an automated notification from FaceAttend Pro</p>
    <p>© {datetime.now().year} FaceAttend Pro · Do not reply to this email</p>
  </div>
</div></body></html>"""
    return subject, html
