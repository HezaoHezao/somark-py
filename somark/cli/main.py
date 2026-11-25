from __future__ import annotations

import warnings
from typing import Optional

import typer

from somark import __version__
from somark._config import set_active_profile
from somark._warnings import SoMarkWarning
import somark.cli._runtime as runtime
from somark.cli._help import HELP_CONTEXT_SETTINGS, examples
from somark.cli._output import print_error
from somark.cli.cmd_auth import app as auth_app
from somark.cli.cmd_auth import logout
from somark.cli.cmd_config import app as config_app
from somark.cli.cmd_doctor import app as doctor_app
from somark.cli.cmd_login import login
from somark.cli.cmd_parse import app as parse_app
from somark.cli.cmd_pdf import app as pdf_app
from somark.cli.cmd_preview import preview
from somark.cli.cmd_usage import usage
from somark.cli.cmd_use import use

app = typer.Typer(
    name="somark",
    help="SoMark SDK + CLI — Document parsing, PDF processing, and SoMarkDown preview. [PY]",
    epilog=examples("somark parse document.pdf --formats md,json --out output.md", "somark usage --format table"),
    context_settings=HELP_CONTEXT_SETTINGS,
    add_completion=False,
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True, context_settings=HELP_CONTEXT_SETTINGS)
def main(
    ctx: typer.Context,
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key for this command. Env SOMARK_API_KEY does not override the active mode."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Base URL"),
    timeout: Optional[float] = typer.Option(None, "--timeout", help="Request timeout (seconds)"),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Config profile name (e.g. workbuddy). Default: ~/.somark/config.toml",
    ),
    no_warnings: bool = typer.Option(False, "--no-warnings", help="Suppress SoMark warnings"),
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit", is_eager=True),
):
    runtime.api_key = api_key
    runtime.base_url = base_url
    runtime.timeout = timeout

    if profile:
        try:
            set_active_profile(profile)
        except ValueError as exc:
            print_error(str(exc))
            raise typer.Exit(1)

    warnings.simplefilter("ignore" if no_warnings else "default", SoMarkWarning)
    if version:
        typer.echo(f"somark {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


app.add_typer(parse_app, name="parse")
app.command("usage", context_settings=HELP_CONTEXT_SETTINGS, epilog=examples("somark usage --format table"))(usage)
app.add_typer(pdf_app, name="pdf")
app.command("preview", context_settings=HELP_CONTEXT_SETTINGS, epilog=examples("somark preview output.md --port 7878"))(preview)
app.add_typer(doctor_app, name="doctor")
app.add_typer(config_app, name="config")
app.command(
    "login",
    context_settings=HELP_CONTEXT_SETTINGS,
    epilog=examples(
        "somark login --no-open",
        "somark login --api-key sk-... --no-open",
        "somark login --url https://private.example/api/v1",
    ),
)(login)
app.command(
    "use",
    context_settings=HELP_CONTEXT_SETTINGS,
    epilog=examples("somark use auto", "somark use oxr", "somark use private", "somark use"),
)(use)
app.add_typer(auth_app, name="auth")
# WorkBuddy cli.json unAuth + Skill 使用顶层 logout；auth logout 仍可用
app.command("logout", context_settings=HELP_CONTEXT_SETTINGS)(logout)
