from __future__ import annotations

from typing import Optional

import typer

from somark.cli._output import console, print_error, print_success


def private_login(
    url: Optional[str] = typer.Option(None, "--url", help="Private deployment base URL (optional; prompted if omitted)"),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Private deployment API key (optional; prompted if omitted, can leave empty)",
    ),
):
    """Interactive private setup: Base URL required, API key optional. Prefer: somark private-login"""
    from somark._config import CONFIG_FILE, save_config

    console.print("配置私有部署（一步一步来）")
    console.print("1/2 填写 Base URL（必填），例如 https://your-host/api/v1")

    if not url:
        url = typer.prompt("Private Base URL")
    url = str(url).strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        print_error("Invalid URL (must start with http:// or https://)")
        raise typer.Exit(1)

    console.print("2/2 填写 API Key（可选；无私有 Key 直接回车跳过）")
    if api_key is None:
        # default="" so Enter skips; hide_input still works with empty
        api_key = typer.prompt("Private API key (optional)", default="", hide_input=True)
    api_key = str(api_key).strip()

    payload = {"private_base_url": url}
    if api_key:
        if not api_key.startswith("sk-"):
            print_error("Invalid API key format (should start with 'sk-')")
            raise typer.Exit(1)
        payload["private_api_key"] = api_key
        key_note = "URL + API key"
    else:
        key_note = "URL only（未写入 API key）"

    save_config(**payload)
    print_success(f"Private deployment saved ({key_note}) → {CONFIG_FILE}")
    console.print("Next: somark --profile workbuddy use private")
