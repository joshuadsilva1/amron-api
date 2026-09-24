from app import db
from datetime import datetime


class SystemSetting(db.Model):
    """Generic admin-configurable key/value store — e.g. the default
    wastage % pre-filled onto a brand-new BOM component (see
    recipes_api.create_recipe). Values are stored as text; callers parse
    them to whatever type they expect (float, bool, ...)."""
    __tablename__ = 'system_settings'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(255), nullable=True)

    updated_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Known settings and their defaults — used to seed/backfill and to give the
# admin UI a description even before a row exists.
DEFAULT_SETTINGS = {
    'default_wastage_percent': {
        'value': '10',
        'description': (
            "Pre-filled wastage %% on a brand-new BOM component (e.g. powder "
            "spillage during moulding). Each component can still be "
            "overridden individually by an Admin — this is only the "
            "starting point for ones nobody has set yet."
        ),
    },
}


def get_default_wastage_percent():
    """Reads system_settings.default_wastage_percent, falling back to the
    hardcoded default in DEFAULT_SETTINGS if no row exists yet or the
    stored value is somehow unparseable."""
    row = SystemSetting.query.get('default_wastage_percent')
    raw = row.value if row else DEFAULT_SETTINGS['default_wastage_percent']['value']
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_SETTINGS['default_wastage_percent']['value'])
