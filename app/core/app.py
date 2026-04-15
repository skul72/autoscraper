from __future__ import annotations

import asyncio
import threading
import traceback
from datetime import datetime

from app.config.settings import DEFAULT_SAVE_EVERY_ITEMS, DEFAULT_SAVE_EVERY_MINUTES
from app.config.slots import create_slot, delete_slot, get_active_slot, list_slots, load_slots_meta, set_active_slot, set_default_slot
from app.core.control import ControlState
from app.core.state import SharedState
from app.core.utils import agora_iso, calcular_timer_segundos, formatar_duracao_segundos, normalizar_espacos, to_int
from app.scraper.flow import atualizar_apenas_categorias, executar_fluxo
from app.core.constants import RUN_MODE_CATEGORIES_ONLY, RUN_MODE_EXISTING_REVIEW, RUN_MODE_FULL, RUN_MODE_LABELS, RUN_MODE_LINKS_ONLY, RUN_MODE_PRIMARY, RUN_MODE_SELECTED_SYNC, RUN_MODES
from app.storage.cache import load_available_categories
from app.storage.catalog import get_resume_info, load_existing_products, save_state
from app.storage.files import read_json
from app.storage.paths import categories_cache_path, config_json_path, output_json_path, progress_json_path, queue_cache_path
from app.storage.status import save_full_log_txt, save_status_txt


def obter_config_padrao() -> dict:
    return {
        "verify_mode": "normal",
        "scope_mode": "all",
        "scope_start": 1,
        "scope_end": 0,
        "scope_match_text": "",
        "save_every_items": DEFAULT_SAVE_EVERY_ITEMS,
        "save_every_minutes": DEFAULT_SAVE_EVERY_MINUTES,
        "selected_categories": [],
    }


def normalizar_config_dict(config: dict) -> dict:
    base = obter_config_padrao()
    if isinstance(config, dict):
        base.update(config)
    verify_mode = str(base.get("verify_mode", "normal") or "normal").strip().lower()
    if verify_mode not in {"normal", "complete"}:
        verify_mode = "normal"
    scope_mode = str(base.get("scope_mode", "all") or "all").strip().lower()
    if scope_mode not in {"all", "range", "match", "selected"}:
        scope_mode = "all"
    selected_categories = base.get("selected_categories", [])
    if not isinstance(selected_categories, list):
        selected_categories = []
    return {
        "verify_mode": verify_mode,
        "scope_mode": scope_mode,
        "scope_start": max(1, to_int(base.get("scope_start", 1), 1)),
        "scope_end": max(0, to_int(base.get("scope_end", 0), 0)),
        "scope_match_text": str(base.get("scope_match_text", "") or ""),
        "save_every_items": max(1, to_int(base.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS), DEFAULT_SAVE_EVERY_ITEMS)),
        "save_every_minutes": max(1, to_int(base.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES), DEFAULT_SAVE_EVERY_MINUTES)),
        "selected_categories": sorted({normalizar_espacos(x) for x in selected_categories if normalizar_espacos(x)}),
    }


def carregar_config_slot(slot_name: str) -> dict:
    raw = read_json(config_json_path(slot_name), {})
    if not isinstance(raw, dict):
        raw = {}
    return normalizar_config_dict(raw)


def salvar_config_slot(slot_name: str, config: dict) -> dict:
    from app.storage.files import write_json_atomic

    atual = carregar_config_slot(slot_name)
    if isinstance(config, dict):
        atual.update(config)
    normalizada = normalizar_config_dict(atual)
    write_json_atomic(config_json_path(slot_name), normalizada)
    return normalizada


