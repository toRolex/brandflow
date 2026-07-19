from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

_CATALOG_PATH = Path(__file__).with_name("catalog.json")

with _CATALOG_PATH.open(encoding="utf-8") as _fh:
    _DATA: dict = json.load(_fh)


def default_provider_document() -> dict:
    return deepcopy(_DATA["default_document"])


def provider_options_payload() -> dict:
    return deepcopy(_DATA["provider_options"])
