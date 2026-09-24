from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class WhatsAppConfig(db.Model):
    """Single-row settings for the business's WhatsApp sending account
    (Gupshup today; `provider` exists so this doesn't need a schema change
    if that ever switches)."""
    __tablename__ = 'whatsapp_config'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    provider = db.Column(db.String(50), default='gupshup')

    api_key = db.Column(db.String(255), nullable=True)
    app_name = db.Column(db.String(100), nullable=True)
    sender_number = db.Column(db.String(20), nullable=True)

    is_active = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReportSubscription(db.Model):
    """One daily WhatsApp report: who gets it, and when. `department_id`
    NULL is the whole-factory report; otherwise it's that department's own
    report. `send_time` is HH:MM in the factory's local time (REPORT_TZ,
    default Asia/Kolkata). A scheduled job (flask send-daily-reports, run
    every 15 min — see render.yaml) sends whatever is due and stamps
    `last_sent_on` so each report goes out once per day."""
    __tablename__ = 'report_subscriptions'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=True)

    recipient_number = db.Column(db.String(20), nullable=False)
    send_time = db.Column(db.String(5), nullable=False, default='08:00')
    is_enabled = db.Column(db.Integer, default=1)

    last_sent_on = db.Column(db.Date, nullable=True)
    last_status = db.Column(db.String(20), nullable=True)   # 'sent' | 'failed'
    last_error = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
