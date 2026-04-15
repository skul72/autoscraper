from __future__ import annotations

import math

from app.adapters.ultrapackv2_plugin import build_page_candidates
from app.config.settings import MAX_PAGINAS_FALLBACK, TEST_MODE, TESTE_MAX_ITENS_POR_CATEGORIA
from app.scraper.flow_helpers import checar_pause_stop, safe_goto
from app.core.utils import normalizar_espacos


async def coletar_total_itens_na_categoria(page):
    texto = await page.evaluate("""() => { const el = document.querySelector('.itens-total'); return el ? (el.innerText || el.textContent || '').trim() : ''; }""")
    import re
    m = re.search(r"(\d+)", normalizar_espacos(texto))
    return int(m.group(1)) if m else 0


async def coletar_cards_da_pagina(page, control, app):
    await checar_pause_stop(control, app)
    try:
        await page.wait_for_selector(".new-post-display.new-posts2, a.link-cover[href*='/item/']", timeout=10000)
    except Exception:
        return []
    itens = await page.evaluate("""() => Array.from(document.querySelectorAll('.new-post-display.new-posts2')).map(card => { const cover = card.querySelector("a.link-cover[href*='/item/']"); const titulo = card.querySelector("h2 a[href*='/item/']"); const link = (cover && cover.href) || (titulo && titulo.href) || ''; let nome = ''; if (titulo){ const c=titulo.cloneNode(true); c.querySelectorAll('.version').forEach(el=>el.remove()); nome=(c.innerText||c.textContent||'').replace(/\s+/g,' ').trim(); } const versaoEl=card.querySelector('.version'); const versao=versaoEl?(versaoEl.innerText||versaoEl.textContent||'').replace(/\s+/g,' ').trim():''; return {link_produto:link,nome_lista:nome,versao_lista:versao}; }).filter(i=>i.link_produto)""")
    unicos, vistos = [], set()
    for item in itens:
        link = normalizar_espacos(item.get("link_produto", ""))
        if link and link not in vistos:
            vistos.add(link)
            unicos.append(item)
    return unicos


async def coletar_itens_da_categoria(page, categoria, control, app):
    nome = categoria["categoria_nome"]
    url = categoria["categoria_url"]
    app.log(f"📂 Categoria: {nome}")
    itens_por_link = {}
    await safe_goto(page, build_page_candidates(url, 1)[0], control, app)
    total = await coletar_total_itens_na_categoria(page)
    itens_p1 = await coletar_cards_da_pagina(page, control, app)
    for item in itens_p1:
        item.update({"categoria_nome": nome, "categoria_url": url, "tipo": "plugin"})
        itens_por_link[item["link_produto"]] = item
    total_ref = total or len(itens_por_link)
    max_pag = min(max(1, math.ceil((total_ref or 1) / 128)), MAX_PAGINAS_FALLBACK)
    for numero in range(2, max_pag + 1):
        await checar_pause_stop(control, app)
        if TEST_MODE and TESTE_MAX_ITENS_POR_CATEGORIA and len(itens_por_link) >= TESTE_MAX_ITENS_POR_CATEGORIA:
            break
        encontrou = False
        for cand in build_page_candidates(url, numero):
            try:
                await safe_goto(page, cand, control, app)
                itens = await coletar_cards_da_pagina(page, control, app)
                if not itens:
                    continue
                before = len(itens_por_link)
                for item in itens:
                    item.update({"categoria_nome": nome, "categoria_url": url, "tipo": "plugin"})
                    itens_por_link[item["link_produto"]] = item
                if len(itens_por_link) > before:
                    encontrou = True
                    break
            except Exception:
                pass
        if not encontrou:
            break
    return list(itens_por_link.values())
