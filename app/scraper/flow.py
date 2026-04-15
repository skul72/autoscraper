from __future__ import annotations

import time

from app.adapters.ultrapackv2_plugin import BASE_URL
from app.browser.auth import tentar_login
from app.browser.session import close_browser_session, open_browser_session
from app.config.settings import TEST_MODE, TESTE_MAX_CATEGORIAS
from app.core.constants import RUN_MODE_CATEGORIES_ONLY, RUN_MODE_EXISTING_REVIEW, RUN_MODE_FULL, RUN_MODE_LINKS_ONLY, RUN_MODE_SELECTED_SYNC
from app.core.exceptions import StopScraper
from app.core.utils import agora_iso, ensure_trailing_slash, normalizar_espacos, normalizar_item_fila
from app.scraper.categories import coletar_categorias_plugins
from app.scraper.details import extrair_detalhes_do_item
from app.scraper.flow_helpers import safe_goto, checar_pause_stop
from app.scraper.items import coletar_itens_da_categoria
from app.storage.cache import load_available_categories, normalize_available_categories, save_available_categories
from app.storage.catalog import get_resume_info, load_existing_products, merge_product, save_state
from app.storage.files import read_json
from app.storage.paths import progress_json_path
from app.storage.status import save_full_log_txt


async def atualizar_apenas_categorias(app):
    class PassiveControl:
        def should_stop(self): return False
        def is_paused(self): return False
        def is_running(self): return False

    passive = PassiveControl()
    p = browser = context = page = detail = None
    try:
        p, browser, context, page, detail = await open_browser_session()
        app.state.update(current_phase="Atualizando categorias", status="Rodando")
        app.log("📚 Atualizando a lista de categorias...")
        await safe_goto(page, BASE_URL, passive, app)
        if not await tentar_login(page, BASE_URL, passive, app):
            app.log("⚠️ Atualização de categorias abortada: login automático falhou.")
            return load_available_categories(app.get_current_slot())
        categorias = await coletar_categorias_plugins(page, passive, app)
        available = normalize_available_categories([{"nome": c.get("categoria_nome", ""), "url": c.get("categoria_url", ""), "total": int(c.get("total_esperado", 0) or 0)} for c in categorias])
        save_available_categories(app.get_current_slot(), available)
        selected = list(app.state.snapshot()["data"].get("selected_categories", []) or [])
        urls = {ensure_trailing_slash(c.get("url", "")) for c in available if c.get("url")}
        app.state.update(available_categories=available, selected_categories=[ensure_trailing_slash(u) for u in selected if ensure_trailing_slash(u) in urls], current_phase="Categorias atualizadas")
        return available
    finally:
        await close_browser_session(p, browser, page, detail)


async def _processar_fila(app, control, detail_page, produtos_dict, fila, meta_base):
    processed = 0
    counters = {"itens_novos_adicionados": 0, "itens_atualizados": 0, "itens_sem_mudanca": 0}
    save_state(app, produtos_dict, {**meta_base, "status": "em_andamento", "resume_full_queue_items": fila, "resume_queue_index": 0, "resume_queue_total": len(fila), **counters})
    for item in fila:
        await checar_pause_stop(control, app)
        produto_novo = await extrair_detalhes_do_item(detail_page, item, control, app)
        link = normalizar_espacos(produto_novo.get("link_produto", ""))
        existente = produtos_dict.get(link)
        if existente is None:
            produtos_dict[link] = produto_novo
            counters["itens_novos_adicionados"] += 1
        else:
            final = merge_product(existente, produto_novo)
            produtos_dict[link] = final
            if final != existente:
                counters["itens_atualizados"] += 1
            else:
                counters["itens_sem_mudanca"] += 1
        processed += 1
        if processed % int(meta_base.get("save_every_items", 5)) == 0:
            save_state(app, produtos_dict, {**meta_base, "status": "em_andamento", "resume_full_queue_items": fila, "resume_queue_index": processed, "resume_queue_total": len(fila), **counters})
    return counters


