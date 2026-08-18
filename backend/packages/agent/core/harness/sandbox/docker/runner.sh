#!/bin/sh
# rag-nsjail 容器入口：用 nsjail 包住 python 执行挂载进来的脚本。
#
# 用法：rag-nsjail:py310 <script_basename> <venv_site_packages>
#   <script_basename>    挂载的 /sb/work 下的脚本文件名（如 script.py）
#   <venv_site_packages> venv 的 site-packages 在容器内路径（/sb/env/lib/python3.10/site-packages）
#
# 用 CLI 标志而非 config 文件：Docker Desktop (Mac) 的 VM 文件系统不支持
# nsjail 在 buildMountTree 里对 bind 挂载的 MS_REMOUNT，CLI standalone 路径可绕过。
# 环境变量经 --keep_env 透传（SandboxRuntime 已把 PYTHONPATH 指向挂载的 venv，
# 使容器内 python3.10 复用宿主装好的依赖）。
set -eu
SCRIPT="$1"
SITE_PACKAGES="${2:-}"
[ -n "$SITE_PACKAGES" ] && export PYTHONPATH="$SITE_PACKAGES"
export PYTHONDONTWRITEBYTECODE=1
exec /usr/local/bin/nsjail \
  -Mo --chroot / --cwd /sb/work \
  --bindmount /sb --bindmount /dev --bindmount /proc --bindmount /tmp \
  --time_limit 60 --keep_env \
  -- /usr/local/bin/python "/sb/work/${SCRIPT}"
