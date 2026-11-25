from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Callable, Optional
from urllib.parse import urlparse

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
VALID_ACTIVE_MODES = ("auto", "oxr", "private")
# OXR free-tier hard limits (client-side guard; do not silently truncate)
OXR_MAX_FILE_BYTES = 10 * 1024 * 1024
OXR_MAX_PAGES = 20
# OXR 官方文件格式（8 种）；Office 等完整格式仅 api/private
OXR_ALLOWED_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
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
        if not path.exists():
            from somark._exceptions import InvalidParamError

            raise InvalidParamError(f"File not found: {path}")
        suffix = path.suffix.lower()
        if not suffix or suffix not in OXR_ALLOWED_SUFFIXES:
            raise UnsupportedFileError(
                f"OXR free tier does not support '{suffix or '(no suffix)'}'. "
                "Run: somark login  (or somark login --url <private-base> for a private deployment).",
                code=1104,
            )
        size = path.stat().st_size
        if size > OXR_MAX_FILE_BYTES:
            mb = size / (1024 * 1024)
            raise FileTooLargeError(
                f"OXR free tier limit is 10 MB / 20 pages; file is {mb:.2f} MB. "
                "Refuse to parse (will not truncate). Run: somark login",
                code=1132,
            )
        if suffix == ".pdf":
            pages = _pdf_page_count(path)
            if pages is None:
                raise FileTooLargeError(
                    "OXR free tier limit is 10 MB / 20 pages; could not confirm the PDF page count. "
                    "Refuse to parse. Run: somark login",
                    code=1132,
                )
            if pages > OXR_MAX_PAGES:
                raise FileTooLargeError(
                    f"OXR free tier limit is 10 MB / 20 pages; PDF has {pages} pages. "
                    "Refuse to parse (will not truncate). Run: somark login",
                    code=1132,
                )


_PROFILE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def config_file_for_profile(profile: Optional[str] = None) -> Path:
    if not profile or profile == "default":
        return CONFIG_DIR / "config.toml"
    if _PROFILE_NAME.fullmatch(profile) is None:
        raise ValueError(
            f'Invalid profile "{profile}". Use only letters, numbers, "_" and "-".'
        )
    root = CONFIG_DIR.resolve()
    path = (root / "profiles" / f"{profile}.toml").resolve()
    if path.parent != (root / "profiles"):
        raise ValueError(f'Invalid profile "{profile}". Path must stay inside {root}.')
    return path


def set_active_profile(profile: Optional[str]) -> Path:
    global CONFIG_FILE, _ACTIVE_PROFILE
    path = config_file_for_profile(profile)
    _ACTIVE_PROFILE = profile if profile and profile != "default" else None
    CONFIG_FILE = path
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


def _parse_active_mode(value: Any) -> Optional[str]:
    text = _parse_optional_str(value)
    if text == "api":
        return "auto"
    return text


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
        # File-only. Tier changes go through `somark use`, not an environment variable.
        env_var="",
        option_key="active_mode",
        default=None,
        parser=_parse_active_mode,
        validator=_validate_active_mode,
        masker=_mask_identity,
        formatter=_format_default,
        show_when_unset=False,
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
    elif entry.key == "private_api_key" and "private_api_key" in file_cfg:
        # A stored empty string means the user cleared the key; env must not restore it.
        raw_value = file_cfg.get("private_api_key")
        source = "file"
    elif entry.env_var and os.environ.get(entry.env_var):
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


