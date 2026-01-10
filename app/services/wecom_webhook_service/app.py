# ==== BRAIN AUTO-INJECT ====
import os, time, re, requests
try:
    from dotenv import load_dotenv
    load_dotenv("/srv/wecom/shared/.env.wecom")
except Exception:
    pass

BRAIN_URL = os.getenv("BRAIN_URL", "http://127.0.0.1:7870/api/ask")

def _clean_text(s: str) -> str:
    if not isinstance(s, str): return ""
    s = re.sub(r'\[(?:图片|image|img)\]', '', s)
    s = re.sub(r'\[[^\]]+\]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:60]

def ask_brain(text, user_id=""):
    t0 = time.time()
    try:
        for i in (0, 1):  # 一次重试
            try:
                r = requests.post(BRAIN_URL, json={"question": text, "user_id": user_id}, timeout=15)
                j = r.json()
                meta = j.get("meta", {}) or {}
                ans  = _clean_text(j.get("answer") or "")
                conf = float(meta.get("confidence") or 0)
                if conf < 0.60 or not ans:
                    ans = "我先核对您的情况，稍后给您更精准方案～"
                print({"tag":"brain_call","ok":True,"ms":int((time.time()-t0)*1000),"conf":conf})
                return ans
            except requests.exceptions.ReadTimeout:
                if i == 0:
                    time.sleep(0.5)
                    continue
                raise
    except Exception as e:
        print({"tag":"brain_call","ok":False,"err":str(e)})
        return "系统繁忙，已转人工处理～"

_orig_post = requests.post
def _post_with_brain(url, *args, **kwargs):
    try:
        if "qyapi.weixin.qq.com/cgi-bin/message/send" in str(url):
            js = kwargs.get("json")
            if isinstance(js, dict):
                touser = js.get("touser") or js.get("to_user") or js.get("ToUserName") or ""

                md = js.get("markdown")
                if isinstance(md, dict) and isinstance(md.get("content"), str):
                    md["content"] = ask_brain(_clean_text(md["content"]), user_id=touser)
                    js["markdown"] = md
                    kwargs["json"] = js
                    print({"tag":"brain_wrap","type":"markdown","ok":True,"touser":touser})
                    return _orig_post(url, *args, **kwargs)

                tx = js.get("text") or {}
                if isinstance(tx, dict) and isinstance(tx.get("content"), str):
                    tx["content"] = ask_brain(_clean_text(tx["content"]), user_id=touser)
                    js["text"] = tx
                    kwargs["json"] = js
                    print({"tag":"brain_wrap","type":"text","ok":True,"touser":touser})
    except Exception as e:
        print({"tag":"brain_wrap","ok":False,"err":str(e)})
    return _orig_post(url, *args, **kwargs)

BRAIN_ENABLED = os.getenv("BRAIN_ENABLED", "0") in ("1", "true", "True", "yes", "on")
if BRAIN_ENABLED:
    requests.post = _post_with_brain
else:
    print({"tag":"brain_inject","enabled":False})

# ==== /BRAIN AUTO-INJECT ====
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import os, base64, hashlib, struct, xml.etree.ElementTree as ET
import os, requests, time

from dotenv import load_dotenv

load_dotenv("/srv/wecom/shared/.env.wecom")

BRAIN_URL = os.getenv("BRAIN_URL", "http://127.0.0.1:7870/api/ask")

def ask_brain(text, user_id=""):

    t0 = time.time()

    try:

        r = requests.post(BRAIN_URL, json={"question": text, "user_id": user_id}, timeout=8)

        j = r.json()

        ans = j.get("answer") or "这边先安排专员跟进，稍后给您具体方案～"

        print({"tag":"brain_call","ok":True,"ms":int((time.time()-t0)*1000),"ctx":j.get("meta",{})})

        return ans

    except Exception as e:

        print({"tag":"brain_call","ok":False,"err":str(e)})

        return "系统繁忙，已转人工处理～"

from Crypto.Cipher import AES
from datetime import datetime, timezone

app = FastAPI(title="WeCom Webhook (minimal)", version="1.0.0")

TOKEN   = os.getenv("WECOM_TOKEN", "")
AES_KEY = os.getenv("WECOM_AES_KEY", "")   # 43 位
CORP_ID = os.getenv("WECOM_CORP_ID", "")
DRY_RUN = os.getenv("WECOM_DRY_RUN", "0") == "1"

# NDJSON 轻量落库
NDJSON_PATH = os.getenv("WECOM_NDJSON", "/srv/wecom/shared/wecom_messages.ndjson")
def append_ndjson(row: dict):
    try:
        os.makedirs(os.path.dirname(NDJSON_PATH), exist_ok=True)
        if "ts" not in row:
            row["ts"] = datetime.now(timezone.utc).isoformat()
        with open(NDJSON_PATH, "a", encoding="utf-8") as f:
            import json; f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        print("ndjson error:", e)

def _b64key(aes43: str) -> bytes:
    # 企业微信 AESKey 是 43 位 base64，需补 '=' 再 decode 成 32 字节 key
    return base64.b64decode(aes43 + "=")

def _pkcs7_unpad(d: bytes) -> bytes:
    pad = d[-1]
    if pad < 1 or pad > 32: raise ValueError("bad padding")
    return d[:-pad]

def _aes_decrypt_b64(cipher_b64: str) -> bytes:
    key = _b64key(AES_KEY)
    iv  = key[:16]
    cipher = base64.b64decode(cipher_b64)
    plain  = AES.new(key, AES.MODE_CBC, iv=iv).decrypt(cipher)
    return _pkcs7_unpad(plain)

def _wx_verify_sig(token: str, ts: str, nonce: str, data: str) -> str:
    # 企业微信签名：对 token, timestamp, nonce, data 进行字典序排序拼接后 sha1
    s = "".join(sorted([token, ts, nonce, data])).encode()
    return hashlib.sha1(s).hexdigest()

@app.get("/healthz")
def healthz():
    ok = bool(TOKEN and AES_KEY and CORP_ID)
    return JSONResponse({"ok": ok})

@app.get("/wecom/webhook", response_class=PlainTextResponse)
async def wecom_verify(request: Request):
    """
    企业微信 URL 验证：GET ?msg_signature=&timestamp=&nonce=&echostr=
    校验签名 -> 解密 echostr -> 返回明文（严格 1s 内、无多余字符）
    """
    qs = request.query_params
    msg_signature = qs.get("msg_signature", "")
    timestamp     = qs.get("timestamp", "")
    nonce         = qs.get("nonce", "")
    echostr       = qs.get("echostr", "")
    if not (TOKEN and AES_KEY and CORP_ID):
        raise HTTPException(500, detail="env not ready")

    expect = _wx_verify_sig(TOKEN, timestamp, nonce, echostr)
    if expect != msg_signature:
        raise HTTPException(403, detail="verify failed")

    # 解密 echostr：结构 = 16字节rand + 4字节len + msg(明文) + CorpID
    try:
        plain = _aes_decrypt_b64(echostr)
        rand   = plain[:16]
        msglen = struct.unpack(">I", plain[16:20])[0]
        msg    = plain[20:20+msglen]
        corpid = plain[20+msglen:].decode()
        if corpid != CORP_ID:
            raise HTTPException(403, detail="corpid mismatch")
        return msg.decode()
    except Exception:
        raise HTTPException(403, detail="decrypt failed")

@app.post("/wecom/webhook", response_class=PlainTextResponse)
async def wecom_post(request: Request):
    """
    企业微信推送：POST XML(含 Encrypt)
    做签名校验 -> 解密 -> 解析关键字段 -> 轻量 NDJSON 落地 -> 返回 'success'
    """
    qs = request.query_params
    msg_signature = qs.get("msg_signature", "")
    timestamp     = qs.get("timestamp", "")
    nonce         = qs.get("nonce", "")

    body = await request.body()
    try:
        root_in = ET.fromstring(body)
        encrypt = root_in.findtext("Encrypt") or ""
    except Exception:
        # 兼容极端：有时 CDN/WAF 会改写 body
        encrypt = ""

    # 校验签名
    expect = _wx_verify_sig(TOKEN, timestamp, nonce, encrypt)
    if expect != msg_signature:
        raise HTTPException(403, detail="sign failed")

    # 解密
    plain_xml = b""
    try:
        if encrypt:
            plain = _aes_decrypt_b64(encrypt)
            msglen = struct.unpack(">I", plain[16:20])[0]
            plain_xml = plain[20:20+msglen]
        else:
            # 无 Encrypt 时，直接透传（极少数测试场景）
            plain_xml = body
    except Exception:
        # 为了链路稳定，仍然返回 success；但标记日志
        append_ndjson({"type":"error","reason":"decrypt fail","remote_ip":getattr(getattr(request, 'client', None), 'host', '')})
        return "success"

    # 解析 & 落日志（只保留这一处，避免重复写 NDJSON）
    try:
        r = ET.fromstring(plain_xml)
        log_obj = {
            "from_user": r.findtext("FromUserName") or "",
            "to_user":   r.findtext("ToUserName") or "",
            "msg_type":  r.findtext("MsgType") or "",
            "event":     r.findtext("Event") or "",
            "content":   r.findtext("Content") or "",
            "create_at": int(r.findtext("CreateTime") or "0"),
            "remote_ip": getattr(getattr(request, "client", None), "host", ""),
        }
        append_ndjson(log_obj)
    except Exception as e:
        append_ndjson({"type":"error","reason":f"parse fail: {e}"})

    # DRY_RUN=1 时，直接 ACK；DRY_RUN=0 时你也可以在这里挂主动回复

    return "success"

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import os, requests, xml.etree.ElementTree as ET
import os, requests, time

from dotenv import load_dotenv

load_dotenv("/srv/wecom/shared/.env.wecom")

BRAIN_URL = os.getenv("BRAIN_URL", "http://127.0.0.1:7870/api/ask")

def ask_brain(text, user_id=""):

    t0 = time.time()

    try:

        r = requests.post(BRAIN_URL, json={"question": text, "user_id": user_id}, timeout=8)

        j = r.json()

        ans = j.get("answer") or "这边先安排专员跟进，稍后给您具体方案～"

        print({"tag":"brain_call","ok":True,"ms":int((time.time()-t0)*1000),"ctx":j.get("meta",{})})

        return ans

    except Exception as e:

        print({"tag":"brain_call","ok":False,"err":str(e)})

        return "系统繁忙，已转人工处理～"


# 载入 env（根目录）
load_dotenv(".env.wecom")
load_dotenv(".env.doubao")

WECOM_DRY_RUN = os.getenv("WECOM_DRY_RUN", "0") in ("1","true","True")
WECOM_CORP_ID      = os.getenv("WECOM_CORP_ID","")
WECOM_AGENT_ID     = os.getenv("WECOM_AGENT_ID","")
WECOM_AGENT_SECRET = os.getenv("WECOM_AGENT_SECRET","")
WECOM_TOKEN        = os.getenv("WECOM_TOKEN","")
WECOM_AES_KEY      = os.getenv("WECOM_AES_KEY","")

from services.wecom_webhook_service.wxbizmsgcrypt import WXBizMsgCrypt
from services.shared.doubao import chat

app = FastAPI(title="WeCom Webhook + Doubao", version="1.0.0")

@app.get("/healthz")
def healthz():
    return {"ok": True}

def _crypt():
    if not (WECOM_TOKEN and WECOM_AES_KEY and WECOM_CORP_ID):
        raise HTTPException(500, "WeCom TOKEN/AES/CORP_ID not set; fill .env.wecom before URL verify.")
    return WXBizMsgCrypt(WECOM_TOKEN, WECOM_AES_KEY, WECOM_CORP_ID)

def _get_access_token():
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={WECOM_CORP_ID}&corpsecret={WECOM_AGENT_SECRET}"
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    data = r.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"gettoken failed: {data}")
    return data["access_token"]

