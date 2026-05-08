#!/usr/bin/env python3
"""Build the basebook book.

Collects all ``article.md`` files in sorted order, prepends a YAML frontmatter
generated from ``book.toml``, and renders the result to PDF and HTML via pandoc.

All metadata (title, author, fonts, geometry, colors, ...) lives in the config
file, so the script itself stays book-agnostic.

Run from anywhere:

    uv run python scripts/build.py
    uv run python scripts/build.py --format html -v
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.logging import RichHandler

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "book.toml"

# Allow importing sibling script as a module without making scripts/ a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_fonts  # noqa: E402

console = Console(stderr=True)
log = logging.getLogger("basebook.build")


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


# ── config ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BookConfig:
    title: str
    subtitle: str | None
    author: str
    date: str
    lang: str
    toc: bool
    toc_depth: int
    numbersections: bool
    documentclass: str
    geometry: str
    fontsize: str
    mainfont: str | None
    monofont: str | None
    mathfont: str | None
    colorlinks: bool
    linkcolor: str
    urlcolor: str
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def to_yaml_frontmatter(self) -> str:
        lines = ["---"]

        def add(key: str, value: Any) -> None:
            if value is None or value == "":
                return
            if isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                lines.append(f"{key}: {value}")
            else:
                lines.append(f'{key}: "{value}"')

        add("title", self.title)
        add("subtitle", self.subtitle)
        add("author", self.author)
        add("date", self.date)
        add("lang", self.lang)
        add("toc", self.toc)
        add("toc-depth", self.toc_depth)
        add("numbersections", self.numbersections)
        add("documentclass", self.documentclass)
        add("geometry", self.geometry)
        add("fontsize", self.fontsize)
        add("mainfont", self.mainfont)
        add("monofont", self.monofont)
        add("mathfont", self.mathfont)
        add("colorlinks", self.colorlinks)
        add("linkcolor", self.linkcolor)
        add("urlcolor", self.urlcolor)
        for k, v in self.extra_metadata.items():
            add(k, v)
        lines.append("---")
        lines.append("")
        return "\n".join(lines)


@dataclass(frozen=True)
class BuildConfig:
    source_dir: Path
    output_dir: Path
    article_glob: str
    formats: tuple[str, ...]
    pdf_engines: tuple[str, ...]
    page_break: str


def _resolve_path(base: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def _load_config(path: Path) -> tuple[BookConfig, BuildConfig]:
    if not path.exists():
        log.error("Config file not found: %s", path)
        log.error("Create it (see book.toml in the repo root) or pass --config <path>.")
        sys.exit(2)

    with path.open("rb") as f:
        data = tomllib.load(f)

    book_section = data.get("book", {}) or {}
    toc_section = book_section.get("toc", {}) or {}
    layout = book_section.get("layout", {}) or {}
    fonts = book_section.get("fonts", {}) or {}
    links = book_section.get("links", {}) or {}

    book = BookConfig(
        title=book_section.get("title", ""),
        subtitle=book_section.get("subtitle"),
        author=book_section.get("author", ""),
        date=book_section.get("date", ""),
        lang=book_section.get("lang", "en"),
        toc=bool(toc_section.get("enabled", True)),
        toc_depth=int(toc_section.get("depth", 3)),
        numbersections=bool(layout.get("numbersections", True)),
        documentclass=layout.get("documentclass", "book"),
        geometry=layout.get("geometry", "margin=2.5cm"),
        fontsize=layout.get("fontsize", "11pt"),
        mainfont=fonts.get("main"),
        monofont=fonts.get("mono"),
        mathfont=fonts.get("math"),
        colorlinks=bool(links.get("colored", True)),
        linkcolor=links.get("linkcolor", "blue"),
        urlcolor=links.get("urlcolor", "blue"),
        extra_metadata=book_section.get("extra", {}) or {},
    )

    build_section = data.get("build", {}) or {}
    pdf_section = build_section.get("pdf", {}) or {}
    base = path.parent.resolve()
    build = BuildConfig(
        source_dir=_resolve_path(base, build_section.get("source_dir", ".")),
        output_dir=_resolve_path(base, build_section.get("output_dir", "dist")),
        article_glob=build_section.get("article_glob", "**/article.md"),
        formats=tuple(build_section.get("formats", ["pdf", "html"])),
        pdf_engines=tuple(pdf_section.get("engines", ["xelatex", "pdflatex"])),
        page_break=build_section.get("page_break", "\\newpage"),
    )
    return book, build


# ── pipeline ─────────────────────────────────────────────────────────────────


def _collect_articles(build: BuildConfig) -> list[Path]:
    articles = sorted(build.source_dir.glob(build.article_glob), key=str)
    if not articles:
        log.warning(
            "No articles matched '%s' under %s", build.article_glob, build.source_dir
        )
    return articles


def _combine_articles(
    book: BookConfig,
    build: BuildConfig,
    articles: list[Path],
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    log.info("Writing combined markdown -> %s", output)
    total_bytes = 0
    with output.open("w", encoding="utf-8") as out:
        out.write(book.to_yaml_frontmatter())
        out.write("\n")
        for article in articles:
            try:
                rel = article.relative_to(build.source_dir)
            except ValueError:
                rel = article
            log.debug("  + %s", rel)
            text = article.read_text(encoding="utf-8")
            out.write(text)
            out.write(f"\n\n{build.page_break}\n\n")
            total_bytes += len(text)
    line_count = sum(1 for _ in output.open("r", encoding="utf-8"))
    log.info(
        "Combined %d articles -> %s lines, %.1f KiB",
        len(articles),
        f"{line_count:,}",
        total_bytes / 1024,
    )


def _pick_pdf_engine(engines: tuple[str, ...]) -> str | None:
    for engine in engines:
        if shutil.which(engine):
            log.debug("Using PDF engine: %s", engine)
            return engine
    return None


def _run_pandoc(args: list[str], description: str) -> bool:
    log.info("pandoc: %s", description)
    log.debug("$ %s", " ".join(args))
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        log.error("pandoc not found in PATH")
        return False
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        log.error("pandoc failed (exit %d) for %s", result.returncode, description)
        for line in stderr.splitlines():
            log.error("  %s", line)
        return False
    if stderr:
        for line in stderr.splitlines():
            log.warning("  %s", line)
    return True


def _build_pdf(
    book: BookConfig, build: BuildConfig, source_md: Path, output_pdf: Path
) -> bool:
    engine = _pick_pdf_engine(build.pdf_engines)
    if engine is None:
        log.warning(
            "No LaTeX engine found (tried: %s); skipping PDF.",
            ", ".join(build.pdf_engines),
        )
        return False
    args: list[str] = [
        "pandoc",
        str(source_md),
        "--pdf-engine",
        engine,
        "--toc",
        f"--toc-depth={book.toc_depth}",
        "-N",
        "-o",
        str(output_pdf),
    ]
    if engine == "pdflatex":
        # pdflatex needs explicit UTF-8 + babel for Cyrillic content
        args += [
            "-V",
            "header-includes=\\usepackage[utf8]{inputenc}\\usepackage[russian,english]{babel}",
        ]
    if _run_pandoc(args, f"PDF via {engine}"):
        log.info("[bold green]PDF[/bold green]: %s", output_pdf)
        return True
    return False


def _build_html(book: BookConfig, source_md: Path, output_html: Path) -> bool:
    args = [
        "pandoc",
        str(source_md),
        "--standalone",
        "--toc",
        f"--toc-depth={book.toc_depth}",
        "-N",
        "--metadata",
        f"title={book.title}",
        "-o",
        str(output_html),
    ]
    if _run_pandoc(args, "HTML"):
        log.info("[bold green]HTML[/bold green]: %s", output_html)
        return True
    return False


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
    "--format",
    "formats",
    type=click.Choice(["pdf", "html", "md"], case_sensitive=False),
    multiple=True,
    help="Restrict to specific output formats. Default: from config.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Override output directory.",
)
@click.option(
    "--no-install-fonts",
    is_flag=True,
    help="Skip the auto-install of fonts before building.",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(
    config_path: Path,
    formats: tuple[str, ...],
    output_dir: Path | None,
    no_install_fonts: bool,
    verbose: bool,
) -> None:
    """Combine all article.md files and render via pandoc."""
    _setup_logging(verbose)
    log.info("[bold]basebook builder[/bold]")

    book, build = _load_config(config_path)
    if output_dir is not None:
        build = BuildConfig(
            source_dir=build.source_dir,
            output_dir=output_dir.expanduser().resolve(),
            article_glob=build.article_glob,
            formats=build.formats,
            pdf_engines=build.pdf_engines,
            page_break=build.page_break,
        )

    log.info("Source : %s", build.source_dir)
    log.info("Output : %s", build.output_dir)

    requested = {f.lower() for f in formats} if formats else {f.lower() for f in build.formats}
    log.debug("Formats: %s", sorted(requested))

    articles = _collect_articles(build)
    if not articles:
        log.error("Nothing to build.")
        sys.exit(1)

    build.output_dir.mkdir(parents=True, exist_ok=True)
    output_md = build.output_dir / "book.md"
    _combine_articles(book, build, articles, output_md)

    if requested == {"md"}:
        log.info("[bold green]Done[/bold green] (markdown only)")
        return

    if not shutil.which("pandoc"):
        log.error(
            "pandoc not found in PATH. Install it:\n"
            "  Ubuntu/Debian : sudo apt-get install pandoc texlive-xetex fontconfig\n"
            "  macOS         : brew install pandoc basictex\n"
            "  Windows       : winget install JohnMacFarlane.Pandoc"
        )
        sys.exit(3)

    if not no_install_fonts:
        required = [f for f in (book.mainfont, book.monofont, book.mathfont) if f]
        if required:
            try:
                install_fonts.ensure_fonts(config_path, required)
            except SystemExit:
                raise
            except Exception as e:  # pragma: no cover — defensive
                log.warning("Font auto-install failed: %s", e)
                log.warning("Continuing build; pandoc may fall back to default fonts.")

    failures: list[str] = []
    if "pdf" in requested:
        if not _build_pdf(book, build, output_md, build.output_dir / "book.pdf"):
            failures.append("pdf")
    if "html" in requested:
        if not _build_html(book, output_md, build.output_dir / "book.html"):
            failures.append("html")

    if failures:
        log.error("Build finished with failures: %s", ", ".join(failures))
        sys.exit(1)
    log.info("[bold green]Done[/bold green]")


if __name__ == "__main__":
    cli()
