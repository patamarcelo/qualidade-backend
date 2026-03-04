# <seu_app>/utils/storages_lookup.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

# Cache em memória do processo (gunicorn/uvicorn): 1x por worker
_STORAGES_MAP: Optional[Dict[int, str]] = None

def _storages_json_path() -> Path:
    """
    Ajuste o Path aqui conforme sua estrutura de pastas.
    Este arquivo fica em: <seu_app>/utils/data/storages.json
    """
    return Path(__file__).resolve().parent / "data" / "storages.json"

def load_storages_map(force_reload: bool = False) -> Dict[int, str]:
    global _STORAGES_MAP
    if _STORAGES_MAP is not None and not force_reload:
        return _STORAGES_MAP

    p = _storages_json_path()
    if not p.exists():
        _STORAGES_MAP = {}
        return _STORAGES_MAP

    data: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8")) or {}

    # aceita tanto {"storages":[...]} quanto uma lista direta [...]
    items = data.get("storages", data if isinstance(data, list) else []) or []

    m: Dict[int, str] = {}
    for s in items:
        try:
            sid = int(s.get("id"))
            name = str(s.get("name") or "").strip()
            if sid and name:
                m[sid] = name
        except Exception:
            continue

    _STORAGES_MAP = m
    return m

def resolve_storage_name(storage_id: Any) -> Optional[str]:
    """
    Recebe storage_id (str/int) e retorna name ou None.
    """
    try:
        sid = int(storage_id)
    except Exception:
        return None

    m = load_storages_map(force_reload=False)
    return m.get(sid)