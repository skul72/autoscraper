from __future__ import annotations

import asyncio
import threading
import traceback
from datetime import datetime

from app.config.slots import create_slot, delete_slot, get_active_slot, list_slots, load_slots_meta, set_active_slot, set_default_slot
from app.core.constants import RUN_MODE_FULL, RUN_MODE_LABELS, RUN_MODE_PRIMARY, RUN_MODES
from app.core.control import ControlState
from app.core.state import SharedState
from app.core.utils import agora_iso, calcular_timer_segundos, formatar_duracao_segundos, normalizar_espacos, to_int
from app.scraper.flow import atualizar_apenas_categorias, executar_fluxo
from app.storage.cache import load_available_categories
from app.storage.catalog import get_resume_info, load_existing_products, save_state
from app.storage.files import read_json
from app.storage.paths import (
    categories_cache_path,
    output_csv_path,
    output_json_path,
    progress_json_path,
    queue_cache_path,
    status_txt_path,
    logs_txt_path,
)
from app.storage.status import save_full_log_txt, save_status_txt
from app.config.settings import DEFAULT_SAVE_EVERY_ITEMS, DEFAULT_SAVE_EVERY_MINUTES, TEST_MODE


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
    selected_categories = sorted({normalizar_espacos(x) for x in selected_categories if normalizar_espacos(x)})
    return {
        "verify_mode": verify_mode,
        "scope_mode": scope_mode,
        "scope_start": max(1, to_int(base.get("scope_start", 1), 1)),
        "scope_end": max(0, to_int(base.get("scope_end", 0), 0)),
        "scope_match_text": str(base.get("scope_match_text", "") or ""),
        "save_every_items": max(1, to_int(base.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS), DEFAULT_SAVE_EVERY_ITEMS)),
        "save_every_minutes": max(1, to_int(base.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES), DEFAULT_SAVE_EVERY_MINUTES)),
        "selected_categories": selected_categories,
    }


def _config_path(slot: str):
    from app.storage.paths import config_json_path

    return config_json_path(slot)


def carregar_config_slot(slot_name: str) -> dict:
    raw = read_json(_config_path(slot_name), {})
    if not isinstance(raw, dict):
        raw = {}
    return normalizar_config_dict(raw)


def salvar_config_slot(slot_name: str, config: dict) -> dict:
    from app.storage.files import write_json_atomic

    atual = carregar_config_slot(slot_name)
    if isinstance(config, dict):
        atual.update(config)
    final = normalizar_config_dict(atual)
    write_json_atomic(_config_path(slot_name), final)
    return final


