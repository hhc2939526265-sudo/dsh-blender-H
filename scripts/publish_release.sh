#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# GitHub 一键发布脚本（Linux / macOS）
# 前提：已通过 `gh auth login` 完成 GitHub 授权，或环境变量 GH_TOKEN 有效。
# 流程：校验登录态 → 推送 main 分支与 v1.1.5 标签 → 创建 Release 并上传三个安装包。
#
# 用法：
#   bash scripts/publish_release.sh            # 仓库已存在
#   bash scripts/publish_release.sh --create   # 仓库尚不存在，先创建（默认私有，可改 --public）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SLUG="hhc2939526265-sudo/dsh-blender-H"
TAG="v1.1.5"
PACKAGES_DIR="packages"

# ---- 1. 校验 gh 登录态 ----
if ! command -v gh >/dev/null 2>&1; then
  echo "[ERROR] 未安装 GitHub CLI（gh）。请先安装：https://cli.github.com/" >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "[ERROR] 尚未登录 GitHub。请先执行：gh auth login" >&2
  exit 1
fi

# ---- 2. 可选：创建远程仓库 ----
if [[ "${1:-}" == "--create" ]]; then
  VISIBILITY="private"
  if [[ "${2:-}" == "--public" ]]; then VISIBILITY="public"; fi
  echo "==> 创建远程仓库 ${SLUG}（${VISIBILITY}）"
  gh repo create "${SLUG}" --"${VISIBILITY}" --source=. --remote=origin --description "DSH ↔ Blender 双向实时桥接插件" || true
fi

# ---- 3. 推送分支与标签 ----
echo "==> 推送 main 分支"
git push -u origin main
echo "==> 推送标签 ${TAG}"
git push origin "${TAG}"

# ---- 4. 创建 Release 并上传产物 ----
echo "==> 创建 Release ${TAG}"
gh release create "${TAG}" \
  "${PACKAGES_DIR}/DSH_Blender_Bridge_Addon_${TAG}.zip" \
  "${PACKAGES_DIR}/DSH_Blender_Bridge_Plugin_${TAG}.zip" \
  "${PACKAGES_DIR}/DSH_Blender_Bridge_Source_${TAG}.zip" \
  --title "DSH ↔ Blender Bridge ${TAG}" \
  --notes-file CHANGELOG.md \
  --latest

echo "[OK] Release 发布完成：https://github.com/${SLUG}/releases/tag/${TAG}"
