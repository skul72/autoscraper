from __future__ import annotations

import asyncio
import time

from app.adapters.ultrapackv2_plugin import BASE_URL
from app.browser.auth import tentar_login
from app.browser.session import close_browser_session, open_browser_session
from app.config.settings import DEFAULT_SAVE_EVERY_ITEMS, DEFAULT_SAVE_EVERY_MINUTES, TEST_MODE, TESTE_MAX_CATEGORIAS
from app.core.constants import (
    RUN_MODE_CATEGORIES_ONLY,
    RUN_MODE_EXISTING_REVIEW,
    RUN_MODE_FULL,
    RUN_MODE_LABELS,
    RUN_MODE_LINKS_ONLY,
    RUN_MODE_SELECTED_SYNC,
)
from app.core.exceptions import StopScraper
from app.core.utils import agora_iso, ensure_trailing_slash, normalizar_espacos, normalizar_item_fila, to_int
from app.scraper.categories import coletar_categorias_plugins
from app.scraper.details import extrair_detalhes_do_item
from app.scraper.flow_helpers import checar_pause_stop, safe_goto
from app.scraper.items import coletar_itens_da_categoria
from app.storage.cache import (
    load_available_categories,
    load_categories_cache,
    load_queue_cache,
    normalize_available_categories,
    save_available_categories,
    save_categories_cache,
    save_queue_cache,
)
from app.storage.catalog import (
    describe_product_changes,
    get_resume_info,
    load_existing_products,
    merge_product,
    save_state,
)
from app.storage.files import read_json
from app.storage.paths import progress_json_path
from app.storage.status import save_full_log_txt


def filtrar_categorias_por_escopo(categorias, run_options):
    scope_mode = run_options.get("scope_mode", "all")
    if scope_mode == "all":
        return categorias
    if scope_mode == "range":
        start = max(1, to_int(run_options.get("scope_start", 1), 1))
        end = to_int(run_options.get("scope_end", 0), 0) or len(categorias)
        if end < start:
            end = start
        return categorias[start - 1 : end]
    if scope_mode == "match":
        import re

        raw = run_options.get("scope_match_text", "") or ""
        termos = [normalizar_espacos(x).lower() for x in re.split(r"[\n,;]+", raw) if normalizar_espacos(x)]
        if not termos:
            return categorias
        return [c for c in categorias if any(t in normalizar_espacos(c.get("categoria_nome", "")).lower() or t in normalizar_espacos(c.get("categoria_url", "")).lower() for t in termos)]
    if scope_mode == "selected":
        selecionadas = {ensure_trailing_slash(normalizar_espacos(x)) for x in (run_options.get("selected_categories", []) or []) if normalizar_espacos(x)}
        return [c for c in categorias if ensure_trailing_slash(c.get("categoria_url", "")) in selecionadas]
    return categorias


def categoria_cache_valida_normal(categoria_atual, category_cache, queue_cache):
    key = ensure_trailing_slash(categoria_atual["categoria_url"])
    meta = category_cache.get("categories", {}).get(key)
    fila = queue_cache.get("categories", {}).get(key)
    if not meta or not fila:
        return False, "sem cache"
    total_atual = int(categoria_atual.get("total_esperado", 0))
    total_meta = int(meta.get("total_esperado", -1))
    total_coletado = int(meta.get("total_coletado", -1))
    itens = fila.get("itens", [])
    if not meta.get("catalogada"):
        return False, "cache incompleto"
    if total_atual != total_meta:
        return False, "quantidade do catálogo mudou"
    if total_atual != total_coletado:
        return False, "quantidade coletada não bate"
    if total_atual != len(itens):
        return False, "fila salva não bate"
    return True, "cache válido"