def _blank(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


OFFICIAL_API_HOSTS = {
    "somark.cn",
    "www.somark.cn",
    "somark.ai",
    "www.somark.ai",
    "somark.tech",
    "www.somark.tech",
}


def is_oxr_endpoint(url: Optional[str]) -> bool:
    return (url or "").rstrip("/") == OXR_DEFAULT_BASE_URL.rstrip("/")


def is_official_api_host(url: Optional[str]) -> bool:
    return _host_of(url or "") in OFFICIAL_API_HOSTS


def classify_destination(url: str) -> str:
    """Return official, oxr, or private. Empty and non-http values are rejected."""
    text = str(url or "").strip()
    if not text.startswith(("http://", "https://")):
        raise ValueError(f'Invalid base url "{url}". Must start with http:// or https://')
    if is_oxr_endpoint(text):
        return "oxr"
    if is_official_api_host(text):
        return "official"
    return "private"


def allows_missing_api_key(base_url: Optional[str], private_base_url: Optional[str] = None) -> bool:
    """No user key is valid only for the free OXR endpoint or a non-official host."""
    del private_base_url
    if not isinstance(base_url, str):
        return False
    base = base_url.strip()
    if not base:
        return False
    if is_oxr_endpoint(base):
        return True
    return not is_official_api_host(base)


AUTO_LOGIN_HINT = "active_mode=auto requires an API key and official base_url. Run: somark login"
PRIVATE_URL_HINT = "active_mode=private requires private_base_url. Run: somark login --url <private-base>"


def _same_url(left: Optional[str], right: Optional[str]) -> bool:
    return (left or "").rstrip("/") == (right or "").rstrip("/")


def _apply_active_mode(
    cfg: dict[str, Any],
    sources: dict[str, str],
    *,
    explicit_api_key: bool,
    explicit_base_url: bool,
    file_cfg: dict,
) -> dict[str, Any]:
    """Mode picks the destination. A key never changes the host by itself."""
    file_mode = cfg.get("active_mode") if sources.get("active_mode") == "file" else None
    if file_mode == "api":
        file_mode = "auto"
    file_base = _blank(file_cfg.get("base_url"))
    if file_base and not explicit_base_url and sources.get("base_url") == "env":
        cfg["base_url"] = file_base
        sources["base_url"] = "file"

    chosen_key = _blank(cfg.get("api_key")) if explicit_api_key else None
    cfg["request_blocked"] = None

    if explicit_base_url:
        url = str(cfg.get("base_url") or "")
        kind = classify_destination(url)
        cfg["base_url"] = url.rstrip("/")
        cfg["active_mode"] = file_mode or ("private" if kind == "private" else "auto")
        if kind == "oxr":
            cfg["base_url"] = OXR_DEFAULT_BASE_URL
            cfg["api_key"] = None
            return cfg
        if kind == "official":
            if explicit_api_key:
                cfg["api_key"] = chosen_key
                return cfg
            saved_key = _blank(file_cfg.get("api_key"))
            if saved_key is None and sources.get("api_key") == "env":
                saved_key = _blank(cfg.get("api_key"))
            saved_official = file_base if file_base and classify_destination(file_base) == "official" else None
            if saved_official and _same_url(saved_official, url) and saved_key:
                cfg["api_key"] = saved_key
                return cfg
            cfg["api_key"] = None
            cfg["request_blocked"] = AUTO_LOGIN_HINT
            return cfg
        private_url = _blank(cfg.get("private_base_url"))
        if explicit_api_key:
            cfg["api_key"] = chosen_key
        elif private_url and _same_url(private_url, url):
            cfg["api_key"] = _blank(cfg.get("private_api_key"))
        else:
            cfg["api_key"] = None
        return cfg

    if file_mode == "oxr":
        cfg["active_mode"] = "oxr"
        cfg["base_url"] = OXR_DEFAULT_BASE_URL
        cfg["api_key"] = None
        return cfg

    legacy_private = file_mode is None and bool(file_base) and classify_destination(file_base) == "private"
    if file_mode == "private" or legacy_private:
        cfg["active_mode"] = "private"
        private_url = _blank(cfg.get("private_base_url"))
        if legacy_private and not private_url:
            cfg["base_url"] = file_base.rstrip("/") if file_base else ""
            cfg["api_key"] = chosen_key if explicit_api_key else _blank(cfg.get("private_api_key"))
            return cfg
        if not private_url:
            cfg["base_url"] = ""
            cfg["api_key"] = None
            cfg["request_blocked"] = PRIVATE_URL_HINT
            return cfg
        cfg["base_url"] = private_url
        cfg["api_key"] = chosen_key if explicit_api_key else _blank(cfg.get("private_api_key"))
        return cfg

    cfg["active_mode"] = "auto"
    base_source = sources.get("base_url")
    base_value = _blank(cfg.get("base_url")) if base_source in {"file", "env"} else None
    key = chosen_key if explicit_api_key else (
        _blank(cfg.get("api_key")) if sources.get("api_key") in {"file", "env", "explicit"} else None
    )
    if base_value and key and classify_destination(base_value) == "official":
        cfg["base_url"] = base_value.rstrip("/")
        cfg["api_key"] = key
        return cfg
    if file_mode is None and base_source == "env" and base_value and key:
        cfg["base_url"] = base_value.rstrip("/")
        cfg["api_key"] = key
        return cfg
    cfg["base_url"] = ""
    cfg["api_key"] = None
    cfg["request_blocked"] = AUTO_LOGIN_HINT
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
    cfg: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for entry in CONFIG_SCHEMA:
        value, source = _resolve_entry(entry, explicit_options=explicit_options, file_cfg=file_cfg)
        cfg[entry.key] = value
        sources[entry.key] = source
    return _apply_active_mode(
        cfg,
        sources,
        explicit_api_key=api_key is not None,
        explicit_base_url=base_url is not None,
        file_cfg=file_cfg,
    )


def has_official_api_key() -> bool:
    if os.environ.get("SOMARK_API_KEY"):
        return True
    return bool(_load_toml_config().get("api_key"))


def has_official_credentials() -> bool:
    """Official auto mode is ready only when a saved official host and a key both exist."""
    file_cfg = _load_toml_config()
    base = _blank(file_cfg.get("base_url"))
    if not base:
        return False
    try:
        if classify_destination(base) != "official":
            return False
    except ValueError:
        return False
    if _blank(file_cfg.get("api_key")):
        return True
    return bool(_blank(os.environ.get("SOMARK_API_KEY")))


def has_private_credentials() -> bool:
    """Ready when a private URL is set. Official hosts still require a key."""
    file_cfg = _load_toml_config()
    url = _blank(os.environ.get("SOMARK_PRIVATE_BASE_URL") or file_cfg.get("private_base_url"))
    if not url:
        return False
    if is_official_api_host(url):
        file_key = file_cfg.get("private_api_key")
        if file_key is not None:
            return bool(_blank(file_key))
        return bool(_blank(os.environ.get("SOMARK_PRIVATE_API_KEY")))
    return True


def get_mode_readiness() -> dict[str, Any]:
    cfg = resolve_config()
    file_cfg = _load_toml_config()
    api_base = _blank(file_cfg.get("base_url")) or ""
    if api_base and is_oxr_endpoint(api_base):
        api_base = ""
    return {
        "active_mode": cfg["active_mode"],
        "auto": {"ready": has_official_credentials(), "base_url": api_base or "(not set)"},
        "oxr": {"ready": True, "base_url": OXR_DEFAULT_BASE_URL},
        "private": {
            "ready": has_private_credentials(),
            "base_url": file_cfg.get("private_base_url"),
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
