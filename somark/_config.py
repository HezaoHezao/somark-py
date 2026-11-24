from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable, Optional

# 国内站（默认）；国外站见 OFFICIAL_REGION_BASE_URLS["ai"]
DEFAULT_BASE_URL = "https://somark.cn/api/v1"
OXR_DEFAULT_BASE_URL = "https://free-oxr.somark.cn/api/v1"
OFFICIAL_REGION_BASE_URLS = {
    "cn": "https://somark.cn/api/v1",
    "ai": "https://somark.ai/api/v1",
}
OFFICIAL_REGION_WORKBENCH = {
    "cn": "https://somark.cn/workbench/apikey",
    "ai": "https://somark.ai/workbench/apikey",
}
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
VALID_ACTIVE_MODES = ("oxr", "api", "private")
# OXR free-tier hard limits (client-side guard; do not silently truncate)
OXR_MAX_FILE_BYTES = 10 * 1024 * 1024
OXR_MAX_PAGES = 20
OXR_ALLOWED_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".tif",
    ".jp2",
    ".dib",
    ".ppm",
    ".pgm",
    ".pbm",
    ".gif",
    ".heic",
    ".heif",
    ".webp",
    ".xpm",
    ".tga",
    ".dds",
    ".xbm",
}
CONFIG_DIR = Path.home() / ".somark"
CONFIG_FILE = CONFIG_DIR / "config.toml"
_ACTIVE_PROFILE: Optional[str] = None


def _pdf_page_count(path: Path) -> Optional[int]:
    try:
        import sopdf
    except ImportError:
        return None
    try:
        with sopdf.open(str(path)) as doc:
            return len(doc.pages)
    except Exception:
        return None


def enforce_oxr_input_limits(files: list[str]) -> None:
    """Refuse OXR parse when file exceeds free-tier limits (no silent truncation)."""
    from somark._exceptions import FileTooLargeError, UnsupportedFileError

    for raw in files:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix and suffix not in OXR_ALLOWED_SUFFIXES:
            raise UnsupportedFileError(
                f"OXR free tier does not support '{suffix}'. "
                "Switch to api (`somark use api` after login) or private for Office/other formats.",
                code=1104,
            )
        size = path.stat().st_size
        if size > OXR_MAX_FILE_BYTES:
            mb = size / (1024 * 1024)
            raise FileTooLargeError(
                f"OXR free tier limit is 10 MB / 20 pages; file is {mb:.2f} MB. "
                "Refuse to parse (will not truncate). Run: somark login && somark use api",
                code=1132,
            )
        if suffix == ".pdf":
            pages = _pdf_page_count(path)
            if pages is not None and pages > OXR_MAX_PAGES:
                raise FileTooLargeError(
                    f"OXR free tier limit is 10 MB / 20 pages; PDF has {pages} pages. "
                    "Refuse to parse (will not truncate). Run: somark login && somark use api",
                    code=1132,
                )


def config_file_for_profile(profile: Optional[str] = None) -> Path:
    if not profile or profile == "default":
        return CONFIG_DIR / "config.toml"
    return CONFIG_DIR / "profiles" / f"{profile}.toml"


def set_active_profile(profile: Optional[str]) -> Path:
    global CONFIG_FILE, _ACTIVE_PROFILE
    _ACTIVE_PROFILE = profile if profile and profile != "default" else None
    CONFIG_FILE = config_file_for_profile(profile)
    return CONFIG_FILE


def get_active_profile() -> Optional[str]:
    return _ACTIVE_PROFILE


ConfigParser = Callable[[Any], Any]
ConfigValidator = Callable[[str, Any], None]
ConfigMasker = Callable[[str], str]
ConfigFormatter = Callable[[Any], str]


@dataclass(frozen=True)
class ConfigEntry:
    key: str
    env_var: str
    option_key: str
    default: Any
    parser: ConfigParser
    validator: ConfigValidator
    masker: ConfigMasker
    formatter: ConfigFormatter
    show_when_unset: bool


def _parse_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _parse_str(value: Any) -> str:
    return str(value)


def _parse_float(value: Any) -> float:
    return float(value)


def _parse_int(value: Any) -> int:
    return int(value)


def _validate_any(_key: str, _value: Any) -> None:
    return None


