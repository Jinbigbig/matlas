#!/usr/bin/env bash
# Matlas 发布：构建 _site → 推送 gh-pages。main 只放源码，产物永不进 main。
#
#   ./publish.sh           构建（strict 自检）+ 推送 gh-pages
#   ./publish.sh --no-push 只构建，不推送（本地预览用）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PY:-python}"
TMP="${TMPDIR:-/tmp}/_matlas_pages"
PUSH=1
[ "${1:-}" = "--no-push" ] && PUSH=0

cd "$ROOT"
echo "[1/4] 构建（红线自检 strict）"
"$PY" build.py --strict

if [ "$PUSH" -eq 0 ]; then
  echo "[√] 已构建到 $ROOT/_site（未推送）"
  exit 0
fi

REMOTE="$(git remote get-url origin)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ -n "$(git status --porcelain)" ]; then
  echo "[!] 工作区有未提交改动，先提交再发布（产物不应夹带源码改动）。" >&2
  exit 1
fi

echo "[2/4] 同步产物到临时目录"
rm -rf "$TMP" && mkdir -p "$TMP"
cp -r "$ROOT/_site/." "$TMP/"
touch "$TMP/.nojekyll"

echo "[3/4] 提交 gh-pages"
cd "$TMP"
[ -d .git ] || git init -q -b gh-pages
git add -A
git -c user.name="$(git -C "$ROOT" config user.name)" \
    -c user.email="$(git -C "$ROOT" config user.email)" \
    commit -q -m "site: 构建产物 $(date +%Y-%m-%dT%H:%M:%S)" || echo "      （产物无变化，跳过提交）"
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"

echo "[4/4] 推送 gh-pages"
git push -f origin gh-pages

cd "$ROOT"
echo "[√] 已发布。main 分支 $BRANCH 未受影响。"
