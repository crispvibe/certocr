#!/bin/bash
set -euo pipefail
# CentOS 7：RapidOCR（ONNX），不依赖 Paddle，避免 libstdc++ 不兼容
APP_DIR="/www/server/heyu-license-ocr"
CONDA_PREFIX="/opt/miniconda3"
SERVICE_NAME="heyu-license-ocr"

if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
fi
swapon /swapfile 2>/dev/null || true

if [ ! -x "${CONDA_PREFIX}/bin/python" ]; then
  cd /tmp
  curl -fsSL -o miniconda.sh https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py39_4.12.0-Linux-x86_64.sh
  bash miniconda.sh -b -p "${CONDA_PREFIX}"
fi

PIP="${CONDA_PREFIX}/bin/pip"
"${PIP}" install -i https://pypi.tuna.tsinghua.edu.cn/simple -U pip setuptools wheel
"${PIP}" install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  -r "${APP_DIR}/requirements.txt"

cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Heyu License OCR (RapidOCR)
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
Environment=PORT=8091
ExecStart=${CONDA_PREFIX}/bin/python ${APP_DIR}/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}
sleep 3
curl -sf "http://127.0.0.1:8091/health" && echo " OCR OK"
