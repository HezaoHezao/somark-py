from __future__ import annotations

import json

import typer

from somark.cli._help import HELP_CONTEXT_SETTINGS
from somark.cli._output import console, print_success

app = typer.Typer(help="Connection status helpers for WorkBuddy.", no_args_is_help=True)


@app.command("status", context_settings=HELP_CONTEXT_SETTINGS)
def status(
    output: str = typer.Option("text", "--output", help="Output format: text|json"),
):
    """Report readiness for the active_mode (oxr always ready)."""
    from somark._config import (
        get_active_profile,
        get_config_value,
        has_official_api_key,
        has_private_credentials,
        resolve_config,
    )

    cfg = resolve_config()
    mode = cfg.get("active_mode") or "oxr"
    profile = get_active_profile() or "default"

    if mode == "oxr":
        logged_in = True
        method = "oxr"
    elif mode == "api":
        logged_in = has_official_api_key()
        method = "api_key"
    else:
        logged_in = has_private_credentials()
        method = "private_api_key"

    payload = {
        "logged_in": logged_in,
        "method": method,
        "active_mode": mode,
        "profile": profile,
        "has_file_credential": bool(get_config_value("api_key")),
        "base_url": cfg.get("base_url"),
    }

    if output == "json":
        console.print(json.dumps(payload, ensure_ascii=False))
    elif logged_in:
        console.print(f"active_mode={mode}")
        console.print(f"Ready ({method})")
    else:
        console.print(f"active_mode={mode}")
        console.print("Not ready for current mode")

    raise typer.Exit(0 if logged_in else 1)


@app.command("logout", context_settings=HELP_CONTEXT_SETTINGS)
def logout():
    """Clear credentials and reset active_mode to oxr."""
    from somark._config import clear_config, save_config

    clear_config("api_key", "private_api_key", "private_base_url", "active_mode")
    save_config(active_mode="oxr")
    print_success("Logged out; active_mode reset to oxr")
