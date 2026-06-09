#!/usr/bin/env bash
# 本地一键发版：构建 AppImage → 上传 R2（精确版本 + latest）→ 更新 version.json → 部署 Pages
#
# 用法：
#   scripts/release.sh v0.2.0
#
# 可覆盖的环境变量：
#   R2_BUCKET       默认 quaverq
#   PAGES_PROJECT   默认 quaverq
#   CDN_HOST        默认 cdn.quaverq.nvimer.org
#
# 前置条件：
#   - 已 npm i -g wrangler 且 wrangler login 完成
#   - 已 uv sync --dev

set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "用法: $0 <version>  例如 $0 v0.2.0" >&2
  exit 1
fi
if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "错误: version 必须形如 v0.2.0（vMAJOR.MINOR.PATCH）" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

R2_BUCKET="${R2_BUCKET:-quaverq}"
PAGES_PROJECT="${PAGES_PROJECT:-quaverq}"
CDN_HOST="${CDN_HOST:-cdn.quaverq.nvimer.org}"
APPIMAGE="dist/QuaverQ-x86_64.AppImage"
VERSION_JSON="docs-site/version.json"

command -v wrangler >/dev/null 2>&1 || { echo "缺 wrangler，先 npm i -g wrangler && wrangler login" >&2; exit 1; }
command -v uv       >/dev/null 2>&1 || { echo "缺 uv，参考 README 安装" >&2; exit 1; }
command -v python3  >/dev/null 2>&1 || { echo "缺 python3" >&2; exit 1; }

echo "==> [1/4] 构建 AppImage ($VERSION)"
uv run python build.py --appimage
[[ -f "$APPIMAGE" ]] || { echo "错误: 未生成 $APPIMAGE" >&2; exit 1; }

SIZE=$(stat -c '%s' "$APPIMAGE")
RELEASED_AT=$(date -u +%Y-%m-%d)
HUMAN_SIZE=$(numfmt --to=iec-i --suffix=B "$SIZE" 2>/dev/null || echo "${SIZE} bytes")

echo "==> [2/4] 上传到 R2"
echo "    $R2_BUCKET/$VERSION/QuaverQ-x86_64.AppImage  ($HUMAN_SIZE)"
wrangler r2 object put "$R2_BUCKET/$VERSION/QuaverQ-x86_64.AppImage" \
  --file "$APPIMAGE" --remote
echo "    $R2_BUCKET/latest/QuaverQ-x86_64.AppImage"
wrangler r2 object put "$R2_BUCKET/latest/QuaverQ-x86_64.AppImage" \
  --file "$APPIMAGE" --remote

echo "==> [3/4] 更新 $VERSION_JSON"
VERSION="$VERSION" SIZE="$SIZE" RELEASED_AT="$RELEASED_AT" \
CDN_HOST="$CDN_HOST" VERSION_JSON="$VERSION_JSON" \
python3 <<'PY'
import json, os, pathlib
path = pathlib.Path(os.environ["VERSION_JSON"])
data = json.loads(path.read_text()) if path.exists() else {}
data["version"] = os.environ["VERSION"]
data["filename"] = "QuaverQ-x86_64.AppImage"
data["url"] = f"https://{os.environ['CDN_HOST']}/{data['version']}/QuaverQ-x86_64.AppImage"
data["size"] = int(os.environ["SIZE"])
data["released_at"] = os.environ["RELEASED_AT"]
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print(f"    {path} 已更新")
PY

echo "==> [4/4] 部署到 Cloudflare Pages: $PAGES_PROJECT"
wrangler pages deploy docs-site \
  --project-name="$PAGES_PROJECT" \
  --branch=main \
  --commit-dirty=true

cat <<EOF

✓ 发版完成：$VERSION
  归档:   https://$CDN_HOST/$VERSION/QuaverQ-x86_64.AppImage
  Latest: https://$CDN_HOST/latest/QuaverQ-x86_64.AppImage
  体积:   $HUMAN_SIZE

提醒：$VERSION_JSON 已在工作区修改但未 commit，记得：
  git add $VERSION_JSON && git commit -m "release: $VERSION" && git tag $VERSION
EOF
