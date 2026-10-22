#!/usr/bin/env bash
# Matlas 发布：构建 _site → 同步到 gh-pages 工作树 → 推送。
#
#   两个分支的分工（本地都可见）：
#     main      源码 + 数据   工作区  <repo>/           _site/ 与 .publish/ 均被忽略
#     gh-pages  构建产物      工作树  <repo>/.publish/  一个提交 = 一次发布，历史连续
#
#   ./publish.sh           构建（strict 自检）+ 提交 + 推送 gh-pages
#   ./publish.sh --no-push 只构建，不动产物分支（本地预览用）
#
# 首次使用需要先建工作树：git worktree add .publish gh-pages
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PY:-python}"
PUB="$ROOT/.publish"
PUSH=1
[ "${1:-}" = "--no-push" ] && PUSH=0

cd "$ROOT"

echo "[1/4] 构建（红线自检 strict）"
"$PY" build.py --strict

if [ "$PUSH" -eq 0 ]; then
  echo "[√] 已构建到 $ROOT/_site（未推送，产物分支未改动）"
  exit 0
fi

# ---- 前置校验：任何一项不满足都直接停，避免把产物写进错误的地方 ----
if [ ! -d "$PUB" ]; then
  echo "[!] 产物工作树不存在。先执行：git worktree add .publish gh-pages" >&2
  exit 1
fi
CUR="$(git -C "$PUB" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
if [ "$CUR" != "gh-pages" ]; then
  echo "[!] $PUB 当前在 '$CUR' 分支，不是 gh-pages，拒绝写入。" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "[!] main 工作区有未提交改动，先提交再发布（产物不应夹带源码改动）。" >&2
  exit 1
fi

echo "[2/4] 清空产物工作树（保留 .git）"
find "$PUB" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

echo "[3/4] 同步 _site → .publish"
cp -r "$ROOT/_site/." "$PUB/"
touch "$PUB/.nojekyll"

echo "[4/4] 提交并推送 gh-pages"
cd "$PUB"
git add -A
if git diff --cached --quiet; then
  echo "       （产物无变化，跳过提交）"
else
  git -c user.name="$(git -C "$ROOT" config user.name)" \
      -c user.email="$(git -C "$ROOT" config user.email)" \
      commit -q -m "site: 构建产物 $(date +%Y-%m-%dT%H:%M:%S)"
  git push origin gh-pages
fi

cd "$ROOT"
echo "[√] 已发布。源码分支 main 未受影响；产物提交历史见 git -C .publish log"
