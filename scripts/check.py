#!/usr/bin/env python3
"""Validate book structure.

Reports leaf directories (directories with no further subdirectories) that
do not contain the expected article file. Mirrors the original ``check.sh``
behavior but with logging, configurable ignores, and a proper exit code.

Run from anywhere:

    uv run python scripts/check.py
    uv run python scripts/check.py -v
"""
from __future__ import annotations

import logging
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "book.toml"
DEFAULT_IGNORE = (
    ".git",
    ".claude",
    "dist",
    "scripts",
    ".venv",
    "__pycache__",
    ".idea",
    ".vscode",
)

console = Console(stderr=True)
log = logging.getLogger("basebook.check")


def _setup_logging(verbose: bool) -> None:
    handler = RichHandler(
        console=console,
        show_time=False,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        handlers=[handler],
        force=True,
    )


@dataclass(frozen=True)
class CheckConfig:
    source_dir: Path
    article_filename: str
    ignore_dirs: frozenset[str]


def _resolve_path(base: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def _load_config(path: Path) -> CheckConfig:
    source_dir = ROOT
    article_filename = "article.md"
    ignore = DEFAULT_IGNORE

    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)
        check_section = data.get("check", {}) or {}
        build_section = data.get("build", {}) or {}
        source_str = (
            check_section.get("source_dir")
            or build_section.get("source_dir", ".")
        )
        source_dir = _resolve_path(path.parent.resolve(), source_str)
        article_filename = check_section.get("article_filename", article_filename)
        ignore = tuple(check_section.get("ignore_dirs", ignore))
    else:
        log.warning("No config at %s, using defaults.", path)

    return CheckConfig(
        source_dir=source_dir,
        article_filename=article_filename,
        ignore_dirs=frozenset(ignore),
    )


def _is_ignored(rel_parts: tuple[str, ...], ignore: frozenset[str]) -> bool:
    return any(part in ignore for part in rel_parts)


def _find_empty_leaves(cfg: CheckConfig) -> list[Path]:
    bad: list[Path] = []
    for path in cfg.source_dir.rglob("*"):
        if not path.is_dir():
            continue
        try:
            rel_parts = path.relative_to(cfg.source_dir).parts
        except ValueError:
            continue
        if _is_ignored(rel_parts, cfg.ignore_dirs):
            continue
        # Ignore non-ignored subdirs only — an ignored subdir shouldn't make
        # this directory "non-leaf".
        has_real_child_dir = any(
            child.is_dir() and child.name not in cfg.ignore_dirs
            for child in path.iterdir()
        )
        if has_real_child_dir:
            continue
        if not (path / cfg.article_filename).exists():
            bad.append(path)
    return sorted(bad, key=str)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to book configuration TOML.",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(config_path: Path, verbose: bool) -> None:
    """Report leaf directories that are missing the article file."""
    _setup_logging(verbose)
    cfg = _load_config(config_path)
    log.info(
        "Scanning [bold]%s[/bold] for leaf dirs without [cyan]%s[/cyan]",
        cfg.source_dir,
        cfg.article_filename,
    )
    log.debug("Ignored dirs: %s", sorted(cfg.ignore_dirs))

    bad = _find_empty_leaves(cfg)
    if not bad:
        log.info(
            "[bold green]OK[/bold green] — all leaf directories contain %s",
            cfg.article_filename,
        )
        return

    log.warning(
        "Found %d leaf director%s missing %s:",
        len(bad),
        "y" if len(bad) == 1 else "ies",
        cfg.article_filename,
    )
    for p in bad:
        try:
            rel = p.relative_to(cfg.source_dir)
        except ValueError:
            rel = p
        click.echo(str(rel))
    sys.exit(1)


if __name__ == "__main__":
    cli()
