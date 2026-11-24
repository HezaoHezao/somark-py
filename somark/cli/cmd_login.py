from __future__ import annotations

from typing import Optional

import typer

from somark.cli._output import console, print_error, print_success


def login(
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="Official site: cn (国内站 somark.cn) | ai (国外站 somark.ai). Default: prompt / cn.",
    ),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser"),
):
    """Login to SoMark official API: pick CN/AI site, save API key + matching base_url (overwrites previous key)."""
    from somark._config import (
        CONFIG_FILE,
        OFFICIAL_REGION_BASE_URLS,
        OFFICIAL_REGION_WORKBENCH,
        save_config,
    )

    choice = (region or "").strip().lower()
    if choice not in OFFICIAL_REGION_BASE_URLS:
        console.print("选择官网站点（API Key 与 Base URL 必须同一站点）：")
        console.print("  1) cn — 国内站 https://somark.cn  （大陆用户推荐）")
        console.print("  2) ai — 国外站 https://somark.ai  （含港澳台及海外）")
        raw = typer.prompt("请输入 1/cn 或 2/ai", default="cn")
        raw = str(raw).strip().lower()
        if raw in ("1", "cn", "china", "国内", "国内站"):
            choice = "cn"
        elif raw in ("2", "ai", "global", "国际", "国外", "国外站"):
            choice = "ai"
        else:
            print_error("Invalid region. Use --region cn or --region ai")
            raise typer.Exit(1)

    base_url = OFFICIAL_REGION_BASE_URLS[choice]
    url = OFFICIAL_REGION_WORKBENCH[choice]
    site_label = "国内站 somark.cn" if choice == "cn" else "国外站 somark.ai"

    if not no_open:
        import webbrowser

        console.print(f"Opening {url} ({site_label}) in your browser...")
        webbrowser.open(url)
    else:
        console.print(f"Visit {url} to register / login and create an API key ({site_label}).")

    api_key = typer.prompt("Enter your API key", hide_input=True)
    if not api_key.startswith("sk-"):
        print_error("Invalid API key format (should start with 'sk-')")
        raise typer.Exit(1)

    save_config(api_key=api_key, base_url=base_url)
    print_success(f"Authenticated ({site_label}). Key + base_url saved to {CONFIG_FILE}")
    console.print(f"base_url={base_url}")
    console.print("Tip: re-run login to replace the key; run `somark logout` (or `somark auth logout`) to delete credentials.")
