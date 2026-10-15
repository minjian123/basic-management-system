#!/bin/bash
# 在 Ubuntu 侧安装「重启到 Windows」桌面快捷方式
# 用法：bash 安装-重启到Windows快捷方式.sh
#
# 作用：装好后桌面上出现「重启到 Windows」，双击（带确认框）即可设 UEFI
#       BootNext 指向 Windows 并重启；只生效一次，之后回到默认顺序。
#
# 卸载：sudo rm -f /usr/local/bin/reboot-to-windows \
#                  /etc/sudoers.d/reboot-to-windows \
#                  ~/.local/share/applications/reboot-to-windows.desktop \
#                  "$(xdg-user-dir DESKTOP)/reboot-to-windows.desktop"

set -euo pipefail

# ---------- 0. 基本检查 ----------
if [ "$(id -u)" -eq 0 ]; then
  echo "请不要用 root 直接运行（脚本内部会按需 sudo）。" >&2
  exit 1
fi

if [ ! -d /sys/firmware/efi ]; then
  echo "当前不是 UEFI 启动，本脚本不适用。" >&2
  exit 1
fi

echo "== 重启到 Windows 快捷方式 安装程序 =="
echo

# ---------- 1. 确定 Windows 的 UEFI 启动项编号 ----------
if ! command -v efibootmgr >/dev/null 2>&1; then
  echo "缺少 efibootmgr，正在安装..."
  sudo apt-get update -qq && sudo apt-get install -y efibootmgr
fi

echo "当前固件启动项："
efibootmgr | sed 's/^/  /'
echo

# 优先匹配描述含 Windows 的项；否则退回 0000
WIN_NUM="$(efibootmgr | awk -F'[ *]+' '/^Boot[0-9A-Fa-f]{4}/ && tolower($0) ~ /windows/ {print substr($1,5,4); exit}')"
if [ -z "${WIN_NUM:-}" ]; then
  WIN_NUM="0000"
  echo "未从描述中识别到 Windows 项，回退使用 0000。"
fi
echo "将使用 Windows 启动项编号：$WIN_NUM"
echo "（若不对，安装后编辑 /usr/local/bin/reboot-to-windows 里的编号）"
echo

# ---------- 2. 写入切换脚本 ----------
sudo tee /usr/local/bin/reboot-to-windows >/dev/null <<EOF
#!/bin/bash
# 设置 UEFI BootNext 指向 Windows(${WIN_NUM})，然后重启（只生效一次）。
set -u

if command -v zenity >/dev/null 2>&1; then
  zenity --question --title="重启到 Windows" \\
         --text="确定重启回 Windows 吗？\\n\\n请先保存所有未保存的工作。" \\
         --ok-label="重启" --cancel-label="取消" || exit 0
fi

if ! efibootmgr -n ${WIN_NUM} >/dev/null 2>&1; then
  msg="设置下次启动项失败（efibootmgr -n ${WIN_NUM}）。"
  echo "\$msg" >&2
  command -v zenity >/dev/null 2>&1 && \\
    zenity --error --title="重启到 Windows 失败" --text="\$msg"
  exit 1
fi

systemctl reboot
EOF
sudo chmod 755 /usr/local/bin/reboot-to-windows
echo "已写入 /usr/local/bin/reboot-to-windows"

# ---------- 3. 免密规则（仅这一条命令免密） ----------
echo "$USER ALL=(root) NOPASSWD: /usr/local/bin/reboot-to-windows" | sudo tee /etc/sudoers.d/reboot-to-windows >/dev/null
sudo chmod 440 /etc/sudoers.d/reboot-to-windows
if sudo visudo -c -f /etc/sudoers.d/reboot-to-windows >/dev/null 2>&1; then
  echo "已写入免密规则 /etc/sudoers.d/reboot-to-windows"
else
  echo "免密规则语法校验失败，已回滚该文件。" >&2
  sudo rm -f /etc/sudoers.d/reboot-to-windows
  exit 1
fi

# ---------- 4. 桌面项 ----------
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/桌面")"
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR" "$DESKTOP_DIR"

cat > "$APP_DIR/reboot-to-windows.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=重启到 Windows
Name[en]=Reboot to Windows
Comment=设置下次启动进入 Windows 并立即重启
Exec=sudo -n /usr/local/bin/reboot-to-windows
Icon=system-reboot
Terminal=false
Categories=System;
EOF

cp "$APP_DIR/reboot-to-windows.desktop" "$DESKTOP_DIR/"
chmod +x "$DESKTOP_DIR/reboot-to-windows.desktop"

# GNOME 要求桌面图标标记 trusted，否则双击被拦
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/reboot-to-windows.desktop" metadata::trusted true 2>/dev/null || true
fi

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$APP_DIR/reboot-to-windows.desktop" && echo "desktop 文件语法校验通过"
fi

echo
echo "== 安装完成 =="
echo "桌面图标：$DESKTOP_DIR/reboot-to-windows.desktop"
echo "应用菜单：$APP_DIR/reboot-to-windows.desktop"
echo
echo "双击「重启到 Windows」即可（会弹确认框）。"
