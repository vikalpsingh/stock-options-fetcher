from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import SecurityMapping
from .normalizer import build_alias_index, normalize_company_name
from .seed_security_map import build_seed_security_map


def default_security_map_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "security_map" / "company_security_map.json"


def default_audit_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "security_map" / "company_security_map_audit.jsonl"


def _model_dump(mapping: SecurityMapping) -> dict[str, Any]:
    return mapping.to_dict() if hasattr(mapping, "to_dict") else dict(mapping)


def load_security_map(path: str | Path | None = None, include_seed: bool = True) -> dict[str, SecurityMapping]:
    maps: dict[str, SecurityMapping] = build_seed_security_map() if include_seed else {}
    file_path = Path(path) if path else default_security_map_path()
    if not file_path.exists():
        return maps
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return maps
    rows = data.get("mappings") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return maps
    for item in rows:
        if not isinstance(item, dict):
            continue
        if hasattr(SecurityMapping, "model_validate"):
            mapping = SecurityMapping.model_validate(item)
        else:
            mapping = SecurityMapping.parse_obj(item)
        key = normalize_company_name(mapping.canonical_name)
        if key:
            maps[key] = mapping
    return maps


def save_security_map(
    security_map: dict[str, SecurityMapping],
    path: str | Path | None = None,
    audit_path: str | Path | None = None,
) -> Path:
    file_path = Path(path) if path else default_security_map_path()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if file_path.exists():
        backup = file_path.with_suffix(f".{datetime.now().strftime('%Y%m%d%H%M%S')}.bak")
        shutil.copy2(file_path, backup)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mappings": [_model_dump(mapping) for mapping in security_map.values()],
    }
    fd, temp_name = tempfile.mkstemp(prefix=file_path.name, suffix=".tmp", dir=str(file_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, file_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    append_security_map_audit("save", {"path": str(file_path), "count": len(security_map)}, audit_path)
    return file_path


def append_security_map_audit(action: str, details: dict[str, Any], audit_path: str | Path | None = None) -> None:
    file_path = Path(audit_path) if audit_path else default_audit_path()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "details": details,
    }
    with file_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def get_security_mapping(company_name: Any, path: str | Path | None = None) -> SecurityMapping | None:
    security_map = load_security_map(path)
    key = normalize_company_name(company_name)
    if key in security_map:
        return security_map[key]
    alias_index = build_alias_index()
    canonical = alias_index.get(key)
    if canonical:
        return security_map.get(normalize_company_name(canonical))
    return None


def upsert_security_mapping(mapping: SecurityMapping, path: str | Path | None = None) -> Path:
    security_map = load_security_map(path)
    security_map[normalize_company_name(mapping.canonical_name)] = mapping
    append_security_map_audit("upsert", _model_dump(mapping))
    return save_security_map(security_map, path)
