import os, time, base64, struct, hashlib, requests
from Crypto.Cipher import AES
from dotenv import load_dotenv

load_dotenv(".env.wecom")
TOKEN=os.getenv("WECOM_TOKEN"); AESKEY=os.getenv("WECOM_AES_KEY"); CORP=os.getenv("WECOM_CORP_ID")
assert TOKEN and AESKEY and CORP, "请先在 .env.wecom 填好 WECOM_TOKEN / WECOM_AES_KEY(43位) / WECOM_CORP_ID"

key=base64.b64decode(AESKEY + "="); iv=key[:16]

def enc_echo(p: bytes) -> str:
    pkg = os.urandom(16) + struct.pack(">I", len(p)) + p + CORP.encode()
    pad = 32 - (len(pkg) % 32)
    pkg += bytes([pad]) * pad
    return base64.b64encode(AES.new(key, AES.MODE_CBC, iv=iv).encrypt(pkg)).decode()

nonce="n"; ts=str(int(time.time()))
echo=enc_echo(b"test-echo")
sig=hashlib.sha1("".join(sorted([TOKEN, ts, nonce, echo])).encode()).hexdigest()
url=f"https://benjusi.online/wecom/webhook?msg_signature={sig}&timestamp={ts}&nonce={nonce}&echostr={echo}"

r = requests.get(url, timeout=5, proxies={"http": None, "https": None})
print("Status:", r.status_code, "Body:", r.text)