def salvar_cache_categoria_individual(category_cache, queue_cache, categoria, itens_categoria, origem, app):
    from app.core.utils import calcular_links_signature

    key = ensure_trailing_slash(categoria["categoria_url"])
    agora = agora_iso()
    links_signature, links_count = calcular_links_signature(itens_categoria)
    category_cache["categories"][key] = {
        "categoria_nome": categoria["categoria_nome"],
        "categoria_url": key,
        "total_esperado": int(categoria.get("total_esperado", 0)),
        "total_coletado": len(itens_categoria),
        "catalogada": True,
        "origem": origem,
        "links_signature": links_signature,
        "links_count": links_count,
        "ultima_verificacao_integridade": agora,
        "ultima_atualizacao": agora,
    }
    queue_cache["categories"][key] = {
        "categoria_nome": categoria["categoria_nome"],
        "categoria_url": key,
        "total_esperado": int(categoria.get("total_esperado", 0)),
        "total_coletado": len(itens_categoria),
        "links_signature": links_signature,
        "links_count": links_count,
        "itens": itens_categoria,
        "ultima_verificacao_integridade": agora,
        "ultima_atualizacao": agora,
    }
    save_categories_cache(app.get_current_slot(), category_cache)
    save_queue_cache(app.get_current_slot(), queue_cache)


async def atualizar_apenas_categorias(app):
    class PassiveControl:
        def should_stop(self): return False
        def is_paused(self): return False
        def is_running(self): return False

    passive = PassiveControl()
    p = browser = context = page = detail_page = None
    try:
        p, browser, context, page, detail_page = await open_browser_session()
        app.state.update(current_phase="Atualizando categorias", status="Rodando")
        app.log("📚 Atualizando a lista de categorias...")
        await safe_goto(page, BASE_URL, passive, app)
        logado = await tentar_login(page, BASE_URL, passive, app)
        if not logado:
            app.log("⚠️ Atualização de categorias abortada: login automático falhou.")
            return load_available_categories(app.get_current_slot())
        await asyncio.sleep(2)
        categorias = await coletar_categorias_plugins(page, passive, app)
        available_categories = normalize_available_categories([
            {"nome": cat.get("categoria_nome", ""), "url": cat.get("categoria_url", ""), "total": int(cat.get("total_esperado", 0) or 0)}
            for cat in categorias
        ])
        save_available_categories(app.get_current_slot(), available_categories)
        selecionadas_atuais = list(app.state.snapshot()["data"].get("selected_categories", []) or [])
        urls_disponiveis = {ensure_trailing_slash(cat.get("url", "")) for cat in available_categories if normalizar_espacos(cat.get("url", ""))}
        app.state.update(
            available_categories=available_categories,
            selected_categories=[ensure_trailing_slash(url) for url in selecionadas_atuais if normalizar_espacos(url) and ensure_trailing_slash(url) in urls_disponiveis],
            current_phase="Categorias atualizadas",
        )
        return available_categories
    finally:
        await close_browser_session(p, browser, page, detail_page)


async def abrir_contexto_logado(app, control):
    p, browser, context, page, detail_page = await open_browser_session()
    app.log(f"🔑 Acessando {BASE_URL}...")
    await safe_goto(page, BASE_URL, control, app)
    app.log("🔑 Tentando login...")
    logado = await tentar_login(page, BASE_URL, control, app)
    if not logado:
        app.log("⚠️ Login automático falhou. Faça login manualmente no navegador do Playwright e depois clique em Continuar.")
        control.pause()
        while control.is_paused():
            await asyncio.sleep(0.5)
            if control.should_stop():
                raise StopScraper()
    await asyncio.sleep(2)
    app.log(f"🌍 URL após login: {page.url}")
    return p, browser, context, page, detail_page