def _validate_base_url(key: str, value: Any) -> None:
    if value is not None and not str(value).startswith(("http://", "https://")):
        raise ValueError(f'Invalid {key} "{value}". Must start with http:// or https://')


def _validate_active_mode(key: str, value: Any) -> None:
    if value is None or value == "":
        return
    if str(value) not in VALID_ACTIVE_MODES:
        raise ValueError(f'Invalid {key} "{value}". Must be one of: {", ".join(VALID_ACTIVE_MODES)}')


def _mask_identity(value: str) -> str:
    return value


def _mask_api_key(value: str) -> str:
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"


def _format_default(value: Any) -> str:
    return str(value)


def _format_float(value: Any) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


CONFIG_SCHEMA: tuple[ConfigEntry, ...] = (
    ConfigEntry(
        key="api_key",
        env_var="SOMARK_API_KEY",
        option_key="api_key",
        default=None,
        parser=_parse_optional_str,
        validator=_validate_any,
        masker=_mask_api_key,
        formatter=_format_default,
        show_when_unset=False,
    ),
    ConfigEntry(
        key="base_url",
        env_var="SOMARK_BASE_URL",
        option_key="base_url",
        default=DEFAULT_BASE_URL,
        parser=_parse_str,
        validator=_validate_base_url,
        masker=_mask_identity,
        formatter=_format_default,
        show_when_unset=True,
    ),
    ConfigEntry(
        key="timeout",
        env_var="SOMARK_TIMEOUT",
        option_key="timeout",
        default=DEFAULT_TIMEOUT,
        parser=_parse_float,
        validator=_validate_any,
        masker=_mask_identity,
        formatter=_format_float,
        show_when_unset=True,
    ),
    ConfigEntry(
        key="max_retries",
        env_var="SOMARK_MAX_RETRIES",
        option_key="max_retries",
        default=DEFAULT_MAX_RETRIES,
        parser=_parse_int,
        validator=_validate_any,
        masker=_mask_identity,
        formatter=_format_default,
        show_when_unset=True,
    ),
    ConfigEntry(
        key="private_base_url",
        env_var="SOMARK_PRIVATE_BASE_URL",
        option_key="private_base_url",
        default=None,
        parser=_parse_optional_str,
        validator=_validate_base_url,
        masker=_mask_identity,
        formatter=_format_default,
        show_when_unset=False,
    ),
    ConfigEntry(
        key="private_api_key",
        env_var="SOMARK_PRIVATE_API_KEY",
        option_key="private_api_key",
        default=None,
        parser=_parse_optional_str,
        validator=_validate_any,
        masker=_mask_api_key,
        formatter=_format_default,
        show_when_unset=False,
    ),
    ConfigEntry(
        key="active_mode",
        env_var="SOMARK_MODE",
        option_key="active_mode",
        default=None,
        parser=_parse_optional_str,
        validator=_validate_active_mode,
        masker=_mask_identity,
        formatter=_format_default,
        show_when_unset=True,
    ),
)

CONFIG_SCHEMA_BY_KEY = {entry.key: entry for entry in CONFIG_SCHEMA}
VALID_CONFIG_KEYS = set(CONFIG_SCHEMA_BY_KEY)


def _load_toml_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        import toml

        return toml.load(CONFIG_FILE)
    except Exception:
        return {}


def _resolve_entry(
    entry: ConfigEntry,
    *,
    explicit_options: dict[str, Any],
    file_cfg: dict,
) -> tuple[Any, str]:
    if entry.option_key in explicit_options and explicit_options[entry.option_key] is not None:
        raw_value = explicit_options[entry.option_key]
        source = "explicit"
    elif os.environ.get(entry.env_var):
        raw_value = os.environ[entry.env_var]
        source = "env"
    elif entry.key == "base_url" and os.environ.get("SOMARK_API_BASE_URL"):
        raw_value = os.environ["SOMARK_API_BASE_URL"]
        source = "env"
    elif file_cfg.get(entry.key) is not None:
        raw_value = file_cfg[entry.key]
        source = "file"
    else:
        raw_value = entry.default
        source = "default"

    value = entry.parser(raw_value)
    entry.validator(entry.key, value)
    return value, source


