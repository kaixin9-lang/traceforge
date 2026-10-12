#!/usr/bin/env bash
set -euo pipefail
gateway=$(ip -4 route show default | awk '{print $3;exit}')
proxy=${TRACEFORGE_PROXY:-http://$gateway:7897}
curl -sS --max-time 8 --proxy "$proxy" https://registry-1.docker.io/v2/ | grep -q UNAUTHORIZED
mkdir -p /etc/systemd/system/docker.service.d
printf '[Service]\nEnvironment="HTTP_PROXY=%s" "HTTPS_PROXY=%s" "NO_PROXY=localhost,127.0.0.1,::1"\n' "$proxy" "$proxy" > /etc/systemd/system/docker.service.d/traceforge-proxy.conf
systemctl daemon-reload
systemctl restart docker