def _send_text(to_user: str, content: str):
    token = _get_access_token()
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
    payload = {
        "touser": to_user,
        "msgtype": "text",
        "agentid": int(WECOM_AGENT_ID or "0"),
        "text": {"content": content[:2000]},
        "safe": 0
    }
    r = requests.post(url, json=payload, timeout=8)
    r.raise_for_status()
    return r.json()

@app.get("/wecom/webhook", response_class=PlainTextResponse)
async def verify(msg_signature: str, timestamp: str, nonce: str, echostr: str):
    ret, echo = _crypt().VerifyURL(msg_signature, timestamp, nonce, echostr)
    if ret != 0 or echo is None:
        raise HTTPException(403, "verify failed")
    return echo

@app.post("/wecom/webhook", response_class=PlainTextResponse)
async def message(request: Request):
    sig   = request.query_params.get("msg_signature", "")
    ts    = request.query_params.get("timestamp", "")
    nonce = request.query_params.get("nonce", "")
    cipher_xml = await request.body()

    ret, plain_xml = _crypt().DecryptMsg(cipher_xml, sig, ts, nonce)
    if ret != 0 or plain_xml is None:
        raise HTTPException(403, "decrypt failed")

    # 轻量落盘（只保留一处，避免重复写入）
    try:
        from services.wecom_webhook_service.hook_ndjson import log_plain_xml
        ip = getattr(getattr(request, "client", None), "host", "")
        log_plain_xml(plain_xml, ip)
    except Exception as _e:
        print("hook err:", _e)

    if WECOM_DRY_RUN:
        return "success"

    root = ET.fromstring(plain_xml)
    msg_type  = root.findtext("MsgType") or ""
    from_user = root.findtext("FromUserName") or ""

    reply = None
    if msg_type == "text":
        content = root.findtext("Content") or ""
        system = {"role":"system","content":"你是美业门店AI助手。给1句中文私信回复，友好克制，禁止夸大疗效。必要时提醒过敏测试和防晒。不超过60字。"}
        user   = {"role":"user","content":f"客户说：{content}"}
        try:
            reply = chat([system, user])[:200]
        except Exception:
            reply = "好的～我这边为您核对后尽快回复。"

    if reply:
        try:
            _send_text(from_user, reply)
        except Exception:
            pass  # 不影响我们返回 success

    return "success"
