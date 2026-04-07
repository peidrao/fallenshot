#!/usr/bin/env bash
# install.sh — Instala fallenshot no sistema
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ------------------------------------------------------------------
# 1. Dependências do sistema (só instala o que falta)
# ------------------------------------------------------------------
DEPS=(python3 python3-gi python3-gi-cairo python3-dbus
      gir1.2-gtk-4.0 gir1.2-gdkpixbuf-2.0
      gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0
      gstreamer1.0-plugins-base gstreamer1.0-pipewire
      xdg-desktop-portal xdg-desktop-portal-gnome
      wl-clipboard)

MISSING=()
for pkg in "${DEPS[@]}"; do
    dpkg -s "$pkg" &>/dev/null || MISSING+=("$pkg")
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "==> Instalando dependências faltantes: ${MISSING[*]}"
    sudo apt-get install -y "${MISSING[@]}"
else
    echo "==> Dependências já instaladas."
fi

# ------------------------------------------------------------------
# 2. Executável
# ------------------------------------------------------------------
chmod +x "$SCRIPT_DIR/fallenshot"
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
ln -sf "$SCRIPT_DIR/fallenshot" "$LOCAL_BIN/fallenshot"
echo "==> Executável: $LOCAL_BIN/fallenshot"

# ------------------------------------------------------------------
# 3. Ícone
# ------------------------------------------------------------------
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/icons/fallenshot.png" "$ICON_DIR/fallenshot.png"
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "==> Ícone instalado."

# ------------------------------------------------------------------
# 4. Entrada .desktop (aparece no launcher GNOME)
# ------------------------------------------------------------------
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cp "$SCRIPT_DIR/io.github.fallenshot.desktop" "$DESKTOP_DIR/io.github.fallenshot.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
echo "==> Atalho no launcher instalado."

# ------------------------------------------------------------------
echo ""
echo "✓ Pronto! Para usar:"
echo "  fallenshot"
echo ""
echo "Para configurar PrintScreen no GNOME:"
echo "  Configurações → Teclado → Atalhos personalizados"
echo "  Comando: $LOCAL_BIN/fallenshot"