async def carregar_categorias_filtradas_online(app, control, page, run_options, force_selected=False):
    categorias = await coletar_categorias_plugins(page, control, app)
    if not categorias:
        app.log("❌ Nenhuma categoria de plugin encontrada.")
        return [], []
    available_categories = normalize_available_categories([
        {"nome": cat.get("categoria_nome", ""), "url": cat.get("categoria_url", ""), "total": int(cat.get("total_esperado", 0) or 0)} for cat in categorias
    ])
    save_available_categories(app.get_current_slot(), available_categories)
    selecionadas_atuais = list(app.state.snapshot()["data"].get("selected_categories", []) or [])
    urls_disponiveis = {ensure_trailing_slash(cat.get("url", "")) for cat in available_categories if cat.get("url")}
    app.state.update(
        available_categories=available_categories,
        selected_categories=[ensure_trailing_slash(url) for url in selecionadas_atuais if ensure_trailing_slash(url) in urls_disponiveis],
    )
    options = dict(run_options)
    if force_selected:
        options["scope_mode"] = "selected"
    return categorias, filtrar_categorias_por_escopo(categorias, options)


async def montar_fila_por_categorias(app, control, page, categorias, produtos_dict, verify_mode):
    category_cache = load_categories_cache(app.get_current_slot())
    queue_cache = load_queue_cache(app.get_current_slot())
    itens_processamento, links_processamento = [], set()
    categorias_reutilizadas = categorias_refeitas = itens_existentes_detectados = itens_novos_detectados = 0

    for i, categoria in enumerate(categorias, start=1):
        await checar_pause_stop(control, app)
        app.state.update(status="Rodando", current_phase="Montando fila", current_category=categoria["categoria_nome"], current_item="-")
        if verify_mode == "normal":
            valida, motivo = categoria_cache_valida_normal(categoria, category_cache, queue_cache)
            categorias_reutilizadas += 1 if valida else 0
            categorias_refeitas += 0 if valida else 1
            itens_categoria = await coletar_itens_da_categoria(page, categoria, control, app)
            salvar_cache_categoria_individual(category_cache, queue_cache, categoria, itens_categoria, "normal_checked_live" if valida else "normal_recatalogada", app)
        else:
            itens_categoria = await coletar_itens_da_categoria(page, categoria, control, app)
            categorias_refeitas += 1
            salvar_cache_categoria_individual(category_cache, queue_cache, categoria, itens_categoria, "complete_changed", app)

        for item in itens_categoria:
            link = normalizar_espacos(item.get("link_produto", ""))
            if not link or link in links_processamento:
                continue
            links_processamento.add(link)
            itens_processamento.append(normalizar_item_fila(item))
            if link in produtos_dict:
                itens_existentes_detectados += 1
            else:
                itens_novos_detectados += 1

        app.state.update(reused_categories=categorias_reutilizadas, refetched_categories=categorias_refeitas, queue_detected_count=len(itens_processamento), new_links_detected=itens_novos_detectados, existing_links_detected=itens_existentes_detectados)

    return {
        "items": itens_processamento,
        "categorias_reutilizadas": categorias_reutilizadas,
        "categorias_refeitas": categorias_refeitas,
        "itens_novos_detectados": itens_novos_detectados,
        "itens_existentes_detectados": itens_existentes_detectados,
    }


