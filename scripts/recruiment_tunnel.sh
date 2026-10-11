#!/usr/bin/env bash
# SSH 隧道保活（可选的历史部署辅助脚本）
#
# 用途：招聘链路早期部署在远端服务器时，本机通过 SSH 隧道访问远端 MySQL / NocoDB：
#   本地 ${LOCAL_MYSQL_PORT}  -> 远端 127.0.0.1:${REMOTE_MYSQL_PORT}   (MySQL)
#   本地 ${LOCAL_NOCODB_PORT} -> 远端 127.0.0.1:${REMOTE_NOCODB_PORT} (NocoDB)
#
# 用法：
#   TUNNEL_HOST=myserver ./scripts/recruiment_tunnel.sh
#
# 环境变量：TUNNEL_HOST（必填）、TUNNEL_USER、LOCAL_MYSQL_PORT、REMOTE_MYSQL_PORT、
#           LOCAL_NOCODB_PORT、REMOTE_NOCODB_PORT
set -euo pipefail

TUNNEL_HOST="${TUNNEL_HOST:-}"
LOCAL_MYSQL_PORT="${LOCAL_MYSQL_PORT:-13306}"
REMOTE_MYSQL_PORT="${REMOTE_MYSQL_PORT:-3306}"
LOCAL_NOCODB_PORT="${LOCAL_NOCODB_PORT:-18080}"
REMOTE_NOCODB_PORT="${REMOTE_NOCODB_PORT:-18080}"

if [ -z "$TUNNEL_HOST" ]; then
  echo "error: 请设置 TUNNEL_HOST（例如 TUNNEL_HOST=myserver $0）" >&2
  exit 2
fi

target="${TUNNEL_USER:+${TUNNEL_USER}@}${TUNNEL_HOST}"

exec ssh -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -N -L "127.0.0.1:${LOCAL_MYSQL_PORT}:127.0.0.1:${REMOTE_MYSQL_PORT}" \
     -L "127.0.0.1:${LOCAL_NOCODB_PORT}:127.0.0.1:${REMOTE_NOCODB_PORT}" \
     "$target"