def _infer_active_mode(stored_mode: Optional[str], official_api_key: Optional[str]) -> str:
    if stored_mode in VALID_ACTIVE_MODES:
        return stored_mode
    return "api" if official_api_key else "oxr"


def _apply_active_mode(cfg: dict[str, Any], *, skip_credential_rewrite: bool) -> dict[str, Any]:
    official_key = cfg.get("api_key")
    mode = _infer_active_mode(cfg.get("active_mode"), official_key)
    cfg["active_mode"] = mode

    if skip_credential_rewrite:
        return cfg

    if mode == "oxr":
        cfg["base_url"] = OXR_DEFAULT_BASE_URL
        cfg["api_key"] = None
    elif mode == "api":
        if not cfg.get("base_url"):
            cfg["base_url"] = DEFAULT_BASE_URL
    elif mode == "private":
        private_url = cfg.get("private_base_url")
        private_key = cfg.get("private_api_key")
        if private_url:
            cfg["base_url"] = private_url
        cfg["api_key"] = private_key
    return cfg


def resolve_config(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> dict:
    file_cfg = _load_toml_config()
    explicit_options = {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    cfg = {
        entry.key: _resolve_entry(entry, explicit_options=explicit_options, file_cfg=file_cfg)[0]
        for entry in CONFIG_SCHEMA
    }
    skip_rewrite = api_key is not None or base_url is not None
    return _apply_active_mode(cfg, skip_credential_rewrite=skip_rewrite)


def has_official_api_key() -> bool:
    if os.environ.get("SOMARK_API_KEY"):
        return True
    return bool(_load_toml_config().get("api_key"))


def has_private_credentials() -> bool:
    """Private tier is ready once Base URL is set; API key is optional."""
    file_cfg = _load_toml_config()
    url = os.environ.get("SOMARK_PRIVATE_BASE_URL") or file_cfg.get("private_base_url")
    return bool(url)


def get_mode_readiness() -> dict[str, Any]:
    cfg = resolve_config()
    file_cfg = _load_toml_config()
    api_base = file_cfg.get("base_url") or DEFAULT_BASE_URL
    # 避免把 OXR 地址当成官网 API 站展示
    if "free-oxr" in str(api_base):
        api_base = DEFAULT_BASE_URL
    return {
        "active_mode": cfg["active_mode"],
        "oxr": {"ready": True, "base_url": OXR_DEFAULT_BASE_URL},
        "api": {"ready": has_official_api_key(), "base_url": api_base},
        "private": {
            "ready": has_private_credentials(),
            "base_url": cfg.get("private_base_url"),
        },
    }


def save_config(**kwargs) -> None:
    import toml

    for key, value in kwargs.items():
        entry = CONFIG_SCHEMA_BY_KEY.get(key)
        if entry is None:
            raise ValueError(f'Unknown config key "{key}". Valid keys: {", ".join(sorted(VALID_CONFIG_KEYS))}')
        if value is not None:
            parsed_value = entry.parser(value)
            entry.validator(key, parsed_value)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg = _load_toml_config()
    cfg.update({k: v for k, v in kwargs.items() if v is not None})
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        toml.dump(cfg, f)
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def clear_config(*keys: str) -> None:
    import toml

    if not keys:
        return
    cfg = _load_toml_config()
    changed = False
    for key in keys:
        if key in cfg:
            del cfg[key]
            changed = True
    if not changed and not CONFIG_FILE.exists():
        return
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        toml.dump(cfg, f)
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def get_config_value(key: str) -> Optional[str]:
    cfg = _load_toml_config()
    return cfg.get(key)


def mask_config_value(key: str, value: str) -> str:
    entry = CONFIG_SCHEMA_BY_KEY.get(key)
    if entry is None:
        return value
    return entry.masker(value)


def list_config() -> dict:
    return _load_toml_config()


def list_resolved_config() -> list[dict]:
    file_cfg = _load_toml_config()
    entries = []
    for entry in CONFIG_SCHEMA:
        value, source = _resolve_entry(entry, explicit_options={}, file_cfg=file_cfg)
        if value is None and not entry.show_when_unset:
            continue
        entries.append({"key": entry.key, "value": entry.formatter(value), "source": source})
    return entries
