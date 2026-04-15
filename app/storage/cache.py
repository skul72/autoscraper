from __future__ import annotations

from app.core.utils import ensure_trailing_slash, normalizar_espacos, to_int
from app.storage.files import read_json, write_json_atomic
from app.storage.paths import categories_cache_path, queue_cache_path


def load_categories_cache(slot_name: str) -> dict:
    data = read_json(categories_cache_path(slot_name), {"categories": {}})
    if not isinstance(data, dict):
        data = {"categories": {}}
    if not isinstance(data.get("categories"), dict):
        data["categories"] = {}
    return data


def load_queue_cache(slot_name: str) -> dict:
    data = read_json(queue_cache_path(slot_name), {"categories": {}})
    if not isinstance(data, dict):
        data = {"categories": {}}
    if not isinstance(data.get("categories"), dict):
        data["categories"] = {}
    return data


def save_categories_cache(slot_name: str, cache: dict) -> None:
    write_json_atomic(categories_cache_path(slot_name), cache)


def save_queue_cache(slot_name: str, cache: dict) -> None:
    write_json_atomic(queue_cache_path(slot_name), cache)


def normalize_available_categories(categorias: list[dict]) -> list[dict]:
    resultado: list[dict] = []
    vistos: set[str] = set()
    for cat in categorias or []:
        raw_url = normalizar_espacos(cat.get("url") or cat.get("categoria_url", ""))
        url = ensure_trailing_slash(raw_url) if raw_url else ""
        nome = normalizar_espacos(cat.get("nome") or cat.get("categoria_nome", ""))
        if not url or url in vistos:
            continue
        vistos.add(url)
        resultado.append({"nome": nome or url, "url": url, "total": to_int(cat.get("total", 0), 0)})
    return sorted(resultado, key=lambda x: normalizar_espacos(x.get("nome", "")).lower())


def save_available_categories(slot_name: str, categorias: list[dict]) -> None:
    cache = load_categories_cache(slot_name)
    cache["available_categories"] = normalize_available_categories(categorias)
    save_categories_cache(slot_name, cache)


def load_available_categories(slot_name: str) -> list[dict]:
    cache = load_categories_cache(slot_name)
    saved = normalize_available_categories(cache.get("available_categories", []))
    if saved:
        return saved
    derived = normalize_available_categories([
        {
            "nome": item.get("categoria_nome", ""),
            "url": item.get("categoria_url", url),
            "total": item.get("total_esperado", item.get("total_coletado", 0)),
        }
        for url, item in (cache.get("categories", {}) or {}).items()
    ])
    return derived
