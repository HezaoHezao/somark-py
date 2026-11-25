"""Probe which official SoMark site accepts an API key. Does not write config."""

from __future__ import annotations

from typing import Callable, Optional

from somark._config import OFFICIAL_REGION_BASE_URLS

PROBE_TIMEOUT = 8
PROBE_MAX_RETRIES = 0

RequestUsage = Callable[..., bool]


def _request_usage(base_url: str, api_key: str, *, timeout: float = PROBE_TIMEOUT) -> bool:
    from somark._http import HttpClient

    client = HttpClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=PROBE_MAX_RETRIES,
    )
    try:
        client.post("/usage", data={})
        return True
    except Exception:
        return False
    finally:
        client.close()


def probe_official_base_url(
    api_key: str,
    *,
    timeout: float = PROBE_TIMEOUT,
    request_usage: Optional[RequestUsage] = None,
) -> Optional[str]:
    """Return the cn or ai base URL that accepts this key, or None."""
    text = str(api_key or "").strip()
    if not text.startswith("sk-"):
        return None
    request = request_usage or _request_usage
    for base in (OFFICIAL_REGION_BASE_URLS["cn"], OFFICIAL_REGION_BASE_URLS["ai"]):
        try:
            if request(base, text, timeout=timeout):
                return base
        except Exception:
            continue
    return None
