#!/usr/bin/env python3
"""Download and install fonts required by the book build.

Reads ``[[fonts.packages]]`` from ``book.toml`` and downloads the listed font
files into a per-user fonts directory (no sudo). After downloading, runs
``fc-cache`` so XeLaTeX/pandoc can find them.

Idempotent: files already present are skipped (use ``--force`` to redownload).

Run standalone:

    uv run python scripts/install_fonts.py
    uv run python scripts/install_fonts.py --check-only
    uv run python scripts/install_fonts.py --force -v
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "book.toml"
USER_AGENT = "basebook-font-installer/1.0"
DOWNLOAD_TIMEOUT = 60  # seconds

console = Console(stderr=True)
log = logging.getLogger("basebook.fonts")


# ── logging ──────────────────────────────────────────────────────────────────


def _setup_logging(verbose: bool) -> None:
    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%H:%M:%S]"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        handlers=[handler],
        force=True,
    )


# ── platform-aware install path ──────────────────────────────────────────────


def _user_font_dir(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system()
    if system == "Linux":
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "fonts"
    elif system == "Darwin":
        base = Path.home() / "Library" / "Fonts"
    elif system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        base = (Path(local) if local else Path.home()) / "Microsoft" / "Windows" / "Fonts"
    else:
        base = Path.home() / ".fonts"
    return base / "basebook"


# ── config ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FontPackage:
    name: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class FontsConfig:
    install_dir: Path
    packages: tuple[FontPackage, ...]


def load_fonts_config(
    path: Path, install_dir_override: str | None = None
) -> FontsConfig:
    if not path.exists():
        log.error("Config not found: %s", path)
        sys.exit(2)
    with path.open("rb") as f:
        data = tomllib.load(f)
    section = data.get("fonts", {}) or {}
    override = install_dir_override or section.get("install_dir") or None
    install_dir = _user_font_dir(override or None)
    raw_packages = section.get("packages", []) or []
    packages = tuple(
        FontPackage(name=p["name"], files=tuple(p.get("files", ())))
        for p in raw_packages
        if p.get("name") and p.get("files")
    )
    return FontsConfig(install_dir=install_dir, packages=packages)


# ── font detection ───────────────────────────────────────────────────────────


def fc_family_present(family: str) -> bool:
    """Return True iff fontconfig reports a font with this family name."""
    if not shutil.which("fc-list"):
        return False
    result = subprocess.run(
        ["fc-list", f":family={family}", "family"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    target = family.casefold()
    return any(target in line.casefold() for line in result.stdout.splitlines())


# ── download / install ───────────────────────────────────────────────────────


def _download(url: str, dest: Path, *, force: bool) -> bool:
    """Download url to dest atomically. Return True if a new file was written."""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        log.debug("  exists: %s", dest.name)
        return False
    log.info("  download: %s", dest.name)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=dest.name + ".", dir=str(dest.parent))
    tmp_path = Path(tmp_str)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status} for {url}")
                shutil.copyfileobj(resp, tmp_file)
        tmp_path.replace(dest)
        return True
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as e:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"failed to download {url}: {e}") from e


def install_packages(cfg: FontsConfig, *, force: bool = False) -> int:
    """Download all package files. Return number of new files written."""
    cfg.install_dir.mkdir(parents=True, exist_ok=True)
    new_files = 0
    for pkg in cfg.packages:
        log.info("[bold]%s[/bold]", pkg.name)
        for url in pkg.files:
            filename = url.rsplit("/", 1)[-1]
            dest = cfg.install_dir / filename
            try:
                if _download(url, dest, force=force):
                    new_files += 1
            except RuntimeError as e:
                log.error("  %s", e)
                raise SystemExit(4) from e
    return new_files


def refresh_font_cache(install_dir: Path) -> None:
    if not shutil.which("fc-cache"):
        log.warning(
            "fc-cache not found; skipping font-cache refresh. "
            "Install fontconfig (`apt install fontconfig`) for XeLaTeX to discover the fonts."
        )
        return
    log.info("Refreshing font cache: fc-cache -f %s", install_dir)
    result = subprocess.run(
        ["fc-cache", "-f", str(install_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        log.warning(
            "fc-cache exit %d: %s",
            result.returncode,
            (result.stderr or result.stdout or "").strip(),
        )


# ── public API used by build.py ──────────────────────────────────────────────


def ensure_fonts(
    config_path: Path,
    required: list[str],
    *,
    force: bool = False,
) -> None:
    """Make sure the listed font families are findable; install if missing."""
    required = [f for f in required if f]
    if not required and not force:
        return
    missing = [f for f in required if not fc_family_present(f)]
    if not missing and not force:
        log.debug("All required fonts present: %s", required)
        return
    if missing:
        log.info("Required fonts missing: %s. Installing...", ", ".join(missing))
    cfg = load_fonts_config(config_path)
    if not cfg.packages:
        log.warning("[fonts.packages] is empty in %s — nothing to install.", config_path)
        return
    n = install_packages(cfg, force=force)
    log.info("Wrote %d file(s) to %s", n, cfg.install_dir)
    if n > 0 or force:
        refresh_font_cache(cfg.install_dir)
    still_missing = [f for f in required if not fc_family_present(f)]
    if still_missing:
        log.warning(
            "Still not visible to fontconfig: %s. "
            "Files are in %s; XeLaTeX may still find them but check `fc-list :family` output.",
            still_missing,
            cfg.install_dir,
        )


# ── CLI ──────────────────────────────────────────────────────────────────────


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to book configuration TOML.",
)
@click.option(
    "--install-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Override install directory.",
)
@click.option("--force", is_flag=True, help="Re-download even if files exist.")
@click.option(
    "--check-only",
    is_flag=True,
    help="Only check which configured fonts fontconfig can see.",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(
    config_path: Path,
    install_dir: Path | None,
    force: bool,
    check_only: bool,
    verbose: bool,
) -> None:
    """Download and install fonts listed in book.toml."""
    _setup_logging(verbose)
    cfg = load_fonts_config(
        config_path, str(install_dir) if install_dir is not None else None
    )
    log.info("Install dir : %s", cfg.install_dir)
    log.info(
        "Packages    : %s",
        ", ".join(p.name for p in cfg.packages) or "(none configured)",
    )

    if check_only:
        any_missing = False
        for pkg in cfg.packages:
            present = fc_family_present(pkg.name)
            mark = "[green]found[/green]" if present else "[red]missing[/red]"
            log.info("  %-20s %s", pkg.name, mark)
            if not present:
                any_missing = True
        sys.exit(1 if any_missing else 0)

    if not cfg.packages:
        log.warning("Nothing to install.")
        return

    install_packages(cfg, force=force)
    refresh_font_cache(cfg.install_dir)

    log.info("Verifying via fc-list:")
    any_missing = False
    for pkg in cfg.packages:
        present = fc_family_present(pkg.name)
        mark = (
            "[green]found[/green]" if present else "[yellow]not visible[/yellow]"
        )
        log.info("  %-20s %s", pkg.name, mark)
        if not present:
            any_missing = True
    if any_missing:
        log.warning(
            "Some fonts are not visible to fontconfig. They may still work for "
            "XeLaTeX (the files exist in %s); double-check with "
            "`fc-list :family` if pandoc complains.",
            cfg.install_dir,
        )
    log.info("[bold green]Done[/bold green]")


if __name__ == "__main__":
    cli()
