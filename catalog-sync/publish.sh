#!/bin/sh
# Sincroniza los catálogos y los sube a la rama `catalog` del repo público de releases.
# La rama tiene siempre un único commit (se reemplaza cada semana) para que el repo no crezca.
#
# En el Mac usa tus credenciales de git. En GitHub Actions usa CATALOG_PUSH_TOKEN.
set -eu

REPO="github.com/miguelmg4/MiVanApp-releases.git"
BRANCH="catalog"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ -n "${CATALOG_PUSH_TOKEN:-}" ]; then
  URL="https://x-access-token:${CATALOG_PUSH_TOKEN}@${REPO}"
else
  URL="https://${REPO}"
fi

if git clone --quiet --depth 1 --branch "$BRANCH" "$URL" "$WORK" 2>/dev/null; then
  EXISTING=1
else
  EXISTING=0
  git init --quiet "$WORK"
  git -C "$WORK" checkout --quiet --orphan "$BRANCH"
  git -C "$WORK" remote add origin "$URL"
fi

STATUS=0
(cd "$HERE" && python3 run.py --out "$WORK" "$@") || STATUS=$?

cd "$WORK"
git add -A
if git diff --cached --quiet; then
  echo "Sin cambios que publicar."
  exit "$STATUS"
fi
git -c user.name="catalog-sync" -c user.email="catalog-sync@users.noreply.github.com" \
  commit --quiet $([ "$EXISTING" = 1 ] && echo --amend) -m "Catálogos $(date -u +%Y-%m-%d)"
git push --quiet --force origin "HEAD:$BRANCH"
echo "Publicado en https://raw.githubusercontent.com/miguelmg4/MiVanApp-releases/$BRANCH/index.json"
exit "$STATUS"
