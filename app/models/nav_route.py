from app import db


class NavRoute(db.Model):
    """A human-friendly label for a frontend route path, e.g.
    '/(protected)/admin' -> 'Admin Page'. Exists purely so an Admin doesn't
    have to read/type raw Expo Router paths when picking a route elsewhere
    in the admin UI (see AppModule's route picker) — NOT related to
    DepartmentRoute (physical material handoff routing, "Routing Editor"),
    which is a completely different concept that happens to share the word
    "routing"."""
    __tablename__ = "nav_routes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    path = db.Column(db.String(255), unique=True, nullable=False)
    label = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(255), nullable=True)
