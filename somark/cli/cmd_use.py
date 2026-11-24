from __future__ import annotations

from typing import Optional

import typer

from somark.cli._output import console, print_error, print_success

VALID_MODES = ("oxr", "api", "private")


def use(
    mode: Optional[str] = typer.Argument(
        None,
        help="Tier to activate: oxr | api | private. Omit to show current status.",
    ),
):
    """Switch active_mode among oxr / api / private, or show readiness."""
    from somark._config import (
        get_mode_readiness,
        has_official_api_key,
        has_private_credentials,
        save_config,
    )

    if mode is None:
        snap = get_mode_readiness()
        console.print(f"active_mode = {snap['active_mode']}")
        console.print(f"oxr      ready={snap['oxr']['ready']}  base_url={snap['oxr']['base_url']}")
        console.print(f"api      ready={snap['api']['ready']}  base_url={snap['api']['base_url']}")
        priv = snap["private"]
        priv_url = priv["base_url"] or "(not set)"
        console.print(f"private  ready={priv['ready']}  base_url={priv_url}")
        return

    mode = mode.strip().lower()
    if mode not in VALID_MODES:
        print_error(f"Unknown mode '{mode}'. Use: oxr | api | private")
        raise typer.Exit(1)

    if mode == "api" and not has_official_api_key():
        print_error("SoMark API key not configured. Run: somark login")
        raise typer.Exit(1)

    if mode == "private" and not has_private_credentials():
        print_error("Private deployment not configured. Run: somark private-login")
        raise typer.Exit(1)

    save_config(active_mode=mode)
    print_success(f"Switched active_mode to {mode}")
    console.print(f"active_mode={mode}")
