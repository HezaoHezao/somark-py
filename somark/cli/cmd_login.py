from __future__ import annotations

import sys
from typing import Optional

import typer

from somark.cli._output import console, print_error, print_success


def _read_secret(value: Optional[str], *, allow_empty: bool) -> str:
    if value is not None:
        return str(value).strip()
    if sys.stdin.isatty():
        if allow_empty:
            entered = typer.prompt("Enter your API key (optional)", default="", hide_input=True)
        else:
            entered = typer.prompt("Enter your API key", hide_input=True)
        return str(entered or "").strip()
    return sys.stdin.readline().strip()


def login(
    url: Optional[str] = typer.Option(None, "--url", help="Private or official base URL. Omit to probe cn/ai from the API key."),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key. Official keys must start with sk-. Private keys are optional."),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser"),
):
    """Save SoMark credentials. A URL selects the destination; a key alone probes the official site."""
    from somark._config import (
        CONFIG_FILE,
        OFFICIAL_REGION_WORKBENCH,
        classify_destination,
        clear_config,
        save_config,
    )
    from somark._probe import probe_official_base_url

    if url is None:
        if not no_open and sys.stdin.isatty():
            import webbrowser

            workbench = OFFICIAL_REGION_WORKBENCH["cn"]
            console.print(f"Opening {workbench} in your browser...")
            webbrowser.open(workbench)
        key = _read_secret(api_key, allow_empty=False)
        if not key.startswith("sk-"):
            print_error("Invalid API key format (should start with 'sk-')")
            raise typer.Exit(1)
        found = probe_official_base_url(key)
        if not found:
            print_error("Could not reach somark.cn or somark.ai with this API key. Nothing was saved.")
            raise typer.Exit(1)
        save_config(api_key=key, base_url=found, active_mode="auto")
        print_success(f"Authenticated. Key + base_url saved to {CONFIG_FILE}")
        console.print(f"base_url={found}")
        console.print("active_mode=auto")
        return

    target = str(url).strip()
    if not target.startswith(("http://", "https://")):
        print_error("Invalid URL (must start with http:// or https://)")
        raise typer.Exit(1)
    try:
        kind = classify_destination(target)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1)
    target = target.rstrip("/")

    if kind == "oxr":
        save_config(active_mode="oxr")
        print_success("Switched active_mode to oxr")
        console.print("active_mode=oxr")
        return

    if kind == "official":
        key = _read_secret(api_key, allow_empty=False)
        if not key.startswith("sk-"):
            print_error("Invalid API key format (should start with 'sk-')")
            raise typer.Exit(1)
        save_config(api_key=key, base_url=target, active_mode="auto")
        print_success(f"Authenticated. Key + base_url saved to {CONFIG_FILE}")
        console.print(f"base_url={target}")
        console.print("active_mode=auto")
        return

    key = _read_secret(api_key, allow_empty=True)
    save_config(private_base_url=target, active_mode="private")
    if key:
        save_config(private_api_key=key)
        note = "URL + API key"
    else:
        clear_config("private_api_key")
        save_config(private_api_key="")
        note = "URL only（已清除 API key）"
    print_success(f"Private deployment saved ({note}) → {CONFIG_FILE}")
    console.print("active_mode=private")
