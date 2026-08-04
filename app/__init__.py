import os
from flask import Flask, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from sqlalchemy import MetaData

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

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "super-secret-key")

    # --- SUPABASE UPDATE START ---
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        # Supabase/PostgreSQL connection
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        # Local SQLite fallback
        basedir = os.path.abspath(os.path.dirname(__file__))
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "../instance/oem_factory.db")
    # --- SUPABASE UPDATE END ---

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
    from app.api.client_api import clients_bp
    from app.api.orders_api import orders_bp
    from app.api.oem_api import oem_bp
    from app.api.dispatch_api import dispatch_bp
    from app.api.attendance_api import attendance_bp
    from app.api.payroll_api import payroll_bp
    from app.api.notification_api import notification_bp
    from app.api.admin_api import admin_bp
    from app.api.racks_api import racks_bp
    from app.api.import_api import import_bp
    from app.api.whatsapp_api import whatsapp_bp
    from app.api.chat_api import chat_bp
    from app.api.box_api import box_bp


    app.register_blueprint(racks_bp, url_prefix='/api/racks')
    app.register_blueprint(items_bp, url_prefix="/api/items")
    app.register_blueprint(transactions_bp, url_prefix="/api/transactions")
    app.register_blueprint(production_bp, url_prefix="/api/production")
    app.register_blueprint(department_bp, url_prefix="/api/departments")
    app.register_blueprint(recipes_bp, url_prefix="/api/recipes")
    app.register_blueprint(qc_bp, url_prefix="/api/qc")
    app.register_blueprint(suppliers_bp, url_prefix="/api/suppliers")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(clients_bp, url_prefix="/api/clients")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(oem_bp, url_prefix='/api/oem')
    app.register_blueprint(dispatch_bp, url_prefix='/api/transactions/dispatch')
    app.register_blueprint(attendance_bp, url_prefix='/api/attendance')
    app.register_blueprint(payroll_bp, url_prefix='/payroll')
    app.register_blueprint(notification_bp, url_prefix='/api/notifications')
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(import_bp, url_prefix='/api/import')
    app.register_blueprint(whatsapp_bp, url_prefix='/api/whatsapp')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(box_bp, url_prefix='/api/boxes')

    # Serve uploaded bill/chalan images
    uploads_root = os.path.join(app.root_path, '..', 'uploads')
    os.makedirs(uploads_root, exist_ok=True)

    @app.route('/uploads/<path:subpath>')
    def serve_upload(subpath):
        return send_from_directory(uploads_root, subpath)

    return app