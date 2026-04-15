from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from app.ui.page_monitor import render_page_monitor


def make_handler(app):
    assets_dir = Path(__file__).resolve().parents[1] / "ui" / "assets"

    class Handler(BaseHTTPRequestHandler):
        def _send_bytes(self, content: bytes, content_type: str, code=200):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, obj, code=200):
            self._send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", code)

        def _send_html(self, html: str, code=200):
            self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8", code)

        def _read_json_body(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            if length <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                return {}

        def log_message(self, *args):
            return

        def do_GET(self):
            if self.path == "/":
                self._send_html(render_page_monitor()); return
            if self.path == "/state":
                self._send_json(app.state.snapshot()); return
            if self.path == "/logs_full":
                self._send_json({"ok": True, "text": app.state.full_logs_text()}); return
            if self.path == "/assets/styles.css":
                self._send_bytes((assets_dir / "styles.css").read_bytes(), "text/css; charset=utf-8"); return
            if self.path == "/assets/app.js":
                self._send_bytes((assets_dir / "app.js").read_bytes(), "application/javascript; charset=utf-8"); return
            self._send_json({"ok": False, "message": "Rota não encontrada."}, code=404)

        def do_POST(self):
            payload = self._read_json_body()
            routes = {
                "/slot/create": lambda: app.create_slot(payload.get("slot_name", "")),
                "/slot/switch": lambda: app.switch_slot(payload.get("slot_name", "")),
                "/slot/default": lambda: app.set_default_slot(payload.get("slot_name", "")),
                "/slot/delete": lambda: app.delete_slot(payload.get("slot_name", "")),
                "/start": lambda: app.start_worker("primary", payload),
                "/pause": app.pause_worker,
                "/resume": app.resume_worker,
                "/stop": app.stop_worker,
                "/reset": lambda: (False, "Não implementado"),
                "/rebuild": lambda: (False, "Não implementado"),
                "/clear_slot_data": lambda: (False, "Não implementado"),
                "/refresh_categories": app.refresh_categories_only,
                "/config": lambda: app.set_run_options(payload),
            }
            if self.path.startswith("/run/"):
                mode = self.path.split("/run/", 1)[1].strip().lower()
                ok, msg = app.start_worker(mode, payload)
                self._send_json({"ok": ok, "message": msg}); return
            handler = routes.get(self.path)
            if not handler:
                self._send_json({"ok": False, "message": "Rota não encontrada."}, code=404); return
            ok, msg = handler()
            self._send_json({"ok": ok, "message": msg})

    return Handler