class ScraperApp:
    def __init__(self):
        self.control = ControlState()
        meta = load_slots_meta()
        self.state = SharedState(meta["active_slot"], meta["default_slot"], list_slots(), RUN_MODE_LABELS)
        self.server = None
        self.categories_worker_thread: threading.Thread | None = None

    def log(self, msg: str):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        self.state.append_log(line)

    def get_current_slot(self) -> str:
        return get_active_slot()

    def refresh_slots_state(self):
        meta = load_slots_meta()
        self.state.update(current_slot=meta.get("active_slot"), default_slot=meta.get("default_slot"), slots=list_slots())

    def create_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível criar slot com o processo rodando."
        slot = create_slot(slot_name)
        self.refresh_slots_state(); self.load_initial_summary(); self.log(f"🆕 Slot criado/carregado: {slot}")
        return True, f"Slot ativo: {slot}"

    def switch_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível trocar slot com o processo rodando."
        slot = set_active_slot(slot_name)
        self.refresh_slots_state(); self.load_initial_summary(); self.log(f"📂 Slot carregado: {slot}")
        return True, f"Slot carregado: {slot}"

    def set_default_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível alterar o slot default com o processo rodando."
        slot = set_default_slot(slot_name)
        self.refresh_slots_state(); self.load_initial_summary(); self.log(f"⭐ Slot definido como default: {slot}")
        return True, f"Slot default: {slot}"

    def delete_slot(self, slot_name: str):
        if self.control.is_running():
            return False, "Não é possível apagar slot com o processo rodando."
        ok, msg = delete_slot(slot_name)
        self.refresh_slots_state(); self.load_initial_summary()
        if ok:
            self.log(f"🗑 Slot apagado: {slot_name}")
        return ok, msg

    def get_run_options(self):
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

    def set_run_options(self, payload):
        cfg = salvar_config_slot(self.get_current_slot(), payload or {})
        self.state.update(**cfg)
        save_status_txt(self)
        self.log(
            f"⚙️ Configuração aplicada | validação: {cfg['verify_mode']} | escopo: {cfg['scope_mode']} | início: {cfg['scope_start']} | fim: {cfg['scope_end']}"
        )
        return True, "Configuração aplicada."

    def start_worker(self, run_mode=RUN_MODE_FULL, run_payload=None):
        if self.control.is_running():
            return False, "O processo já está rodando."
        run_payload = dict(run_payload or {})
        total_saved = len(load_existing_products(self.get_current_slot()))
        if run_mode == RUN_MODE_PRIMARY:
            progress = read_json(progress_json_path(self.get_current_slot()), {})
            resume = get_resume_info((progress.get("meta", {}) or {}))
            if total_saved > 0 and run_payload.get("force_full_review"):
                run_mode_real = RUN_MODE_FULL
                run_payload["resume"] = False
            elif total_saved > 0 and resume["can_continue"]:
                run_mode_real = resume["run_mode"] if resume["run_mode"] in RUN_MODES else RUN_MODE_FULL
                run_payload["resume"] = True
            else:
                run_mode_real = RUN_MODE_FULL
                run_payload["resume"] = False
        else:
            run_mode_real = run_mode if run_mode in RUN_MODES else RUN_MODE_FULL

        self.control.reset()
        self.control.current_run_mode = run_mode_real
        self.control.current_run_payload = run_payload
        self.state.update(status="Iniciando", running=True, run_mode=run_mode_real, run_mode_label=RUN_MODE_LABELS.get(run_mode_real, run_mode_real), current_phase="Preparando", run_started_at=agora_iso(), run_finished_at="", timer_seconds=0, timer_text="0:00:00")
        self.log(f"▶ Iniciando processo: {RUN_MODE_LABELS.get(run_mode_real, run_mode_real)}")
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

    def rebuild_outputs(self):
        if self.control.is_running():
            return False, "Pare o processo antes de reconstruir as saídas."
        produtos = load_existing_products(self.get_current_slot())
        save_state(self, produtos, {
            "status": "reconstruido",
            "run_mode": self.state.snapshot()["data"].get("run_mode", RUN_MODE_FULL),
            "current_phase": "Reconstruído",
            "modo_teste": TEST_MODE,
        })
        self.log("🧩 Saídas reconstruídas com base no JSON principal")
        return True, "Reconstruído."

    def clear_slot_records(self):
        if self.control.is_running():
            return False, "Pare o processo antes de zerar os registros do slot."
        slot = self.get_current_slot()
        for p in [output_csv_path(slot), output_json_path(slot), progress_json_path(slot), status_txt_path(slot)]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        self.load_initial_summary(); self.log("🧹 Registros do slot zerados")
        return True, "Registros do slot zerados."

    def reset_progress(self):
        if self.control.is_running():
            return False, "Pare o processo antes de apagar o progresso."
        slot = self.get_current_slot()
        for p in [output_csv_path(slot), output_json_path(slot), progress_json_path(slot), categories_cache_path(slot), queue_cache_path(slot), logs_txt_path(slot), status_txt_path(slot)]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        self.load_initial_summary(); self.log("🗑 Progresso apagado")
        return True, "Progresso apagado."

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
            self.log(f"❌ Erro ao atualizar categorias: {''.join(traceback.format_exception_only(type(e), e)).strip()}")
            save_full_log_txt(self)
        finally:
            self.categories_worker_thread = None

    def load_initial_summary(self):
        slot = self.get_current_slot()
        data = read_json(output_json_path(slot), [])
        progresso = read_json(progress_json_path(slot), {})
        meta = progresso.get("meta", {}) or {}
        resume = get_resume_info(meta)
        config = carregar_config_slot(slot)
        available = load_available_categories(slot)
        timer_seconds = to_int(meta.get("timer_seconds", 0), 0)
        if meta.get("run_started_at"):
            timer_seconds = calcular_timer_segundos(meta.get("run_started_at", ""), meta.get("run_finished_at") or None)
        self.state.update(
            status="Parado",
            running=False,
            summary=f"Já existem {len(data)} itens salvos",
            run_mode=meta.get("run_mode", RUN_MODE_FULL),
            run_mode_label=RUN_MODE_LABELS.get(meta.get("run_mode", RUN_MODE_FULL), RUN_MODE_LABELS[RUN_MODE_FULL]),
            current_phase=meta.get("current_phase", "-"),
            current_category=meta.get("ultima_categoria", "-") or "-",
            current_item=meta.get("ultimo_item_nome", "-") or "-",
            saved_count=len(data),
            pending_count=0,
            reused_categories=meta.get("categorias_reutilizadas", 0),
            refetched_categories=meta.get("categorias_refeitas", 0),
            verify_mode=config.get("verify_mode", "normal"),
            scope_mode=config.get("scope_mode", "all"),
            scope_start=config.get("scope_start", 1),
            scope_end=config.get("scope_end", 0),
            scope_match_text=config.get("scope_match_text", ""),
            save_every_items=config.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS),
            save_every_minutes=config.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES),
            available_categories=available,
            selected_categories=config.get("selected_categories", []),
            queue_detected_count=meta.get("queue_detected_count", 0),
            new_links_detected=meta.get("new_links_detected", 0),
            existing_links_detected=meta.get("existing_links_detected", 0),
            new_items_added=meta.get("itens_novos_adicionados", 0),
            items_updated=meta.get("itens_atualizados", 0),
            items_unchanged=meta.get("itens_sem_mudanca", 0),
            can_continue=resume["can_continue"],
            primary_button_label="▶️ Retomar" if len(data) > 0 else "▶️ Iniciar",
            resume_run_mode=resume["run_mode"],
            resume_run_mode_label=RUN_MODE_LABELS.get(resume["run_mode"], resume["run_mode"]),
            resume_queue_index=resume["queue_index"],
            resume_queue_total=resume["queue_total"],
            current_slot=slot,
            default_slot=load_slots_meta().get("default_slot"),
            slots=list_slots(),
            run_started_at=meta.get("run_started_at", ""),
            run_finished_at=meta.get("run_finished_at", ""),
            timer_seconds=timer_seconds,
            timer_text=formatar_duracao_segundos(timer_seconds),
        )
        save_status_txt(self)

    def worker_run(self):
        run_mode = self.control.current_run_mode or RUN_MODE_FULL
        run_payload = dict(self.control.current_run_payload or {})
        try:
            produtos = asyncio.run(executar_fluxo(self, self.get_run_options(), run_mode, run_payload))
            snap = self.state.snapshot()["data"]
            fim = agora_iso()
            timer = calcular_timer_segundos(snap.get("run_started_at", ""), fim)
            self.state.update(status="Concluído", running=False, summary=f"Concluído. Total salvo: {len(produtos)}", saved_count=len(produtos), pending_count=0, current_phase="Finalizado", run_finished_at=fim, timer_seconds=timer, timer_text=formatar_duracao_segundos(timer))
            self.log(f"✅ Processo concluído. Total salvo: {len(produtos)}")
            save_full_log_txt(self)
        except Exception as e:
            snap = self.state.snapshot()["data"]
            fim = agora_iso()
            timer = calcular_timer_segundos(snap.get("run_started_at", ""), fim)
            self.state.update(status="Erro", running=False, run_finished_at=fim, timer_seconds=timer, timer_text=formatar_duracao_segundos(timer))
            self.log(f"❌ Erro: {''.join(traceback.format_exception_only(type(e), e)).strip()}")
            save_full_log_txt(self)
        finally:
            self.control.worker_thread = None
            self.control.current_run_payload = {}
            self.load_initial_summary()
