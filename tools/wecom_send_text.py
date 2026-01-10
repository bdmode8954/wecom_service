from dotenv import load_dotenv
load_dotenv("/srv/wecom/shared/.env.wecom")
#!/usr/bin/env python3
import os, sys, requests
CORP_ID   = os.getenv("WECOM_CORP_ID", "ww196510876c5e51f2")
AGENT_ID  = int(os.getenv("WECOM_AGENT_ID", "1000002"))
SECRET    = os.getenv("WECOM_AGENT_SECRET")  # 必须是“自建应用”的 Secret

def send_text(to_user: str, text: str):
    tok = requests.get("https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                       params={"corpid": CORP_ID, "corpsecret": SECRET}, timeout=8).json()
    if tok.get("errcode") != 0:
        raise SystemExit(f"gettoken fail: {tok}")
    access_token = tok["access_token"]
    data = {"touser": to_user, "msgtype": "text", "agentid": AGENT_ID,
            "text": {"content": text}, "safe": 0}
    r = requests.post(f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}",
                      json=data, timeout=8).json()
    print(r)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: wecom_send_text.py <UserID或@all> <文本>")
        sys.exit(1)
    send_text(sys.argv[1], sys.argv[2])
