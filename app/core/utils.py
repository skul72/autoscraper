from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def to_int(valor, default: int = 0) -> int:
    try:
        return int(valor)
    except Exception:
        return default


def normalizar_espacos(texto) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip()


def formatar_duracao_segundos(total_segundos: int) -> str:
    total_segundos = max(0, int(total_segundos or 0))
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    segundos = total_segundos % 60
    return f"{horas}:{minutos:02d}:{segundos:02d}"


def agora_iso() -> str:
    return datetime.now().isoformat()


def calcular_timer_segundos(run_started_at: str, run_finished_at: str | None = None) -> int:
    if not run_started_at:
        return 0
    try:
        inicio = datetime.fromisoformat(run_started_at)
    except Exception:
        return 0
    if run_finished_at:
        try:
            fim = datetime.fromisoformat(run_finished_at)
        except Exception:
            fim = datetime.now()
    else:
        fim = datetime.now()
    return max(0, int((fim - inicio).total_seconds()))


def set_query_param(url: str, **params) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for k, v in params.items():
        query[k] = str(v)
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def ensure_trailing_slash(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


def limpar_versao(versao: str) -> str:
    versao = normalizar_espacos(versao)
    if not versao:
        return ""
    versao = re.sub(r"^\s*vers[aã]o\s*:\s*", "", versao, flags=re.IGNORECASE).strip()
    versao = versao.replace(",", ".")
    versao = re.sub(r"\s+", "", versao).strip(" .-_")
    m = re.search(r"(?<!\d)(\d+(?:\.\d+){1,5})(?!\d)", versao)
    if m:
        return m.group(1)
    versao = re.sub(r"[^0-9A-Za-z.\-_]+", "", versao)
    return versao.strip(" .-_")


def normalizar_item_fila(item: dict) -> dict:
    return {
        "tipo": normalizar_espacos(item.get("tipo", "")) or "plugin",
        "categoria_nome": normalizar_espacos(item.get("categoria_nome", "")),
        "categoria_url": ensure_trailing_slash(normalizar_espacos(item.get("categoria_url", ""))),
        "link_produto": normalizar_espacos(item.get("link_produto", "")),
        "nome_lista": normalizar_espacos(item.get("nome_lista", "")),
        "versao_lista": normalizar_espacos(item.get("versao_lista", "")),
    }


def calcular_links_signature(itens_categoria: list[dict]) -> tuple[str, int]:
    links = sorted(
        {
            normalizar_espacos(item.get("link_produto", ""))
            for item in itens_categoria
            if normalizar_espacos(item.get("link_produto", ""))
        }
    )
    assinatura = hashlib.sha1("\n".join(links).encode("utf-8")).hexdigest()
    return assinatura, len(links)