async def executar_fluxo(app, run_options, run_mode, run_payload=None):
    run_payload = dict(run_payload or {})
    control = app.control
    produtos_dict = dict(load_existing_products(app.get_current_slot()))
    verify_mode = run_options.get("verify_mode", "normal")
    scope_mode = run_options.get("scope_mode", "all")
    save_every_items = run_options.get("save_every_items", 5)
    save_every_minutes = run_options.get("save_every_minutes", 1)

    if run_mode == RUN_MODE_CATEGORIES_ONLY:
        await atualizar_apenas_categorias(app)
        save_state(app, produtos_dict, {"status": "concluido", "run_mode": run_mode, "current_phase": "Categorias atualizadas", "verify_mode": verify_mode, "scope_mode": scope_mode, "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "run_started_at": app.state.snapshot()["data"].get("run_started_at", ""), "run_finished_at": agora_iso()})
        return list(produtos_dict.values())

    p = browser = context = page = detail = None
    try:
        p, browser, context, page, detail = await open_browser_session()
        await safe_goto(page, BASE_URL, control, app)
        logado = await tentar_login(page, BASE_URL, control, app)
        if not logado:
            app.log("⚠️ Login automático falhou. Faça login manualmente no navegador do Playwright e depois clique em Continuar.")
            control.pause()
            while control.is_paused():
                await checar_pause_stop(control, app)
                time.sleep(0.5)

        if run_payload.get("resume"):
            progresso = read_json(progress_json_path(app.get_current_slot()), {})
            meta = progresso.get("meta", {}) or {}
            resume = get_resume_info(meta)
            if resume["can_continue"]:
                fila = [normalizar_item_fila(i) for i in resume["full_queue"][resume["queue_index"]:]]
                counters = await _processar_fila(app, control, detail, produtos_dict, fila, {"run_mode": resume["run_mode"], "verify_mode": verify_mode, "scope_mode": scope_mode, "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "run_started_at": app.state.snapshot()["data"].get("run_started_at", "")})
                save_state(app, produtos_dict, {"status": "concluido", "run_mode": resume["run_mode"], "current_phase": "Finalizado", "verify_mode": verify_mode, "scope_mode": scope_mode, "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "run_started_at": app.state.snapshot()["data"].get("run_started_at", ""), "run_finished_at": agora_iso(), **counters})
                return list(produtos_dict.values())

        categorias = await coletar_categorias_plugins(page, control, app)
        available = normalize_available_categories([{"nome": c.get("categoria_nome", ""), "url": c.get("categoria_url", ""), "total": int(c.get("total_esperado", 0) or 0)} for c in categorias])
        save_available_categories(app.get_current_slot(), available)

        if TEST_MODE and TESTE_MAX_CATEGORIAS:
            categorias = categorias[:TESTE_MAX_CATEGORIAS]

        fila = []
        seen = set()
        for categoria in categorias:
            itens = await coletar_itens_da_categoria(page, categoria, control, app)
            for item in itens:
                link = normalizar_espacos(item.get("link_produto", ""))
                if not link or link in seen:
                    continue
                seen.add(link)
                fila.append(normalizar_item_fila(item))

        if run_mode == RUN_MODE_LINKS_ONLY:
            save_state(app, produtos_dict, {"status": "concluido", "run_mode": run_mode, "current_phase": "Detecção finalizada", "verify_mode": verify_mode, "scope_mode": scope_mode, "queue_detected_count": len(fila), "new_links_detected": len([f for f in fila if f.get('link_produto') not in produtos_dict]), "existing_links_detected": len([f for f in fila if f.get('link_produto') in produtos_dict]), "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "run_started_at": app.state.snapshot()["data"].get("run_started_at", ""), "run_finished_at": agora_iso()})
            return list(produtos_dict.values())

        if run_mode == RUN_MODE_EXISTING_REVIEW:
            fila = [normalizar_item_fila({"tipo": i.get("tipo", "plugin"), "categoria_nome": i.get("categoria_nome", ""), "categoria_url": i.get("categoria_url", ""), "link_produto": i.get("link_produto", ""), "nome_lista": i.get("nome_produto", ""), "versao_lista": i.get("versao_produto", "")}) for i in produtos_dict.values()]

        counters = await _processar_fila(app, control, detail, produtos_dict, fila, {"run_mode": run_mode, "verify_mode": verify_mode, "scope_mode": scope_mode, "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "run_started_at": app.state.snapshot()["data"].get("run_started_at", "")})
        save_state(app, produtos_dict, {"status": "concluido", "run_mode": run_mode, "current_phase": "Finalizado", "verify_mode": verify_mode, "scope_mode": scope_mode, "queue_detected_count": len(fila), "new_links_detected": len([f for f in fila if f.get('link_produto') not in load_existing_products(app.get_current_slot())]), "existing_links_detected": len([f for f in fila if f.get('link_produto') in load_existing_products(app.get_current_slot())]), "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "run_started_at": app.state.snapshot()["data"].get("run_started_at", ""), "run_finished_at": agora_iso(), **counters})
        return list(produtos_dict.values())
    except StopScraper:
        app.log("⏹ Processo interrompido pelo usuário.")
        save_full_log_txt(app)
        return list(produtos_dict.values())
    finally:
        await close_browser_session(p, browser, page, detail)
