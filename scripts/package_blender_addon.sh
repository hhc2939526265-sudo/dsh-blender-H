#!/usr/bin/env bash
# 打包 Blender Addon 为可直接安装的 zip（__init__.py 位于压缩包根层级）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/src/blender_addon"
OUT_DIR="${ROOT_DIR}/packages"
VERSION="$(grep -oE '"version": \([0-9, ]+\)' "${SRC_DIR}/__init__.py" | head -1 | grep -oE '[0-9]+' | paste -sd. -)"
VERSION="${VERSION:-1.0.0}"
OUT_FILE="${OUT_DIR}/DSH_Blender_Bridge_Addon_v${VERSION}.zip"

mkdir -p "${OUT_DIR}"
rm -f "${OUT_FILE}"

# 清理 Python 缓存
find "${SRC_DIR}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

cd "${SRC_DIR}"
if command -v zip >/dev/null 2>&1; then
  zip -rq "${OUT_FILE}" . -x '*/__pycache__/*' -x '*.pyc'
else
  python3 -c "
import shutil, os
shutil.make_archive('${OUT_FILE%.zip}', 'zip', '${SRC_DIR}')
"
fi

echo "[OK] Blender Addon 包: ${OUT_FILE}"