async def processar_detalhes_fila(app, control, detail_page, produtos_dict, fila_completa, itens_processamento, meta_base, counters_init=None, start_index=0):
    fila_completa = [normalizar_item_fila(x) for x in fila_completa if normalizar_espacos(x.get("link_produto", ""))]
    itens_processamento = [normalizar_item_fila(x) for x in itens_processamento if normalizar_espacos(x.get("link_produto", ""))]
    counters_init = counters_init or {}
    save_every_items = max(1, to_int(meta_base.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS), DEFAULT_SAVE_EVERY_ITEMS))
    save_every_minutes = max(1, to_int(meta_base.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES), DEFAULT_SAVE_EVERY_MINUTES))
    save_every_seconds = save_every_minutes * 60
    ultimo_save = time.time(); itens_desde_ultimo_save = 0
    itens_novos = to_int(counters_init.get("itens_novos_adicionados", 0), 0)
    itens_atualizados = to_int(counters_init.get("itens_atualizados", 0), 0)
    itens_sem_mudanca = to_int(counters_init.get("itens_sem_mudanca", 0), 0)
    processed_absolute = max(0, to_int(start_index, 0)); total_fila = len(fila_completa)

    save_state(app, produtos_dict, {**meta_base, "status": "em_andamento", "current_phase": "Extraindo detalhes", "resume_full_queue_items": fila_completa, "resume_queue_index": processed_absolute, "resume_queue_total": total_fila, "itens_novos_adicionados": itens_novos, "itens_atualizados": itens_atualizados, "itens_sem_mudanca": itens_sem_mudanca})

    try:
        for item in itens_processamento:
            await checar_pause_stop(control, app)
            produto_novo = await extrair_detalhes_do_item(detail_page, item, control, app)
            link = normalizar_espacos(produto_novo.get("link_produto", ""))
            existente = produtos_dict.get(link)
            if existente is None:
                produtos_dict[link] = produto_novo
                itens_novos += 1
            else:
                final = merge_product(existente, produto_novo)
                mudancas = describe_product_changes(existente, final)
                produtos_dict[link] = final
                if mudancas:
                    itens_atualizados += 1
                else:
                    itens_sem_mudanca += 1
            processed_absolute += 1
            itens_desde_ultimo_save += 1
            agora = time.time()
            if itens_desde_ultimo_save >= save_every_items or (agora - ultimo_save) >= save_every_seconds:
                save_state(app, produtos_dict, {**meta_base, "status": "em_andamento", "current_phase": "Extraindo detalhes", "resume_full_queue_items": fila_completa, "resume_queue_index": processed_absolute, "resume_queue_total": total_fila, "itens_novos_adicionados": itens_novos, "itens_atualizados": itens_atualizados, "itens_sem_mudanca": itens_sem_mudanca})
                ultimo_save = agora; itens_desde_ultimo_save = 0
    except StopScraper:
        save_state(app, produtos_dict, {**meta_base, "status": "interrompido", "current_phase": "Extraindo detalhes", "resume_full_queue_items": fila_completa, "resume_queue_index": processed_absolute, "resume_queue_total": total_fila, "itens_novos_adicionados": itens_novos, "itens_atualizados": itens_atualizados, "itens_sem_mudanca": itens_sem_mudanca})
        raise

    return {"itens_novos_adicionados": itens_novos, "itens_atualizados": itens_atualizados, "itens_sem_mudanca": itens_sem_mudanca, "processed_absolute": processed_absolute}


