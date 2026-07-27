from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from sqlalchemy import MetaData
import os

naming_convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

db = SQLAlchemy(metadata=MetaData(naming_convention=naming_convention))
migrate = Migrate()


def create_app():

    app = Flask(__name__)
    CORS(app)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

    basedir = os.path.abspath(os.path.dirname(__file__))

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + os.path.join(basedir, "../instance/oem_factory.db")
    )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    migrate.init_app(app, db, render_as_batch=True)

    from app import models

    from app.api.items_api import items_bp
    from app.api.transaction_api import transactions_bp
    from app.api.production_api import production_bp
    from app.api.department_api import department_bp
    from app.api.recipes_api import recipes_bp
    from app.api.qc_api import qc_bp
    from app.api.supplier_api import suppliers_bp
    from app.api.auth_api import auth_bp

    app.register_blueprint(items_bp, url_prefix="/api/items")
    app.register_blueprint(transactions_bp, url_prefix="/api/transactions")
    app.register_blueprint(production_bp, url_prefix="/api/production")
    app.register_blueprint(department_bp, url_prefix="/api/departments")
    app.register_blueprint(recipes_bp, url_prefix="/api/recipes")
    app.register_blueprint(qc_bp, url_prefix="/api/qc")
    app.register_blueprint(suppliers_bp, url_prefix="/api/suppliers")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    return app