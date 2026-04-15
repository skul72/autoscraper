from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.utils import limpar_versao, normalizar_espacos
from app.scraper.flow_helpers import aguardar, checar_pause_stop, safe_goto


def slug_para_nome(url):
    try:
        slug = urlparse(url).path.strip("/").split("/")[-1]
        return normalizar_espacos(slug.replace("-", " "))
    except Exception:
        return ""


def nome_parece_invalido(nome):
    n = normalizar_espacos(nome).lower()
    ruins = {"", "www.ultrapackv2.com", "ultrapackv2.com", "https://www.ultrapackv2.com", "http://www.ultrapackv2.com"}
    return n in ruins or n.startswith(("http://", "https://", "www.")) or len(n) < 3


def limpar_nome_final(nome):
    return normalizar_espacos(str(nome).replace("–", "-"))


def montar_observacao(classes, texto):
    classes = normalizar_espacos(classes); texto = normalizar_espacos(texto)
    if classes and texto:
        return f"{classes} | {texto}"
    return texto or classes or ""


async def extrair_detalhes_brutos(page):
    return await page.evaluate("""() => { function txt(sel){ const el=document.querySelector(sel); return el ? (el.innerText||el.textContent||'').replace(/\s+/g,' ').trim() : ''; } function attr(sel,a){ const el=document.querySelector(sel); return el ? (el.getAttribute(a)||'').trim() : ''; } let nome_h1=''; for(const sel of ['.single-post-item-detail h1','article.post h1','#content article h1','h1']){ nome_h1=txt(sel); if(nome_h1) break; } let versao=''; for(const el of Array.from(document.querySelectorAll('.inline-block-tag'))){ const t=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim(); if(/^vers[aã]o:/i.test(t)){ const v=el.querySelector('.item-desc-value'); versao=v?(v.innerText||v.textContent||'').replace(/\s+/g,' ').trim():t.replace(/^vers[aã]o:/i,'').trim(); break; } } return { page_url: location.href, nome_h1, versao, img_alt: attr('.single-post-item-img img','alt'), og_title: attr("meta[property='og:title']",'content'), observacao:'', observacao_classes:''}; }""")


def escolher_nome_final(url, item, dados):
    for cand in [dados.get("nome_h1", ""), dados.get("img_alt", ""), dados.get("og_title", ""), item.get("nome_lista", ""), slug_para_nome(url)]:
        cand = limpar_nome_final(cand)
        if not nome_parece_invalido(cand):
            return cand
    return ""


async def extrair_detalhes_do_item(page, item, control, app):
    url = item["link_produto"]
    for tentativa in range(1, 4):
        await checar_pause_stop(control, app)
        try:
            await safe_goto(page, url, control, app); await aguardar(1.0)
            dados = await extrair_detalhes_brutos(page)
            nome = escolher_nome_final(url, item, dados)
            if not nome_parece_invalido(nome):
                return {"tipo": item.get("tipo", "plugin"), "categoria_nome": item.get("categoria_nome", ""), "categoria_url": item.get("categoria_url", ""), "link_produto": url, "nome_produto": nome, "versao_produto": limpar_versao(dados.get("versao") or item.get("versao_lista") or ""), "observacao": montar_observacao(dados.get("observacao_classes", ""), dados.get("observacao", ""))}
        except Exception as e:
            app.log(f"⚠️ Erro na tentativa {tentativa} ao abrir item: {url} | {str(e)[:100]}")
            await aguardar(1.5)
    return {"tipo": item.get("tipo", "plugin"), "categoria_nome": item.get("categoria_nome", ""), "categoria_url": item.get("categoria_url", ""), "link_produto": url, "nome_produto": limpar_nome_final(item.get("nome_lista", "") or slug_para_nome(url)), "versao_produto": limpar_versao(item.get("versao_lista", "")), "observacao": ""}
