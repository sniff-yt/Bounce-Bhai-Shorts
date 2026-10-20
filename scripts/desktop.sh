#!/usr/bin/env bash
# Real studio desktop for the dashboard: Xvfb + Openbox + taskbar, a real xterm streaming the job's
# output, a real Chrome the director drives, and screenshots every few seconds -> out/live/screen.jpg.
# Never fails the job.
set +e
cd "$(dirname "$0")/.."
mkdir -p out/live
sudo apt-get install -y -qq --no-install-recommends xvfb openbox tint2 xterm xdotool imagemagick \
  x11-xserver-utils fonts-dejavu-core fonts-noto-color-emoji fonts-noto-core >/dev/null 2>&1
command -v Xvfb >/dev/null || { echo "desktop: Xvfb missing, skipping"; exit 0; }
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
sleep 1.5
export DISPLAY=:99
[ -n "${GITHUB_ENV:-}" ] && echo "BB_DISPLAY=:99" >> "$GITHUB_ENV"
convert -size 1280x800 radial-gradient:'#FFB38A'-'#5a2214' /tmp/wall.png 2>/dev/null && display -window root /tmp/wall.png >/dev/null 2>&1 &
openbox >/dev/null 2>&1 &
sleep 0.5
mkdir -p ~/.config/tint2
cat > ~/.config/tint2/tint2rc <<'RC'
panel_items = TSC
panel_size = 100% 34
panel_position = bottom center horizontal
panel_background_id = 1
rounded = 0
border_width = 0
background_color = #14120f 88
border_color = #000000 0
taskbar_mode = single_desktop
task_text = 1
task_icon = 1
task_maximum_size = 220 30
task_font = DejaVu Sans 9
task_font_color = #e8e2d6 100
task_active_background_id = 2
rounded = 6
border_width = 0
background_color = #FF6A3D 70
border_color = #000000 0
time1_format = %H:%M
time1_font = DejaVu Sans Bold 10
clock_font_color = #ffffff 100
RC
tint2 >/dev/null 2>&1 &
touch out/live/console.log
xterm -T "Terminal — bounce-bhai@studio" -fa "DejaVu Sans Mono" -fs 9 -geometry 78x52+10+10 \
  -bg "#14120f" -fg "#e8e2d6" -cr "#FF8A5C" -bc -xrm "XTerm*selectToClipboard: false" \
  -e tail -n 300 -F out/live/console.log >/dev/null 2>&1 &
nohup python3 scripts/director.py >/tmp/director.log 2>&1 &
echo "desktop: up on :99"
