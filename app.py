# Gevent monkey patching - must be at the very top before any other imports
from gevent import monkey
monkey.patch_all()

import os

from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    # Docker ortamında debug=False, lokalde debug=True
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=debug_mode,
        use_reloader=debug_mode,
    )
