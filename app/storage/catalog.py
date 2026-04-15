from __future__ import annotations

from datetime import datetime

from app.config.settings import DEFAULT_SAVE_EVERY_ITEMS, DEFAULT_SAVE_EVERY_MINUTES, RETOMAR_DE_ONDE_PAROU
from app.core.utils import calcular_timer_segundos, ensure_trailing_slash, formatar_duracao_segundos, normalizar_espacos, normalizar_item_fila, to_int
from app.storage.files import read_json, write_csv_atomic, write_json_atomic
from app.storage.paths import output_csv_path, output_json_path, progress_json_path

FIELDNAMES = [
    "tipo",
    "categoria_nome",
    "categoria_url",
    "link_produto",
    "nome_produto",
    "versao_produto",
    "observacao",
]


def sort_products(produtos: list[dict]) -> list[dict]:
    return sorted(
        produtos,
        key=lambda x: (
            normalizar_espacos(x.get("categoria_nome", "")).lower(),
            normalizar_espacos(x.get("nome_produto", "")).lower(),
            normalizar_espacos(x.get("link_produto", "")).lower(),
        ),
    )


def load_existing_products(slot_name: str) -> dict[str, dict]:
    if not RETOMAR_DE_ONDE_PAROU:
        return {}
    data = read_json(output_json_path(slot_name), [])
    produtos: dict[str, dict] = {}
    for item in data:
        link = normalizar_espacos(item.get("link_produto", ""))
        if link:
            produtos[link] = item
    return produtos


def normalize_product(produto: dict) -> dict:
    return {
        "tipo": normalizar_espacos(produto.get("tipo", "")) or "plugin",
        "categoria_nome": normalizar_espacos(produto.get("categoria_nome", "")),
        "categoria_url": ensure_trailing_slash(normalizar_espacos(produto.get("categoria_url", ""))),
        "link_produto": normalizar_espacos(produto.get("link_produto", "")),
        "nome_produto": normalizar_espacos(produto.get("nome_produto", "")),
        "versao_produto": normalizar_espacos(produto.get("versao_produto", "")),
        "observacao": normalizar_espacos(produto.get("observacao", "")),
    }


def merge_product(produto_existente: dict, produto_novo: dict) -> dict:
    existente = normalize_product(produto_existente or {})
    novo = normalize_product(produto_novo or {})
    def choose(nv: str, ov: str):
        return nv if normalizar_espacos(nv) else ov
    return {
        "tipo": choose(novo["tipo"], existente["tipo"]) or "plugin",
        "categoria_nome": choose(novo["categoria_nome"], existente["categoria_nome"]),
        "categoria_url": ensure_trailing_slash(choose(novo["categoria_url"], existente["categoria_url"])),
        "link_produto": choose(novo["link_produto"], existente["link_produto"]),
        "nome_produto": choose(novo["nome_produto"], existente["nome_produto"]),
        "versao_produto": choose(novo["versao_produto"], existente["versao_produto"]),
        "observacao": choose(novo["observacao"], existente["observacao"]),
    }


def get_resume_info(meta: dict) -> dict:
    meta = meta or {}
    full_queue = [normalizar_item_fila(i) for i in (meta.get("resume_full_queue_items", []) or []) if normalizar_espacos(i.get("link_produto", ""))]
    queue_total = len(full_queue) if full_queue else to_int(meta.get("resume_queue_total", 0), 0)
    queue_index = max(0, min(queue_total, to_int(meta.get("resume_queue_index", 0), 0)))
    run_mode = meta.get("run_mode", "full_sync")
    status = str(meta.get("status", "") or "").strip().lower()
    can_continue = run_mode in {"full_sync", "existing_review", "selected_sync"} and status in {"em_andamento", "interrompido"} and queue_total > queue_index
    return {"can_continue": can_continue, "run_mode": run_mode, "queue_total": queue_total, "queue_index": queue_index, "full_queue": full_queue}


def save_state(app, produtos_dict: dict, meta: dict) -> None:
    slot = app.get_current_slot()
    produtos = sort_products(list(produtos_dict.values()))
    write_csv_atomic(output_csv_path(slot), FIELDNAMES, produtos)
    write_json_atomic(output_json_path(slot), produtos)

    snap = app.state.snapshot()["data"]
    run_started_at = meta.get("run_started_at", snap.get("run_started_at", ""))
    run_finished_at = meta.get("run_finished_at", snap.get("run_finished_at", ""))
    timer_seconds = calcular_timer_segundos(run_started_at, run_finished_at or None) if run_started_at else to_int(meta.get("timer_seconds", 0), 0)
    meta = {**meta, "run_started_at": run_started_at, "run_finished_at": run_finished_at, "timer_seconds": timer_seconds, "timer_text": formatar_duracao_segundos(timer_seconds)}
    progress = {"updated_at": datetime.now().isoformat(), "total_salvos": len(produtos), "meta": meta}
    write_json_atomic(progress_json_path(slot), progress)

    resume = get_resume_info(meta)
    app.state.update(
        saved_count=len(produtos),
        can_continue=resume["can_continue"],
        resume_queue_index=resume["queue_index"],
        resume_queue_total=resume["queue_total"],
        save_every_items=meta.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS),
        save_every_minutes=meta.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES),
    )



def describe_product_changes(produto_antigo: dict, produto_final: dict) -> list[str]:
    antigo = normalize_product(produto_antigo or {})
    final = normalize_product(produto_final or {})
    mudancas: list[str] = []
    if antigo.get("nome_produto", "") != final.get("nome_produto", ""):
        mudancas.append("nome atualizado")
    if antigo.get("versao_produto", "") != final.get("versao_produto", ""):
        mudancas.append(f"versão: {antigo.get('versao_produto','-') or '-'} -> {final.get('versao_produto','-') or '-'}")
    if antigo.get("observacao", "") != final.get("observacao", ""):
        mudancas.append("observação alterada")
    if antigo.get("categoria_nome", "") != final.get("categoria_nome", ""):
        mudancas.append(f"categoria: {antigo.get('categoria_nome','-') or '-'} -> {final.get('categoria_nome','-') or '-'}")
    return mudancas
