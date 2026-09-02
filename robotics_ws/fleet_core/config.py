"""Configuration loading for fleet agents."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

ROOT = os.environ.get(
    "SIH_PROJECT_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def project_path(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


def load_json(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def load_fleet_config(path: str = None) -> Dict[str, Any]:
    path = path or project_path("configs", "fleet_config.json")
    return load_json(path)


def load_map(path: str = None):
    from .warehouse import WarehouseMap
    path = path or project_path("configs", "warehouse_map.json")
    return WarehouseMap.load(path)
