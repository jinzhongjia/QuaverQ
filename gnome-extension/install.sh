#!/bin/bash
set -e
SRCDIR="$(cd "$(dirname "$0")/quaverq-lyrics@quaverq" && pwd)"
EXTDIR="$HOME/.local/share/gnome-shell/extensions/quaverq-lyrics@quaverq"

echo "编译 GSettings schema..."
glib-compile-schemas "$SRCDIR/schemas/"

if [ -e "$EXTDIR" ]; then
    rm -rf "$EXTDIR"
fi
ln -s "$SRCDIR" "$EXTDIR"

echo "已安装到 $EXTDIR"
echo ""
echo "下一步:"
echo "  1. 重新登录 GNOME 会话"
echo "  2. gnome-extensions enable quaverq-lyrics@quaverq"
echo ""
echo "或者使用 GNOME Extensions 应用启用。"
