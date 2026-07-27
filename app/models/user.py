from app import db
from app.core.utils import generate_uuid
from datetime import datetime


class User(db.Model):

    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    phone_number = db.Column(db.String(20), unique=True, nullable=False)

    full_name = db.Column(db.String(100))

    role = db.Column(db.String(30), default="USER")

    department_id = db.Column(
        db.String(36),
        db.ForeignKey("departments.id")
    )

    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )