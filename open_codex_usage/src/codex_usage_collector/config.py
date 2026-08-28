from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class HostConfig:
    hostname: str
    user: str | None = None
    key_path: Path | None = None
    port: int | None = None


@dataclass(frozen=True)
class StorageConfig:
    type: str
    path: Path


@dataclass(frozen=True)
class ModelCostConfig:
    url: str | None = None


@dataclass(frozen=True)
class CreditMappingConfig:
    path: Path | None = None


@dataclass(frozen=True)
class CreditLimitConfig:
    weekly_limit: float | None = None
    end_of_week: str = "Friday"
    reset_time: str = "00:00"
    roll_over: bool = False


@dataclass(frozen=True)
class LocalConfig:
    enabled: bool = False
    hostname: str | None = None
    paths: list[str] | None = None


@dataclass(frozen=True)
class AppConfig:
    hosts: list[HostConfig]
    paths: list[str]
    storage: StorageConfig
    model_cost: ModelCostConfig = ModelCostConfig()
    credit_mapping: CreditMappingConfig = CreditMappingConfig()
    credit_limit: CreditLimitConfig = CreditLimitConfig()
    local: LocalConfig = LocalConfig()


def load_config(config_path: Path) -> AppConfig:
    raw_config = _load_yaml(config_path)
    hosts = [
        host
        for item in _optional_list(raw_config, "hosts")
        if (host := _parse_host_config(item)) is not None
    ]
    paths = [str(path) for path in _require_list(raw_config, "paths")]
    storage = _parse_storage_config(_require_mapping(raw_config, "storage"), config_path)
    model_cost = _parse_model_cost_config(raw_config.get("model_cost"))
    credit_mapping = _parse_credit_mapping_config(raw_config.get("credit_mapping"), config_path)
    credit_limit = _parse_credit_limit_config(raw_config.get("credit_limit"))
    local = _parse_local_config(raw_config.get("local"))
    if not hosts and not local.enabled:
        raise ValueError("Config must enable local collection or define at least one host")
    return AppConfig(
        hosts=hosts,
        paths=paths,
        storage=storage,
        model_cost=model_cost,
        credit_mapping=credit_mapping,
        credit_limit=credit_limit,
        local=local,
    )


def _load_yaml(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {config_path}")
    return data


def _parse_host_config(raw_host: Any) -> HostConfig | None:
    if not isinstance(raw_host, dict):
        raise ValueError("Each host entry must be a mapping")
    hostname = _require_string(raw_host, "hostname")
    if _is_placeholder_hostname(hostname):
        return None
    user = _optional_string(raw_host.get("user"))
    raw_key_path = _optional_string(raw_host.get("key_path"))
    key_path = Path(raw_key_path).expanduser() if raw_key_path else None
    port = raw_host.get("port")
    if port is not None and not isinstance(port, int):
        raise ValueError(f"Host {hostname} port must be an integer")
    return HostConfig(hostname=hostname, user=user, key_path=key_path, port=port)


def _is_placeholder_hostname(hostname: str) -> bool:
    return hostname.strip().lower() in {"none", "null", "local", "localhost"}


def _parse_storage_config(raw_storage: dict[str, Any], config_path: Path) -> StorageConfig:
    storage_type = _require_string(raw_storage, "type")
    if storage_type != "parquet":
        raise ValueError(f"Unsupported storage type: {storage_type}")
    raw_path = Path(_require_string(raw_storage, "path")).expanduser()
    resolved_path = raw_path if raw_path.is_absolute() else (config_path.parent / raw_path).resolve()
    return StorageConfig(type=storage_type, path=resolved_path)


def _parse_model_cost_config(raw_model_cost: Any) -> ModelCostConfig:
    if raw_model_cost is None:
        return ModelCostConfig()
    if not isinstance(raw_model_cost, dict):
        raise ValueError("Config key 'model_cost' must be a mapping")
    return ModelCostConfig(url=_optional_string(raw_model_cost.get("url")))


def _parse_credit_mapping_config(raw_credit_mapping: Any, config_path: Path) -> CreditMappingConfig:
    if raw_credit_mapping is None:
        return CreditMappingConfig()
    if not isinstance(raw_credit_mapping, dict):
        raise ValueError("Config key 'credit_mapping' must be a mapping")
    raw_path = _optional_string(raw_credit_mapping.get("path"))
    if raw_path is None:
        return CreditMappingConfig()
    path = Path(raw_path).expanduser()
    resolved_path = path if path.is_absolute() else (config_path.parent / path).resolve()
    return CreditMappingConfig(path=resolved_path)


def _parse_credit_limit_config(raw_credit_limit: Any) -> CreditLimitConfig:
    if raw_credit_limit is None:
        return CreditLimitConfig()
    if not isinstance(raw_credit_limit, dict):
        raise ValueError("Config key 'credit_limit' must be a mapping")
    weekly_limit = raw_credit_limit.get("weekly_limit")
    end_of_week, reset_time = _parse_reset_schedule(raw_credit_limit.get("end_of_week", "Friday"))
    roll_over = _optional_bool(raw_credit_limit.get("roll_over"), default=False)
    if weekly_limit is None:
        return CreditLimitConfig(end_of_week=end_of_week, reset_time=reset_time, roll_over=roll_over)
    if isinstance(weekly_limit, bool) or not isinstance(weekly_limit, int | float):
        raise ValueError("Config key 'credit_limit.weekly_limit' must be a number")
    return CreditLimitConfig(
        weekly_limit=float(weekly_limit),
        end_of_week=end_of_week,
        reset_time=reset_time,
        roll_over=roll_over,
    )


def _parse_local_config(raw_local: Any) -> LocalConfig:
    if raw_local is None:
        return LocalConfig(enabled=True)
    if not isinstance(raw_local, dict):
        raise ValueError("Config key 'local' must be a mapping")
    enabled = raw_local.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("Config key 'local.enabled' must be a boolean")
    hostname = _optional_string(raw_local.get("hostname"))
    raw_paths = raw_local.get("paths")
    paths: list[str] | None = None
    if raw_paths is not None:
        if not isinstance(raw_paths, list) or not all(isinstance(path, str) for path in raw_paths):
            raise ValueError("Config key 'local.paths' must be a list of strings")
        paths = [path for path in raw_paths if path.strip()]
    return LocalConfig(enabled=enabled, hostname=hostname, paths=paths)


def _require_mapping(raw_config: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw_config.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Config key '{key}' must be a mapping")
    return value


def _require_list(raw_config: dict[str, Any], key: str) -> list[Any]:
    value = raw_config.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Config key '{key}' must be a non-empty list")
    return value


def _optional_list(raw_config: dict[str, Any], key: str) -> list[Any]:
    value = raw_config.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"Config key '{key}' must be a list")
    return value


def _require_string(raw_config: dict[str, Any], key: str) -> str:
    value = raw_config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config key '{key}' must be a non-empty string")
    return value


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("Config key 'credit_limit.roll_over' must be a boolean")


def _parse_reset_schedule(value: Any) -> tuple[str, str]:
    raw_value = _optional_string(value)
    if raw_value is None:
        raise ValueError("Config key 'credit_limit.end_of_week' must be a weekday name")
    parts = [part.strip() for part in raw_value.split(",", maxsplit=1)]
    weekday = _parse_weekday(parts[0])
    reset_time = _parse_reset_time(parts[1]) if len(parts) > 1 else "00:00"
    return weekday, reset_time


def _parse_reset_time(value: str) -> str:
    pieces = value.split(":")
    if len(pieces) != 2 or not all(piece.isdigit() for piece in pieces):
        raise ValueError("Config key 'credit_limit.end_of_week' time must be HH:MM")
    hour = int(pieces[0])
    minute = int(pieces[1])
    if hour > 23 or minute > 59:
        raise ValueError("Config key 'credit_limit.end_of_week' time must be HH:MM")
    return f"{hour:02d}:{minute:02d}"


def _parse_weekday(value: Any) -> str:
    weekday = _optional_string(value)
    if weekday is None:
        raise ValueError("Config key 'credit_limit.end_of_week' must be a weekday name")
    normalized = weekday.strip().lower()
    weekdays = {
        "monday": "Monday",
        "tuesday": "Tuesday",
        "wednesday": "Wednesday",
        "thursday": "Thursday",
        "friday": "Friday",
        "saturday": "Saturday",
        "sunday": "Sunday",
    }
    try:
        return weekdays[normalized]
    except KeyError as exc:
        raise ValueError("Config key 'credit_limit.end_of_week' must be a weekday name") from exc
