

import os
from dotenv import load_dotenv

load_dotenv()


from app import create_app, db
from flask_cors import CORS


app = create_app()
CORS(app)

if __name__ == '__main__':
    # Defaults to on (unchanged local-dev behavior — the reloader is what
    # made hot-reload work). Set FLASK_DEBUG=0 before any real deployment:
    # debug mode returns raw tracebacks to clients on unhandled errors and,
    # if the debugger endpoint is reachable, allows remote code execution.
    # Belt-and-suspenders: Render auto-injects RENDER=true on every service,
    # so debug is forced off there even if FLASK_DEBUG isn't set explicitly.
    debug = os.getenv('FLASK_DEBUG', '1') == '1' and not os.getenv('RENDER')

    # NOT db.create_all() — this project's schema is tracked entirely by
    # Alembic (migrations/versions/, applied via `flask db upgrade`; Render
    # runs that same command as its preDeployCommand). create_all() used to
    # run here on every dev-server start/reload and would silently create a
    # brand-new model's table straight from its class definition — skipping
    # that migration's seed data AND never touching alembic_version. The
    # next real `flask db upgrade` then hit "relation already exists" and
    # looked like a stuck migration state (see the report_subscriptions and
    # system_settings/audit_logs incidents). Run `flask db upgrade` by hand
    # after pulling a new model/migration instead.

    app.run(host='0.0.0.0', port=5000, debug=debug)