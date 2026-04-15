from __future__ import annotations

import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer

from app.config.settings import PANEL_HOST, PANEL_PORT
from app.web.handlers import make_handler


def start_server(app):
    handler = make_handler(app)
    server = ThreadingHTTPServer((PANEL_HOST, PANEL_PORT), handler)
    app.server = server
    url = f"http://{PANEL_HOST}:{PANEL_PORT}"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Painel iniciado em {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Encerrando painel...")
    finally:
        server.server_close()
