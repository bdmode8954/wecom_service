# 部署包（benjusi.online）— 一键上线指引

## 目录
- app/            代码（CRM、评分服务、企微回调、brain）
- env/            生产用 .env（已填入你的真实值；如需更改请修改后再执行）
- deploy/systemd  三个 systemd 服务文件（crm / scoring / wecom-webhook）
- deploy/nginx    Nginx 站点片段（/wecom/webhook → 8012）
- deploy/deploy_all.sh  一键部署脚本（OpenCloudOS 9 可用）
- tests/          企微离线仿真脚本（GET/POST）

## 一键部署
```bash
cd <本包解压目录>/deploy
bash deploy_all.sh
```

> 先确保：
> - 域名 benjusi.online 的证书链有效；
> - 服务器能连出 qyapi.weixin.qq.com 和 ark.cn-beijing.volces.com；
> - CRM 已允许在 5001 端口监听（本脚本会创建 crm.service 监听 127.0.0.1:5001）。

## 上线第一天（建议）
- 维持 `env/.env.wecom` 中 `WECOM_DRY_RUN=1`（只收不回）。
- 待观察稳定后修改为 `0`，重启：
```bash
sudo sed -i 's/^WECOM_DRY_RUN=.*/WECOM_DRY_RUN=0/' /srv/wecom/shared/.env.wecom
sudo systemctl restart wecom-webhook.service
```

## 企业微信后台保存
- URL：`https://benjusi.online/wecom/webhook`
- Token：`GCcZUdm4sHevV3i0OT`
- EncodingAESKey：`P5A9P4Omc2upVkUydVSMHeo1Yvct8Bm8hbBL99zlreh`
> 点击保存→服务器日志出现 GET→1 秒内返回明文→通过。

## 常见问题
- 403 verify failed：Token/AESKey/CorpID 任何一项不一致；或 Nginx/CDN 篡改。
- 502/504：8012 未启动或超时过长；请 `journalctl -u wecom-webhook -n 200`。
- 回消息失败：需提供 WECOM_AGENT_SECRET；并确认出网可达 `qyapi.weixin.qq.com`。

