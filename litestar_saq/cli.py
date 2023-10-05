from __future__ import annotations

import asyncio
import multiprocessing
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from click import IntRange, group, option
from litestar.cli._utils import LitestarGroup, _format_is_enabled, console
from rich.table import Table
from saq import __version__ as saq_version

from litestar_saq.exceptions import ImproperConfigurationError
from litestar_saq.plugin import SAQPlugin

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.logging.config import BaseLoggingConfig

    from litestar_saq.base import Worker


@group(cls=LitestarGroup, name="worker")
def background_worker_group() -> None:
    """Manage background task workers."""


@background_worker_group.command(
    name="run",
    help="Run background worker processes.",
)
@option(
    "--workers",
    help="The number of worker processes to start.",
    type=IntRange(min=1),
    default=1,
    required=False,
    show_default=True,
)
@option("-v", "--verbose", help="Enable verbose logging.", is_flag=True, default=None, type=bool, required=False)
@option("-d", "--debug", help="Enable debugging.", is_flag=True, default=None, type=bool, required=False)
def run_worker(
    app: Litestar,
    workers: int,
    verbose: bool | None,
    debug: bool | None,
) -> None:
    """Run the API server."""
    console.rule("[yellow]Starting SAQ Workers[/]", align="left")
    if app.logging_config is not None:
        app.logging_config.configure()
    if debug is not None:
        app.debug = True
    if verbose is not None:
        """todo: set the logging level here"""
        _log_level = "debug"
    plugin = get_saq_plugin(app)
    show_saq_info(app, workers, plugin)
    if workers > 1:
        for _ in range(workers - 1):
            p = multiprocessing.Process(target=run_worker_process, args=(plugin.get_workers(), app.logging_config))
            p.start()

    try:
        run_worker_process(workers=plugin.get_workers(), logging_config=cast("BaseLoggingConfig", app.logging_config))
    except KeyboardInterrupt:
        loop = asyncio.get_event_loop()
        for worker_instance in plugin.get_workers():
            loop.run_until_complete(worker_instance.stop())


def get_saq_plugin(app: Litestar) -> SAQPlugin:
    """Retrieve a SAQ plugin from the Litestar application's plugins.

    This function attempts to find a SAQ plugin instance.
    If plugin is not found, it raises an ImproperlyConfiguredException.
    """

    with suppress(KeyError):
        return app.plugins.get(SAQPlugin)
    msg = "Failed to initialize SAQ. The required plugin (SAQPlugin) is missing."
    raise ImproperConfigurationError(
        msg,
    )


def show_saq_info(app: Litestar, workers: int, plugin: SAQPlugin) -> None:  # pragma: no cover
    """Display basic information about the application and its configuration."""

    table = Table(show_header=False)
    table.add_column("title", style="cyan")
    table.add_column("value", style="bright_blue")

    table.add_row("SAQ version", saq_version)
    table.add_row("Debug mode", _format_is_enabled(app.debug))
    table.add_row("Number of Processes", str(workers))
    table.add_row("Queues", str(len(plugin._config.queue_configs)))  # noqa: SLF001

    console.print(table)


def run_worker_process(workers: list[Worker], logging_config: BaseLoggingConfig | None) -> None:
    """Run a worker."""
    loop = asyncio.get_event_loop()
    if logging_config is not None:
        logging_config.configure()
    try:
        for i, worker_instance in enumerate(workers):
            if i < len(workers) - 1:
                loop.create_task(worker_instance.start())
            else:
                loop.run_until_complete(worker_instance.start())
    except KeyboardInterrupt:
        for worker in workers:
            loop.run_until_complete(worker.stop())
