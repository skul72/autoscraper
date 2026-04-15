from __future__ import annotations

from app.config.settings import DEFAULT_SAVE_EVERY_ITEMS, DEFAULT_SAVE_EVERY_MINUTES
from app.storage.files import write_txt_atomic
from app.storage.paths import logs_txt_path, status_txt_path


def build_status_text(app) -> str:
    snap = app.state.snapshot()["data"]
    lines = [
        f"Slot atual: {snap.get('current_slot', '-')}",
        f"Slot default: {snap.get('default_slot', '-')}",
        f"Estado: {snap.get('status', '-')}",
        f"Fluxo atual: {snap.get('run_mode_label', '-')}",
        f"Fase atual: {snap.get('current_phase', '-')}",
        f"Tempo: {snap.get('timer_text', '0:00:00')}",
        f"Resumo: {snap.get('summary', '-')}",
        f"Validação atual: {snap.get('verify_mode', '-')}",
        f"Escopo atual: {snap.get('scope_mode', '-')}",
        f"Salvar a cada itens: {snap.get('save_every_items', DEFAULT_SAVE_EVERY_ITEMS)}",
        f"Salvar a cada minutos: {snap.get('save_every_minutes', DEFAULT_SAVE_EVERY_MINUTES)}",
    ]
    return "\n".join(lines) + "\n"


def save_status_txt(app) -> None:
    write_txt_atomic(status_txt_path(app.get_current_slot()), build_status_text(app))


def save_full_log_txt(app) -> None:
    write_txt_atomic(logs_txt_path(app.get_current_slot()), app.state.full_logs_text())
    save_status_txt(app)
