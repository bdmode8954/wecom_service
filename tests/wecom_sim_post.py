import os, time, base64, struct, hashlib, requests
from Crypto.Cipher import AES
from dotenv import load_dotenv

load_dotenv(".env.wecom")
TOKEN=os.getenv("WECOM_TOKEN"); AESKEY=os.getenv("WECOM_AES_KEY"); CORP=os.getenv("WECOM_CORP_ID")
AGENT=os.getenv("WECOM_AGENT_ID") or "1000002"

key=base64.b64decode(AESKEY + "="); iv=key[:16]

def enc_msg(xml: bytes) -> str:
    pkg = os.urandom(16) + struct.pack(">I", len(xml)) + xml + CORP.encode()
    pad = 32 - (len(pkg) % 32)
    pkg += bytes([pad]) * pad
    return base64.b64encode(AES.new(key, AES.MODE_CBC, iv=iv).encrypt(pkg)).decode()

FROM="u_test"  # 上线后可改成企业内真实可触达的 userId
plain=f"<xml><ToUserName><![CDATA[{CORP}]]></ToUserName><FromUserName><![CDATA[{FROM}]]></FromUserName><CreateTime>{int(time.time())}</CreateTime><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[测试接口-你好]]></Content><MsgId>1234567890</MsgId></xml>".encode()

encrypt=enc_msg(plain)
nonce="n2"; ts=str(int(time.time()))
sig=hashlib.sha1("".join(sorted([TOKEN, ts, nonce, encrypt])).encode()).hexdigest()
cipher=f"<xml><ToUserName><![CDATA[{CORP}]]></ToUserName><AgentID>{AGENT}</AgentID><Encrypt><![CDATA[{encrypt}]]></Encrypt></xml>"
url=f"https://benjusi.online/wecom/webhook?msg_signature={sig}&timestamp={ts}&nonce={nonce}"

r = requests.post(url, data=cipher.encode(), headers={"Content-Type":"text/xml"}, timeout=5, proxies={"http": None, "https": None})
print("POST status:", r.status_code, "body:", r.text)
