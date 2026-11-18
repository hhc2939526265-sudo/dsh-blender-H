#!/usr/bin/env bash
# 打包 DSH 插件为可安装 zip（manifest.json 位于压缩包根层级）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/src/dsh_plugin"
OUT_DIR="${ROOT_DIR}/packages"
VERSION="$(python3 -c "import json;print(json.load(open('${SRC_DIR}/manifest.json'))['version'])")"
OUT_FILE="${OUT_DIR}/DSH_Blender_Bridge_Plugin_v${VERSION}.zip"

mkdir -p "${OUT_DIR}"
rm -f "${OUT_FILE}"

cd "${SRC_DIR}"
if command -v zip >/dev/null 2>&1; then
  zip -rq "${OUT_FILE}" . -x '*.DS_Store'
else
  python3 -c "
import shutil
shutil.make_archive('${OUT_FILE%.zip}', 'zip', '${SRC_DIR}')
"
fi

echo "[OK] DSH 插件包: ${OUT_FILE}"
