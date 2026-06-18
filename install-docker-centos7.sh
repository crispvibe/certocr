#!/bin/bash
set -euo pipefail
# CentOS 7 安装 Docker CE 并启动 OCR（需 root）
if ! command -v docker >/dev/null 2>&1; then
  yum install -y yum-utils
  yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo || true
  yum install -y docker-ce docker-ce-cli containerd.io || yum install -y docker
  systemctl enable docker
  systemctl start docker
fi
if ! swapon --show | grep -q swapfile; then
  if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile || true
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
cd /www/server/heyu-license-ocr
docker compose up -d --build
curl -sf http://127.0.0.1:8091/health && echo " OCR OK"
