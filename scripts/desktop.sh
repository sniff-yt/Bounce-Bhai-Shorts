#!/usr/bin/env bash
# Full studio desktop for the dashboard (XFCE on a virtual screen): taskbar, file manager, text editor,
# terminal streaming the real job output, Chrome + studio apps (AI Chat, Voice Studio, Video Editor,
# YouTube Upload). scripts/director.py switches between them as the job works and screenshots the screen
# every few seconds -> out/live/screen.jpg. Never fails the job.
set +e
cd "$(dirname "$0")/.."
ROOT="$PWD"
mkdir -p out/live/desk
cp -f scripts/desk/* out/live/desk/ 2>/dev/null
sudo apt-get install -y -qq --no-install-recommends xvfb dbus-x11 xfwm4 xfce4-panel xfdesktop4 xfconf xfce4-terminal \
  thunar mousepad adwaita-icon-theme x11-xserver-utils xdotool imagemagick fonts-dejavu-core fonts-noto-color-emoji fonts-noto-core >/dev/null 2>&1
command -v Xvfb >/dev/null || { echo "desktop: Xvfb missing, skipping"; exit 0; }
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
sleep 1.5
export DISPLAY=:99
eval "$(dbus-launch --sh-syntax)"
env | grep -E '^(DBUS_SESSION_BUS_ADDRESS|DISPLAY)=' > /tmp/bb-desktop.env
CFG=~/.config/xfce4/xfconf/xfce-perchannel-xml
mkdir -p "$CFG"
[ -f /etc/xdg/xfce4/panel/default.xml ] && cp -f /etc/xdg/xfce4/panel/default.xml "$CFG/xfce4-panel.xml"
convert -size 1280x800 radial-gradient:'#FFB38A'-'#5a2214' /tmp/wall.png 2>/dev/null
xfwm4 --compositor=off >/dev/null 2>&1 &
sleep 1
xfdesktop >/dev/null 2>&1 &
xfce4-panel >/dev/null 2>&1 &
sleep 2.5
# one clean top panel (drop the launcher dock), studio wallpaper
xfconf-query -c xfce4-panel -p /panels -t int -s 1 --force-array 2>/dev/null && xfce4-panel -r >/dev/null 2>&1 &
MON=$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')
for m in monitorscreen monitor0 "monitor${MON:-screen}"; do
  xfconf-query -c xfce4-desktop -n -t string -p "/backdrop/screen0/$m/workspace0/last-image" -s /tmp/wall.png 2>/dev/null
  xfconf-query -c xfce4-desktop -n -t int -p "/backdrop/screen0/$m/workspace0/image-style" -s 5 2>/dev/null
done
for p in $(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep last-image); do xfconf-query -c xfce4-desktop -p "$p" -s /tmp/wall.png; done
xfdesktop --reload >/dev/null 2>&1 &
touch out/live/console.log
xfce4-terminal --title "Terminal — bounce-bhai@studio" --geometry 92x40+20+40 --hide-menubar \
  --font "DejaVu Sans Mono 9" -x tail -n 300 -F "$ROOT/out/live/console.log" >/dev/null 2>&1 &
nohup python3 scripts/director.py >/tmp/director.log 2>&1 &
echo "desktop: up on :99"
