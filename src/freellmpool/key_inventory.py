"""Safe local inventory of manually-created provider keys.

The inventory is metadata only by default: it tracks which provider keys exist,
where they live (env var name), optional dates and notes. Secret values should
stay in env vars, config.toml, a shell profile, or a real secret manager.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bsk-or-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bcsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bnvapi-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{8,}\b"),
]


def redact_secrets(text: str) -> str:
    """Return text with common API-key shapes redacted."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def default_inventory_path() -> Path:
    override = os.environ.get("FREELLMPOOL_KEYS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "freellmpool" / "keys.toml"


@dataclass(frozen=True)
class KeyRecord:
    provider: str
    env_var: str | None = None
    label: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    commercial_allowed: bool | None = None
    notes: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> KeyRecord:
        return cls(
            provider=str(row.get("provider", "")).strip(),
            env_var=_optional_str(row.get("env_var")),
            label=_optional_str(row.get("label")),
            created_at=_optional_date(row.get("created_at")),
            expires_at=_optional_date(row.get("expires_at")),
            commercial_allowed=_optional_bool(row.get("commercial_allowed")),
            notes=_optional_str(row.get("notes")),
        )

    @property
    def display_label(self) -> str:
        return self.label or self.env_var or self.provider

    def safe_notes(self) -> str | None:
        if self.notes is None:
            return None
        return redact_secrets(self.notes)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _optional_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def load_inventory(path: Path | None = None) -> list[KeyRecord]:
    """Load [[keys]] records from TOML. Missing or invalid files return []."""
    path = path or default_inventory_path()
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        return []
    records = []
    for row in data.get("keys", []):
        if not isinstance(row, dict):
            continue
        record = KeyRecord.from_row(row)
        if record.provider:
            records.append(record)
    return records


def records_by_provider(records: list[KeyRecord]) -> dict[str, list[KeyRecord]]:
    grouped: dict[str, list[KeyRecord]] = {}
    for record in records:
        grouped.setdefault(record.provider, []).append(record)
    return grouped


def default_config_path() -> Path:
    override = os.environ.get("FREELLMPOOL_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "freellmpool" / "config.toml"


def upsert_config_key(env_var: str, value: str, path: Path | None = None) -> Path:
    """Write one [keys] value to config.toml and return the path.

    This small writer preserves existing top-level tables that we understand,
    but does not preserve comments. It is used by the interactive CLI helper.
    """
    path = path or default_config_path()
    data: dict[str, dict] = {}
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
        data = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        data = {}
    keys = dict(data.get("keys", {}))
    keys[env_var] = value
    data["keys"] = keys
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_simple_toml(data), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def append_inventory_record(record: KeyRecord, path: Path | None = None) -> Path:
    """Append a metadata record to keys.toml unless the same provider/env exists."""
    path = path or default_inventory_path()
    records = load_inventory(path)
    exists = any(r.provider == record.provider and r.env_var == record.env_var for r in records)
    if not exists:
        records.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_inventory(records), encoding="utf-8")
    return path


def _dump_inventory(records: list[KeyRecord]) -> str:
    chunks = []
    for record in records:
        lines = ["[[keys]]", f'provider = "{_toml_escape(record.provider)}"']
        for name in ("env_var", "label", "created_at", "expires_at", "notes"):
            value = getattr(record, name)
            if value:
                lines.append(f'{name} = "{_toml_escape(value)}"')
        if record.commercial_allowed is not None:
            lines.append(f"commercial_allowed = {str(record.commercial_allowed).lower()}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def _dump_simple_toml(data: dict[str, dict]) -> str:
    chunks = []
    for table, values in data.items():
        lines = [f"[{table}]"]
        for key, value in values.items():
            lines.append(f'{key} = {_toml_value(value)}')
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    return f'"{_toml_escape(str(value))}"'


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
