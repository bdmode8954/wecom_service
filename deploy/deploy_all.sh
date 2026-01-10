#!/usr/bin/env bash
set -euo pipefail

# === 0) 变量 ===
TS="$(date +%F_%H-%M-%S)"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCORING_DST="/srv/scoring"
WECOM_DST="/srv/wecom"
CRM_DST="/srv/crm"

# === 1) 目录 ===
sudo mkdir -p $SCORING_DST/releases $SCORING_DST/shared $SCORING_DST/venv
sudo mkdir -p $WECOM_DST/releases   $WECOM_DST/shared   $WECOM_DST/venv
sudo mkdir -p $CRM_DST/releases     $CRM_DST/shared     $CRM_DST/venv
sudo chown -R $USER:$USER $SCORING_DST $WECOM_DST $CRM_DST

# === 2) 拷贝代码到 releases/<TS> ===
mkdir -p $SCORING_DST/releases/$TS
mkdir -p $WECOM_DST/releases/$TS
mkdir -p $CRM_DST/releases/$TS

rsync -a "$SRC_DIR/app/services/" "$SCORING_DST/releases/$TS/services/"
rsync -a "$SRC_DIR/app/services/" "$WECOM_DST/releases/$TS/services/"
rsync -a "$SRC_DIR/app/crm/"      "$CRM_DST/releases/$TS/"

ln -sfn $SCORING_DST/releases/$TS $SCORING_DST/current
ln -sfn $WECOM_DST/releases/$TS   $WECOM_DST/current
ln -sfn $CRM_DST/releases/$TS     $CRM_DST/current

# === 3) 写入 env（使用包内 env/*.env*）===
install -m 600 "$SRC_DIR/env/.env.doubao" "$SCORING_DST/shared/.env.doubao"
install -m 600 "$SRC_DIR/env/.env.wecom"  "$WECOM_DST/shared/.env.wecom"
# CRM .env 若不存在，复制模板；如你已有线上 .env，请跳过
if [[ ! -f "$CRM_DST/shared/.env" ]]; then
  install -m 600 "$SRC_DIR/env/.env.crm" "$CRM_DST/shared/.env"
fi

# === 4) Python 虚拟环境 & 依赖 ===
python3 -m venv $SCORING_DST/venv
source $SCORING_DST/venv/bin/activate
pip install --upgrade pip
pip install -r $SCORING_DST/current/services/scoring_service/requirements.txt
deactivate

python3 -m venv $WECOM_DST/venv
source $WECOM_DST/venv/bin/activate
pip install --upgrade pip
pip install -r $WECOM_DST/current/services/wecom_webhook_service/requirements.txt
deactivate

python3 -m venv $CRM_DST/venv
source $CRM_DST/venv/bin/activate
pip install --upgrade pip
pip install -r $CRM_DST/current/requirements.txt
# gunicorn 若未在 requirements.txt，确保安装：
pip install gunicorn
deactivate

# === 5) systemd ===
sudo install -m 644 "$SRC_DIR/deploy/systemd/scoring.service"        /etc/systemd/system/scoring.service
sudo install -m 644 "$SRC_DIR/deploy/systemd/wecom-webhook.service"  /etc/systemd/system/wecom-webhook.service
sudo install -m 644 "$SRC_DIR/deploy/systemd/crm.service"            /etc/systemd/system/crm.service
sudo systemctl daemon-reload
sudo systemctl enable --now scoring wecom-webhook crm

# === 6) Nginx 片段（按需应用）===
echo "如使用 Nginx，请将 $SRC_DIR/deploy/nginx/benjusi.online.conf 合并到你的站点配置后："
echo "  sudo nginx -t && sudo systemctl reload nginx"

# === 7) 健康检查 ===
sleep 1
set +e
curl -fsS http://127.0.0.1:8010/healthz && echo " [scoring OK]"
curl -fsS http://127.0.0.1:8012/healthz && echo " [wecom OK]"
curl -fsS http://127.0.0.1:5001/        >/dev/null && echo " [crm OK]"
set -e

echo "部署完成。首日保持 WECOM_DRY_RUN=1，确认收消息正常后再改 0 并重启 wecom-webhook。"
