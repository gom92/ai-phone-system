#!/bin/bash
# install-configs.sh - generate secrets (if missing) and install Asterisk configs.
# - Secrets live ONLY in secrets/sip-credentials.txt (mode 600) and in
#   /etc/asterisk/{pjsip,manager}.conf (root:asterisk 640). Never in git/chat/logs.
# - Templates in config/asterisk/*.template carry __PLACEHOLDER__ passwords.
set -euo pipefail
BASE="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS="$BASE/secrets/sip-credentials.txt"
ASTCONF=/etc/asterisk

mkdir -p "$BASE/secrets" "$BASE/data" "$BASE/recordings" "$BASE/logs"
chmod 700 "$BASE/secrets"

if [ ! -f "$SECRETS" ]; then
  {
    echo "SIP_1001_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
    echo "SIP_1002_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
    echo "AMI_ADMIN_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
  } > "$SECRETS"
  chmod 600 "$SECRETS"
  echo "generated $SECRETS"
fi
# shellcheck disable=SC1090
set -a; . "$SECRETS"; set +a

sed -e "s/__SIP_1001_PASS__/$SIP_1001_PASS/g" \
    -e "s/__SIP_1002_PASS__/$SIP_1002_PASS/g" \
    "$BASE/config/asterisk/pjsip.conf.template" > "$ASTCONF/pjsip.conf"
sed -e "s/__AMI_ADMIN_PASS__/$AMI_ADMIN_PASS/g" \
    "$BASE/config/asterisk/manager.conf.template" > "$ASTCONF/manager.conf"
cp "$BASE/config/asterisk/extensions.conf" "$BASE/config/asterisk/rtp.conf" \
   "$BASE/config/asterisk/cdr.conf" "$BASE/config/asterisk/modules.conf" "$ASTCONF/"

chown root:asterisk "$ASTCONF/pjsip.conf" "$ASTCONF/manager.conf" 2>/dev/null || true
chmod 640 "$ASTCONF/pjsip.conf" "$ASTCONF/manager.conf"
chmod 644 "$ASTCONF/extensions.conf" "$ASTCONF/rtp.conf" "$ASTCONF/cdr.conf" "$ASTCONF/modules.conf"

# systemd drop-in so Asterisk runs with the UDP shim (see lib/udp_connect_shim.c)
mkdir -p /etc/systemd/system/asterisk.service.d
cat > /etc/systemd/system/asterisk.service.d/shim.conf <<EOF
[Service]
Environment=LD_PRELOAD=$BASE/lib/libudp_connect_shim.so
EOF
systemctl daemon-reload 2>/dev/null || true
echo "configs installed; secrets in $SECRETS (600)"
