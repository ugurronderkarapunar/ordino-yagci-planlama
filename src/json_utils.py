"""JSON list alanları (gemi_id_list, makine_tipi_id_list)."""

from __future__ import annotations

import json
from typing import Any


def id_listesi(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        p = json.loads(value)
        if isinstance(p, list):
            return [int(x) for x in p]
        return [int(p)]
    except (ValueError, TypeError, json.JSONDecodeError):
        return []


def id_list_to_json(lst: list[int]) -> str:
    return json.dumps(lst)
