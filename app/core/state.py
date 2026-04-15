from __future__ import annotations

import threading
from datetime import datetime

from app.config.settings import DEFAULT_SAVE_EVERY_ITEMS, DEFAULT_SAVE_EVERY_MINUTES
from app.core.utils import calcular_timer_segundos, formatar_duracao_segundos


class SharedState:
    def __init__(self, current_slot: str, default_slot: str, slots: list[dict], run_mode_labels: dict[str, str]):
        self.lock = threading.Lock()
        self.logs: list[str] = []
        self.run_mode_labels = run_mode_labels
        self.data = {
            "status": "Parado",
            "summary": "Aguardando início",
            "run_mode": "full_sync",
            "run_mode_label": run_mode_labels["full_sync"],
            "current_phase": "-",
            "current_category": "-",
            "current_item": "-",
            "saved_count": 0,
            "pending_count": 0,
            "running": False,
            "updated_at": "",
            "reused_categories": 0,
            "refetched_categories": 0,
            "verify_mode": "normal",
            "scope_mode": "all",
            "scope_start": 1,
            "scope_end": 0,
            "scope_match_text": "",
            "save_every_items": DEFAULT_SAVE_EVERY_ITEMS,
            "save_every_minutes": DEFAULT_SAVE_EVERY_MINUTES,
            "available_categories": [],
            "selected_categories": [],
            "queue_detected_count": 0,
            "new_links_detected": 0,
            "existing_links_detected": 0,
            "new_items_added": 0,
            "items_updated": 0,
            "items_unchanged": 0,
            "can_continue": False,
            "primary_button_label": "▶️ Iniciar",
            "resume_run_mode": "full_sync",
            "resume_run_mode_label": run_mode_labels["full_sync"],
            "resume_queue_index": 0,
            "resume_queue_total": 0,
            "current_slot": current_slot,
            "default_slot": default_slot,
            "slots": slots,
            "timer_seconds": 0,
            "timer_text": "0:00:00",
            "run_started_at": "",
            "run_finished_at": "",
        }

    def append_log(self, text: str) -> None:
        with self.lock:
            self.logs.append(text)
            if len(self.logs) > 5000:
                self.logs = self.logs[-5000:]
            self.data["updated_at"] = datetime.now().isoformat()

    def update(self, **kwargs) -> None:
        with self.lock:
            self.data.update(kwargs)
            self.data["updated_at"] = datetime.now().isoformat()

    def snapshot(self) -> dict:
        with self.lock:
            data = dict(self.data)
            if data.get("running") and data.get("run_started_at"):
                timer = calcular_timer_segundos(data["run_started_at"])
                data["timer_seconds"] = timer
                data["timer_text"] = formatar_duracao_segundos(timer)
            else:
                data["timer_text"] = formatar_duracao_segundos(data.get("timer_seconds", 0) or 0)
            return {"data": data, "logs": list(self.logs[-600:])}

    def full_logs_text(self) -> str:
        with self.lock:
            return "\n".join(self.logs)
