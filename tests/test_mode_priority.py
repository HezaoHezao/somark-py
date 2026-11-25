import os
from unittest.mock import patch

from somark._config import OXR_DEFAULT_BASE_URL, resolve_config


def _resolved(**kwargs):
    with patch.dict(os.environ, {}, clear=True):
        return resolve_config(**kwargs)


def test_private_mode_ignores_env_official_key():
    file_cfg = {
        "active_mode": "private",
        "private_base_url": "https://private.example/api/v1",
        "private_api_key": "local-key",
    }
    with patch.dict(os.environ, {"SOMARK_API_KEY": "sk-official"}, clear=True):
        with patch("somark._config._load_toml_config", return_value=file_cfg):
            cfg = resolve_config()
    assert cfg["active_mode"] == "private"
    assert cfg["base_url"] == "https://private.example/api/v1"
    assert cfg["api_key"] == "local-key"


def test_explicit_api_key_does_not_change_private_host():
    file_cfg = {
        "active_mode": "private",
        "private_base_url": "https://private.example/api/v1",
        "private_api_key": "local-key",
    }
    with patch.dict(os.environ, {}, clear=True):
        with patch("somark._config._load_toml_config", return_value=file_cfg):
            cfg = resolve_config(api_key="sk-official")
    assert cfg["base_url"] == "https://private.example/api/v1"
    assert cfg["api_key"] == "sk-official"


def test_private_without_url_does_not_target_official():
    file_cfg = {"active_mode": "private", "private_api_key": "local-key"}
    with patch.dict(os.environ, {}, clear=True):
        with patch("somark._config._load_toml_config", return_value=file_cfg):
            cfg = resolve_config()
    assert cfg["request_blocked"]
    assert cfg["base_url"] == ""
    assert "somark.cn" not in (cfg["base_url"] or "")
    assert cfg["api_key"] is None


def test_empty_private_key_in_file_blocks_env_key():
    file_cfg = {
        "active_mode": "private",
        "private_base_url": "https://private.example/api/v1",
        "private_api_key": "",
    }
    with patch.dict(os.environ, {"SOMARK_PRIVATE_API_KEY": "old-key"}, clear=True):
        with patch("somark._config._load_toml_config", return_value=file_cfg):
            cfg = resolve_config()
    assert cfg["base_url"] == "https://private.example/api/v1"
    assert cfg["api_key"] is None


def test_legacy_custom_base_url_without_mode_is_not_rewritten_to_oxr():
    file_cfg = {"base_url": "https://old-private.example/api/v1"}
    with patch.dict(os.environ, {}, clear=True):
        with patch("somark._config._load_toml_config", return_value=file_cfg):
            cfg = resolve_config()
    assert cfg["active_mode"] == "private"
    assert cfg["base_url"] == "https://old-private.example/api/v1"
    assert cfg["api_key"] is None
    assert cfg["base_url"] != OXR_DEFAULT_BASE_URL


def test_fresh_install_uses_auto():
    with patch.dict(os.environ, {}, clear=True):
        with patch("somark._config._load_toml_config", return_value={}):
            cfg = resolve_config()
    assert cfg["active_mode"] == "auto"
    assert cfg["request_blocked"]
    assert cfg["base_url"] in ("", None)
    assert cfg["api_key"] is None
