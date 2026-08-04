

import os
from dotenv import load_dotenv

load_dotenv()


from app import create_app, db
from flask_cors import CORS


app = create_app()
CORS(app)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Defaults to on (unchanged local-dev behavior — the reloader is what
    # made hot-reload work). Set FLASK_DEBUG=0 before any real deployment:
    # debug mode returns raw tracebacks to clients on unhandled errors and,
    # if the debugger endpoint is reachable, allows remote code execution.
    # Belt-and-suspenders: Render auto-injects RENDER=true on every service,
    # so debug is forced off there even if FLASK_DEBUG isn't set explicitly.
    debug = os.getenv('FLASK_DEBUG', '1') == '1' and not os.getenv('RENDER')
    app.run(host='0.0.0.0', port=5000, debug=debug)