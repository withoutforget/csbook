#!/usr/bin/env bash
# Build the book: combines all article.md files in sorted order and produces PDF/HTML.
set -euo pipefail

BOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_MD="$BOOK_DIR/book.md"
OUTPUT_PDF="$BOOK_DIR/book.pdf"
OUTPUT_HTML="$BOOK_DIR/book.html"

echo "=== Book builder ==="
echo "Source: $BOOK_DIR"

# ── 1. Collect all articles ───────────────────────────────────────────────────
echo "" > "$OUTPUT_MD"

# Title page
cat >> "$OUTPUT_MD" <<'TITLEPAGE'
---
title: "Computer Science: полное руководство"
subtitle: "От транзисторов до распределённых систем"
author: "Коллективный труд"
date: "2025"
lang: ru
toc: true
toc-depth: 3
numbersections: true
documentclass: book
geometry: "margin=2.5cm"
fontsize: 11pt
mainfont: "FreeSerif"
monofont: "FreeMono"
colorlinks: true
linkcolor: blue
urlcolor: blue
---

TITLEPAGE

echo "Collecting articles..."
article_count=0

while IFS= read -r file; do
    rel="${file#$BOOK_DIR/}"
    echo "  + $rel"
    cat "$file" >> "$OUTPUT_MD"
    printf '\n\n\\newpage\n\n' >> "$OUTPUT_MD"
    (( article_count++ )) || true
done < <(find "$BOOK_DIR" -name "article.md" | sort)

echo "Total articles collected: $article_count"
echo "Combined markdown: $OUTPUT_MD ($(wc -l < "$OUTPUT_MD") lines)"

# ── 2. Build PDF ──────────────────────────────────────────────────────────────
if command -v pandoc &>/dev/null; then
    echo ""
    echo "Building PDF with pandoc..."

    # Try xelatex first (best Cyrillic support), fall back to pdflatex
    if command -v xelatex &>/dev/null; then
        ENGINE="xelatex"
    elif command -v pdflatex &>/dev/null; then
        ENGINE="pdflatex"
        # pdflatex needs inputenc for UTF-8
        EXTRA_ARGS="-V 'header-includes=\\usepackage[utf8]{inputenc}\\usepackage[russian]{babel}'"
    else
        echo "No LaTeX engine found. Skipping PDF."
        ENGINE=""
    fi

    if [[ -n "$ENGINE" ]]; then
        pandoc "$OUTPUT_MD" \
            --pdf-engine="$ENGINE" \
            --toc \
            --toc-depth=3 \
            -N \
            -o "$OUTPUT_PDF" \
            2>&1 && echo "PDF: $OUTPUT_PDF" || echo "PDF build failed (check pandoc/latex installation)"
    fi

    # ── 3. Build HTML (always works) ─────────────────────────────────────────
    echo ""
    echo "Building HTML..."
    pandoc "$OUTPUT_MD" \
        --standalone \
        --toc \
        --toc-depth=3 \
        -N \
        --metadata title="Computer Science: полное руководство" \
        -o "$OUTPUT_HTML" \
        2>&1 && echo "HTML: $OUTPUT_HTML" || echo "HTML build failed"
else
    echo ""
    echo "pandoc not found. Install it:"
    echo "  Ubuntu/Debian : sudo apt-get install pandoc texlive-xetex fonts-freefont-ttf"
    echo "  macOS         : brew install pandoc basictex"
    echo "  Windows       : winget install JohnMacFarlane.Pandoc"
    echo ""
    echo "Markdown source ready: $OUTPUT_MD"
fi

echo ""
echo "=== Done ==="
