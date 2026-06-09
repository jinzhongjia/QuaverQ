#!/usr/bin/env bash
# 仅部署静态站到 Cloudflare Pages（不重新构建 AppImage，不动 R2）
# 改文案 / 改样式时跑这个。
#
# 用法：
#   scripts/deploy-docs.sh
#
# 可覆盖的环境变量：
#   PAGES_PROJECT   默认 quaverq

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PAGES_PROJECT="${PAGES_PROJECT:-quaverq}"

command -v wrangler >/dev/null 2>&1 || { echo "缺 wrangler，先 npm i -g wrangler && wrangler login" >&2; exit 1; }

echo "==> 部署 docs-site 到 Cloudflare Pages: $PAGES_PROJECT"
wrangler pages deploy docs-site \
  --project-name="$PAGES_PROJECT" \
  --branch=main \
  --commit-dirty=true
