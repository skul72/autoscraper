from __future__ import annotations

import threading


class ControlState:
    def __init__(self):
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.current_run_mode = "full_sync"
        self.current_run_payload: dict = {}

    def reset(self) -> None:
        self.pause_event.clear()
        self.stop_event.clear()

    def pause(self) -> None:
        self.pause_event.set()

    def resume(self) -> None:
        self.pause_event.clear()

    def stop(self) -> None:
        self.stop_event.set()
        self.pause_event.clear()

    def is_paused(self) -> bool:
        return self.pause_event.is_set()

    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    def is_running(self) -> bool:
        return self.worker_thread is not None and self.worker_thread.is_alive()