async def executar_continuacao(app, control, detail_page, produtos_dict, run_payload):
    progresso = read_json(progress_json_path(app.get_current_slot()), {})
    meta = progresso.get("meta", {}) or {}
    resume = get_resume_info(meta)
    if not resume["can_continue"]:
        app.log("⚠️ Não há continuação utilizável salva. Será iniciado um novo fluxo.")
        return None
    fila_completa = resume["full_queue"]
    queue_index = resume["queue_index"]
    review_processed = bool(run_payload.get("resume_review_processed", False))
    if review_processed:
        itens_processamento = list(fila_completa)
        start_index = 0
        counters_init = {"itens_novos_adicionados": 0, "itens_atualizados": 0, "itens_sem_mudanca": 0}
    else:
        itens_processamento = list(fila_completa[queue_index:])
        start_index = queue_index
        counters_init = {"itens_novos_adicionados": to_int(meta.get("itens_novos_adicionados", 0), 0), "itens_atualizados": to_int(meta.get("itens_atualizados", 0), 0), "itens_sem_mudanca": to_int(meta.get("itens_sem_mudanca", 0), 0)}
    if not itens_processamento:
        app.log("⚠️ Não há itens pendentes na fila de continuação.")
        return list(produtos_dict.values())

    meta_base = {"run_mode": resume["run_mode"], "modo_teste": TEST_MODE, "verify_mode": meta.get("verify_mode", "normal"), "scope_mode": meta.get("scope_mode", "all"), "save_every_items": max(1, to_int(meta.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS), DEFAULT_SAVE_EVERY_ITEMS)), "save_every_minutes": max(1, to_int(meta.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES), DEFAULT_SAVE_EVERY_MINUTES)), "categorias_reutilizadas": to_int(meta.get("categorias_reutilizadas", 0), 0), "categorias_refeitas": to_int(meta.get("categorias_refeitas", 0), 0), "queue_detected_count": len(fila_completa), "new_links_detected": to_int(meta.get("new_links_detected", 0), 0), "existing_links_detected": to_int(meta.get("existing_links_detected", 0), 0), "run_started_at": app.state.snapshot()["data"].get("run_started_at", "") or meta.get("run_started_at", ""), "run_finished_at": ""}

    detalhes = await processar_detalhes_fila(app, control, detail_page, produtos_dict, fila_completa, itens_processamento, meta_base, counters_init, start_index)
    save_state(app, produtos_dict, {**meta_base, "status": "concluido", "current_phase": "Finalizado", "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "itens_novos_adicionados": detalhes["itens_novos_adicionados"], "itens_atualizados": detalhes["itens_atualizados"], "itens_sem_mudanca": detalhes["itens_sem_mudanca"], "run_finished_at": agora_iso()})
    return list(produtos_dict.values())


async def executar_fluxo(app, run_options, run_mode, run_payload=None):
    run_payload = dict(run_payload or {})
    control = app.control
    produtos_dict = dict(load_existing_products(app.get_current_slot()))
    verify_mode = run_options.get("verify_mode", "normal")
    scope_mode = run_options.get("scope_mode", "all")
    save_every_items = max(1, to_int(run_options.get("save_every_items", DEFAULT_SAVE_EVERY_ITEMS), DEFAULT_SAVE_EVERY_ITEMS))
    save_every_minutes = max(1, to_int(run_options.get("save_every_minutes", DEFAULT_SAVE_EVERY_MINUTES), DEFAULT_SAVE_EVERY_MINUTES))

    app.state.update(summary=f"Itens já salvos ao iniciar: {len(produtos_dict)}", saved_count=len(produtos_dict), pending_count=0, running=True, status="Rodando", run_mode=run_mode, run_mode_label=RUN_MODE_LABELS.get(run_mode, run_mode), reused_categories=0, refetched_categories=0, queue_detected_count=0, new_links_detected=0, existing_links_detected=0, new_items_added=0, items_updated=0, items_unchanged=0, save_every_items=save_every_items, save_every_minutes=save_every_minutes)

    if run_mode == RUN_MODE_CATEGORIES_ONLY:
        categorias = await atualizar_apenas_categorias(app)
        save_state(app, produtos_dict, {"status": "concluido", "run_mode": RUN_MODE_CATEGORIES_ONLY, "current_phase": "Categorias atualizadas", "modo_teste": TEST_MODE, "verify_mode": verify_mode, "scope_mode": scope_mode, "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "run_started_at": app.state.snapshot()["data"].get("run_started_at", ""), "run_finished_at": agora_iso()})
        return list(produtos_dict.values())

    p = browser = context = page = detail_page = None
    try:
        p, browser, context, page, detail_page = await abrir_contexto_logado(app, control)
        if run_payload.get("resume"):
            resumed = await executar_continuacao(app, control, detail_page, produtos_dict, run_payload)
            if resumed is not None:
                return resumed

        force_selected = run_mode == RUN_MODE_SELECTED_SYNC
        todas_categorias, categorias_filtradas = await carregar_categorias_filtradas_online(app, control, page, run_options, force_selected=force_selected)
        if not todas_categorias:
            return list(produtos_dict.values())
        if TEST_MODE and TESTE_MAX_CATEGORIAS:
            categorias_filtradas = categorias_filtradas[:TESTE_MAX_CATEGORIAS]

        if run_mode in {RUN_MODE_FULL, RUN_MODE_LINKS_ONLY, RUN_MODE_SELECTED_SYNC}:
            fila_info = await montar_fila_por_categorias(app, control, page, categorias_filtradas, produtos_dict, verify_mode)
            meta_base = {"run_mode": run_mode, "modo_teste": TEST_MODE, "verify_mode": verify_mode, "scope_mode": "selected" if force_selected else scope_mode, "categorias_reutilizadas": fila_info["categorias_reutilizadas"], "categorias_refeitas": fila_info["categorias_refeitas"], "queue_detected_count": len(fila_info["items"]), "new_links_detected": fila_info["itens_novos_detectados"], "existing_links_detected": fila_info["itens_existentes_detectados"], "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "run_started_at": app.state.snapshot()["data"].get("run_started_at", ""), "run_finished_at": ""}
            if run_mode == RUN_MODE_LINKS_ONLY:
                save_state(app, produtos_dict, {**meta_base, "status": "concluido", "current_phase": "Detecção finalizada", "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "run_finished_at": agora_iso()})
                return list(produtos_dict.values())
            detalhes = await processar_detalhes_fila(app, control, detail_page, produtos_dict, fila_info["items"], fila_info["items"], meta_base, {"itens_novos_adicionados": 0, "itens_atualizados": 0, "itens_sem_mudanca": 0}, 0)
            save_state(app, produtos_dict, {**meta_base, "status": "concluido", "current_phase": "Finalizado", "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "itens_novos_adicionados": detalhes["itens_novos_adicionados"], "itens_atualizados": detalhes["itens_atualizados"], "itens_sem_mudanca": detalhes["itens_sem_mudanca"], "run_finished_at": agora_iso()})
            return list(produtos_dict.values())

        if run_mode == RUN_MODE_EXISTING_REVIEW:
            fila = [{"tipo": item.get("tipo", "plugin"), "categoria_nome": item.get("categoria_nome", ""), "categoria_url": item.get("categoria_url", ""), "link_produto": item.get("link_produto", ""), "nome_lista": item.get("nome_produto", ""), "versao_lista": item.get("versao_produto", "")} for item in produtos_dict.values()]
            meta_base = {"run_mode": run_mode, "modo_teste": TEST_MODE, "verify_mode": verify_mode, "scope_mode": scope_mode, "categorias_reutilizadas": 0, "categorias_refeitas": 0, "queue_detected_count": len(fila), "new_links_detected": 0, "existing_links_detected": len(fila), "save_every_items": save_every_items, "save_every_minutes": save_every_minutes, "run_started_at": app.state.snapshot()["data"].get("run_started_at", ""), "run_finished_at": ""}
            detalhes = await processar_detalhes_fila(app, control, detail_page, produtos_dict, fila, fila, meta_base, {"itens_novos_adicionados": 0, "itens_atualizados": 0, "itens_sem_mudanca": 0}, 0)
            save_state(app, produtos_dict, {**meta_base, "status": "concluido", "current_phase": "Revisão concluída", "resume_full_queue_items": [], "resume_queue_index": 0, "resume_queue_total": 0, "itens_novos_adicionados": detalhes["itens_novos_adicionados"], "itens_atualizados": detalhes["itens_atualizados"], "itens_sem_mudanca": detalhes["itens_sem_mudanca"], "run_finished_at": agora_iso()})
            return list(produtos_dict.values())

        return list(produtos_dict.values())
    except StopScraper:
        app.log("⏹ Processo interrompido pelo usuário.")
        save_full_log_txt(app)
        return list(produtos_dict.values())
    finally:
        await close_browser_session(p, browser, page, detail_page)
