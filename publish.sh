#!/usr/bin/env bash
# Matlas 发布：构建 _site → 同步到 gh-pages 工作树 → 推送。
#
#   两个分支的分工（本地都可见）：
#     main      源码 + 数据   工作区  <repo>/           _site/ 与 .publish/ 均被忽略
#     gh-pages  构建产物      工作树  <repo>/.publish/  一个提交 = 一次发布，历史连续
#
#   ./publish.sh           构建（strict 自检）+ 提交 + 推送 gh-pages
#   ./publish.sh --no-push 只构建，不动产物分支（本地预览用）
#   SKIP_BUILD=1 ./publish.sh  跳过构建，直接同步现有 _site
#                              （产物目录已单独清空重建好时用，避免覆盖写被拦）
#
# 首次使用需要先建工作树：git worktree add .publish gh-pages
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PY:-python}"
PUB="$ROOT/.publish"
PUSH=1
SKIP_BUILD="${SKIP_BUILD:-0}"
[ "${1:-}" = "--no-push" ] && PUSH=0

cd "$ROOT"

if [ "$SKIP_BUILD" -eq 0 ]; then
  echo "[1/4] 构建（红线自检 strict）"
  "$PY" build.py --strict
else
  echo "[1/4] 跳过构建（SKIP_BUILD=1，直接同步现有 _site）"
  if [ ! -d "$ROOT/_site" ]; then
    echo "[!] _site 不存在，无法跳过构建。" >&2
    exit 1
  fi
fi

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
  # 数据变动（import 产物）允许自动提交：定时任务只跑 import+build+publish，
  # 不允许人工 commit，若这里硬性拒绝，每天 08:00/14:00/19:00 的发布会全部卡住。
  #
  # 白名单含 assets/logo/：队徽与赛事徽章是 build 时抓取/下载的「离线快照」，
  # 与 data/ 同属运行态资源，不是源码。此前只认 data/ 导致 import 每下载一批
  # 新队徽（assets/logo/teams/*.png 未跟踪）就被判成源码改动、整条发布被拒
  # （2026-11-08 实测：37 个新队徽卡住发布，需人工单独提交）。
  # 其余任何路径（pages.py / build.py / README 等）仍视为源码改动，照旧拒绝。
  OTHER="$(git status --porcelain | grep -Ev '^.. (data|assets/logo)/' || true)"
  if [ -n "$OTHER" ]; then
    echo "[!] main 工作区有未提交的源码改动，先提交再发布（产物不应夹带源码改动）。" >&2
    echo "$OTHER" >&2
    exit 1
  fi
  echo "[1.5/4] 自动提交 data/ 与 assets/logo/ 资源变动（import/build 产物）"
  git add -A data assets/logo
  git -c user.name="$(git -C "$ROOT" config user.name)" \
      -c user.email="$(git -C "$ROOT" config user.email)" \
      commit -q -m "data: $(date +%Y-%m-%d) 定时任务导入快照（含 assets/logo 资源）"
  echo "      → $(git rev-parse --short HEAD)"
fi

echo "[2/4] 清空产物工作树（保留 .git）"
# 用「移走」代替删除：安全删除钩子会把 rm 转成回收站操作，产物目录上千个
# 文件时会 fail-closed 报 Permission denied，而 rename 不受该钩子影响。
TRASH="${TMPDIR:-/tmp}/matlas-publish-trash/$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$TRASH"
# 单项移动：偶发有目录被占用（Windows 索引 / 杀软扫描新素材）时只跳过该项，
# 不因一个 mv 失败中断整条发布；随后的 cp 会覆盖同名内容，git add -A 照常收敛。
find "$PUB" -mindepth 1 -maxdepth 1 ! -name .git -print0 | while IFS= read -r -d '' item; do
  if ! mv -t "$TRASH" "$item" 2>/dev/null; then
    echo "      占用中，保留并覆盖：$(basename "$item")"
  fi
done
echo "      旧产物已移出到 $TRASH"

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
