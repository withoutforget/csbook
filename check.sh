find . -type d | while read -r d; do
  find "$d" -mindepth 1 -maxdepth 1 -type d | grep -q . && continue
  [[ -f "$d/article.md" ]] || echo "$d"
done