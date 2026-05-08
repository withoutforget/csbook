symbols=$(find . -name "article.md" | xargs -n 1 cat | wc -m)
no_empty_symbols=$(find . -name "article.md" | xargs -n 1 cat | tr -d '\t\n' | wc -m)
words=$(find . -name "article.md" | xargs -n 1 cat | wc -w)
articles=$(find . -name "article.md" | wc -l)
# approximately
sentences=$(find . -name "article.md" -exec grep -oP '[\p{L}\p{N}][.!?…](\s|$)' {} \; | wc -l)

printf "%-15s %s\n" "Symbols" "$symbols"
printf "%-15s %s\n" "Symbols (no whitespace)" "$no_empty_symbols"
printf "%-15s %s\n" "Words" "$words"
printf "%-15s %s\n" "Sentences" "$sentences"
printf "%-15s %s\n" "Articles" "$articles"