class ScraperApp:
    def __init__(self):
        self.control = ControlState()
        meta = load_slots_meta()
        self.state = SharedState(meta["active_slot"], meta["default_slot"], list_slots(), RUN_MODE_LABELS)
        self.server = None
        self.categories_worker_thread: threading.Thread | None = None

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        self.state.append_log(line)

    def get_current_slot(self) -> str:
        return get_active_slot()

    def refresh_slots_state(self):
        meta = load_slots_meta()
        self.state.update(current_slot=meta["active_slot"], default_slot=meta["default_slot"], slots=list_slots())

    def create_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível criar slot com o processo rodando."
        slot = create_slot(slot_name)
        self.refresh_slots_state()
        self.load_initial_summary()
        self.log(f"🆕 Slot criado/carregado: {slot}")
        return True, f"Slot ativo: {slot}"

    def switch_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível trocar slot com o processo rodando."
        slot = set_active_slot(slot_name)
        self.refresh_slots_state()
        self.load_initial_summary()
        self.log(f"📂 Slot carregado: {slot}")
        return True, f"Slot carregado: {slot}"

    def set_default_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível alterar o slot default com o processo rodando."
        slot = set_default_slot(slot_name)
        self.refresh_slots_state()
        self.load_initial_summary()
        self.log(f"⭐ Slot definido como default: {slot}")
        return True, f"Slot default: {slot}"

    def delete_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível apagar slot com o processo rodando."
        ok, msg = delete_slot(slot_name)
        self.refresh_slots_state()
        self.load_initial_summary()
        if ok:
            self.log(f"🗑 Slot apagado: {slot_name}")
        return ok, msg

    def get_run_options(self) -> dict:
        snap = self.state.snapshot()["data"]
        return {
            "verify_mode": snap.get("verify_mode", "normal"),
            "scope_mode": snap.get("scope_mode", "all"),
            "scope_start": to_int(snap.get("scope_start", 1), 1),
            "scope_end": to_int(snap.get("scope_end", 0), 0),
            "scope_match_text": snap.get("scope_match_text", "") or "",
            "save_every_items": to_int(snap.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS), DEFAULT_SAVE_EVERY_ITEMS),
            "save_every_minutes": to_int(snap.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES), DEFAULT_SAVE_EVERY_MINUTES),
            "selected_categories": list(snap.get("selected_categories", []) or []),
        }

    def set_run_options(self, payload: dict):
        config = salvar_config_slot(self.get_current_slot(), payload or {})
        self.state.update(**config)
        save_status_txt(self)
        return True, "Configuração aplicada."

    def start_worker(self, run_mode="full_sync", run_payload=None):
        if self.control.is_running():
            return False, "O processo já está rodando."
        self.control.reset()
        self.control.current_run_mode = run_mode if run_mode in RUN_MODES else RUN_MODE_FULL
        self.control.current_run_payload = dict(run_payload or {})
        run_started_at = agora_iso()
        self.state.update(status="Iniciando", running=True, run_mode=self.control.current_run_mode, run_mode_label=RUN_MODE_LABELS.get(self.control.current_run_mode, self.control.current_run_mode), current_phase="Preparando", run_started_at=run_started_at, run_finished_at="", timer_seconds=0, timer_text="0:00:00")
        self.log(f"▶ Iniciando processo: {RUN_MODE_LABELS.get(self.control.current_run_mode, self.control.current_run_mode)}")
        worker = threading.Thread(target=self.worker_run, daemon=True)
        self.control.worker_thread = worker
        worker.start()
        return True, "Processo iniciado."

    def pause_worker(self):
        if not self.control.is_running():
            return False, "Não há processo rodando."
        self.control.pause(); self.state.update(status="Pausando..."); self.log("⏸ Pausa solicitada"); save_full_log_txt(self)
        return True, "Pausa solicitada."

    def resume_worker(self):
        if not self.control.is_running():
            return False, "Não há processo rodando."
        self.control.resume(); self.state.update(status="Rodando"); self.log("▶ Continuação solicitada")
        return True, "Continuação solicitada."

    def stop_worker(self):
        if not self.control.is_running():
            return False, "Não há processo rodando."
        self.control.stop(); self.state.update(status="Parando..."); self.log("⏹ Parada solicitada"); save_full_log_txt(self)
        return True, "Parada solicitada."

    def refresh_categories_only(self):
        if self.categories_worker_thread is not None and self.categories_worker_thread.is_alive():
            return False, "A atualização de categorias já está rodando."
        worker = threading.Thread(target=self.refresh_categories_worker_run, daemon=True)
        self.categories_worker_thread = worker
        self.log("🔄 Iniciando atualização de categorias")
        worker.start()
        return True, "Atualização de categorias iniciada."

    def refresh_categories_worker_run(self):
        try:
            categorias = asyncio.run(atualizar_apenas_categorias(self))
            if not self.control.is_running():
                self.state.update(summary=f"Categorias disponíveis: {len(categorias)}")
            self.log(f"✅ Atualização de categorias concluída. Total: {len(categorias)}")
        except Exception as e:
            err = "".join(traceback.format_exception_only(type(e), e)).strip(); self.log(f"❌ Erro ao atualizar categorias: {err}")
            save_full_log_txt(self)
        finally:
            self.categories_worker_thread = None

    def load_initial_summary(self):
        slot = self.get_current_slot()
        data = read_json(output_json_path(slot), [])
        progress = read_json(progress_json_path(slot), {})
        meta = progress.get("meta", {}) or {}
        resume_info = get_resume_info(meta)
        config = carregar_config_slot(slot)
        available = load_available_categories(slot)
        timer_seconds = to_int(meta.get("timer_seconds", 0), 0)
        self.state.update(status="Parado", running=False, summary=f"Já existem {len(data)} itens salvos", saved_count=len(data), verify_mode=config["verify_mode"], scope_mode=config["scope_mode"], scope_start=config["scope_start"], scope_end=config["scope_end"], scope_match_text=config["scope_match_text"], save_every_items=config["save_every_items"], save_every_minutes=config["save_every_minutes"], selected_categories=config.get("selected_categories", []), available_categories=available, can_continue=resume_info["can_continue"], resume_queue_index=resume_info["queue_index"], resume_queue_total=resume_info["queue_total"], run_started_at=meta.get("run_started_at", ""), run_finished_at=meta.get("run_finished_at", ""), timer_seconds=timer_seconds, timer_text=formatar_duracao_segundos(timer_seconds), current_slot=slot, default_slot=load_slots_meta().get("default_slot"), slots=list_slots())
        save_status_txt(self)

    def worker_run(self):
        try:
            produtos = asyncio.run(executar_fluxo(self, self.get_run_options(), self.control.current_run_mode, self.control.current_run_payload))
            snap = self.state.snapshot()["data"]
            fim = agora_iso(); timer = calcular_timer_segundos(snap.get("run_started_at", ""), fim)
            self.state.update(status="Concluído", running=False, summary=f"Concluído. Total salvo: {len(produtos)}", saved_count=len(produtos), pending_count=0, current_phase="Finalizado", run_finished_at=fim, timer_seconds=timer, timer_text=formatar_duracao_segundos(timer))
            self.log(f"✅ Processo concluído. Total salvo: {len(produtos)}")
            save_full_log_txt(self)
        except Exception as e:
            err = "".join(traceback.format_exception_only(type(e), e)).strip(); fim = agora_iso()
            snap = self.state.snapshot()["data"]; timer = calcular_timer_segundos(snap.get("run_started_at", ""), fim)
            self.state.update(status="Erro", running=False, run_finished_at=fim, timer_seconds=timer, timer_text=formatar_duracao_segundos(timer)); self.log(f"❌ Erro: {err}"); save_full_log_txt(self)
        finally:
            self.control.worker_thread = None
            self.control.current_run_payload = {}
            self.load_initial_summary()
