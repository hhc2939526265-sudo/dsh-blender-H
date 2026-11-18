#!/usr/bin/env bash
# 一键打包：Blender Addon 安装包 + DSH 插件安装包 + 完整源码包
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/packages"
VERSION="$(python3 -c "import json;print(json.load(open('${ROOT_DIR}/src/dsh_plugin/manifest.json'))['version'])")"

mkdir -p "${OUT_DIR}"

echo "==> 打包 Blender Addon"
bash "${ROOT_DIR}/scripts/package_blender_addon.sh"

echo "==> 打包 DSH 插件"
bash "${ROOT_DIR}/scripts/package_dsh_plugin.sh"

echo "==> 打包完整源码"
SRC_ARCHIVE="${OUT_DIR}/DSH_Blender_Bridge_Source_v${VERSION}.zip"
rm -f "${SRC_ARCHIVE}"
cd "${ROOT_DIR}"
if command -v zip >/dev/null 2>&1; then
  zip -rq "${SRC_ARCHIVE}" . \
    -x 'packages/*' -x '*/__pycache__/*' -x '*.pyc' \
    -x '*/transfer_cache/*' -x '*/render_output/*' -x '*/logs/*' -x '*/backups/*'
else
  python3 -c "
import shutil
shutil.make_archive('${SRC_ARCHIVE%.zip}', 'zip', '${ROOT_DIR}')
"
fi

echo "[OK] 全部产物位于 ${OUT_DIR}"
ls -lh "${OUT_DIR}"
