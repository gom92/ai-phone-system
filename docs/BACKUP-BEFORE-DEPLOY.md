# 部署前端口/服务快照
时间: 2026-11-24T12:02:16+00:00

## TCP 监听
State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess
LISTEN 0      0          127.0.0.1:8899      0.0.0.0:*    users:(("python",pid=6295,fd=7))

## UDP 监听
State Recv-Q Send-Q Local Address:Port Peer Address:PortProcess

## 主要进程
USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root          67  9.6  6.1 2071584 496880 ?      Sl   11:19   4:08 /opt/hatch/bin/hatch daemon --runtime-cell-leader=2364
root        6295  0.1  1.6 224232 133008 ?       S    11:55   0:00 /home/hatch/workspace/phone-number-identifier/venv/bin/python /home/hatch/workspace/phone-number-identifier/app.py
root        7658  0.1  0.3 105328 26088 ?        Ssl  12:00   0:00 python3 bridge.py serve
root         745  0.2  0.1  38068  9104 ?        Sl   11:19   0:07 /opt/hatch/bin/hatch-execd --runtime-cell-leader=2364
root           1  0.0  0.0  21068  6668 ?        Ss   11:19   0:00 /usr/lib/systemd/systemd
root          17  0.0  0.0  33972  5608 ?        Ss   11:19   0:00 /usr/lib/systemd/systemd-journald
root        7986  0.0  0.0   7916  4384 ?        R    12:02   0:00 ps aux --sort=-%mem
root        7979  0.0  0.0   4344  3592 ?        S    12:02   0:00 /bin/bash --norc --noprofile -c umask 0007; cd ~/workspace/ai-phone-system && { echo "# ???????????????/????????????"; echo "??????: $(date -Is)"; echo; echo "## TCP ??????"; ss -tlnp; echo; echo "## UDP ??????"; ss -ulnp; echo; echo "## ????????????"; ps aux --sort=-%mem | head -25; echo; echo "## ??????"; free -m; } > docs/BACKUP-BEFORE-DEPLOY.md && cat docs/BACKUP-BEFORE-DEPLOY.md
root        7980  0.0  0.0   4348  3552 ?        S    12:02   0:00 /bin/bash --norc --noprofile -c umask 0007; echo "--- DNS ---"; getent hosts text.pollinations.ai github.com raw.githubusercontent.com 2>&1 | head -5; echo "--- HTTP egress ---"; curl -s -m 15 -o /dev/null -w "pollinations: %{http_code}\n" https://text.pollinations.ai/hello; curl -s -m 15 -o /dev/null -w "github: %{http_code}\n" https://github.com; echo "--- UDP egress test (STUN to Google) ---"; python3 - <<'EOF' import socket s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) s.settimeout(5) # STUN binding request (20 bytes, magic cookie) req = bytes([0x00,0x01,0x00,0x00,0x21,0x12,0xa4,0x42]) + bytes(12) try:     s.sendto(req, ("stun.l.google.com", 19302))     data, addr = s.recvfrom(1024)     print("UDP OK: got STUN reply", len(data), "bytes from", addr) except Exception as e:     print("UDP FAIL:", e) s.close() EOF echo "--- local IP ---"; hostname -I 2>/dev/null; ip -4 addr show 2>/dev/null | grep -E "inet " | head -5
root        7656  0.0  0.0   4468  2084 ?        S    12:00   0:00 /bin/bash -- /home/hatch/hooks/scripts/wechat-bridge-watchdog.sh
root        7987  0.0  0.0   2728  1716 ?        S    12:02   0:00 head -25
root        7988  0.0  0.0    432    12 ?        D    12:02   0:00 [curl]

## 内存
               total        used        free      shared  buff/cache   available
Mem:            7934        6582         173          80        1514        1351
Swap:           1023         427         596
