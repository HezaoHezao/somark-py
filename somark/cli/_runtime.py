"""Request overrides shared by the CLI commands. Does not import command modules."""

from __future__ import annotations

from typing import Optional

from somark import SoMark

api_key: Optional[str] = None
base_url: Optional[str] = None
timeout: Optional[float] = None


def make_client() -> SoMark:
    return SoMark(api_key=api_key, base_url=base_url, timeout=timeout)
