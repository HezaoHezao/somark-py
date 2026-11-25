from __future__ import annotations

from typing import Optional

import typer

from somark.cli._output import console, print_error, print_success

VALID_MODES = ("auto", "oxr", "private")


def use(
    mode: Optional[str] = typer.Argument(
        None,
        help="Tier to activate: auto | oxr | private. Omit to show current status.",
    ),
):
    """Switch active_mode among auto / oxr / private, or show readiness."""
    from somark._config import get_mode_readiness, has_official_credentials, has_private_credentials, save_config

    if mode is None:
        snap = get_mode_readiness()
        console.print(f"active_mode = {snap['active_mode']}")
        console.print(f"auto     ready={snap['auto']['ready']}  base_url={snap['auto']['base_url']}")
        console.print(f"oxr      ready={snap['oxr']['ready']}  base_url={snap['oxr']['base_url']}")
        priv = snap["private"]
        priv_url = priv["base_url"] or "(not set)"
        console.print(f"private  ready={priv['ready']}  base_url={priv_url}")
        return

    mode = mode.strip().lower()
    if mode == "api":
        mode = "auto"
    if mode not in VALID_MODES:
        print_error(f"Unknown mode '{mode}'. Use: auto | oxr | private")
        raise typer.Exit(1)

    if mode == "auto" and not has_official_credentials():
        print_error("SoMark API key not configured. Run: somark login")
        raise typer.Exit(1)

    if mode == "private" and not has_private_credentials():
        print_error("Private deployment not configured. Run: somark login --url https://your-host/api/v1")
        raise typer.Exit(1)

    save_config(active_mode=mode)
    print_success(f"Switched active_mode to {mode}")
    console.print(f"active_mode={mode}")
