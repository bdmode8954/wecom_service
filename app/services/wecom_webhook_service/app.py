import os
import base64
import hashlib
import struct
import subprocess
import xml.etree.ElementTree as ET

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from Crypto.Cipher import AES


app = FastAPI(title="WeCom Webhook Relay", version="1.0.0")

TOKEN = os.getenv("WECOM_TOKEN", "")
AES_KEY = os.getenv("WECOM_AES_KEY", "")  # 43-char EncodingAESKey
CORP_ID = os.getenv("WECOM_CORP_ID", "")

RELAY_TO_LOCAL = os.getenv("RELAY_TO_LOCAL", "0") in ("1", "true", "True", "yes", "on")
RELAY_SCRIPT = os.getenv("RELAY_SCRIPT", "/home/ops/wecom_relay/forward.sh")


def relay_to_local(text: str):
    if not RELAY_TO_LOCAL:
        return
    text = (text or "").strip()
    if not text:
        return
    try:
        subprocess.Popen(
            [RELAY_SCRIPT, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print("relay_to_local error:", e)


def _wx_verify_sig(token: str, ts: str, nonce: str, data: str) -> str:
    s = "".join(sorted([token, ts, nonce, data])).encode("utf-8")
    return hashlib.sha1(s).hexdigest()


def _b64key(aes43: str) -> bytes:
    return base64.b64decode(aes43 + "=")


def _pkcs7_unpad(d: bytes) -> bytes:
    if not d:
        raise ValueError("empty plaintext")
    pad = d[-1]
    if pad < 1 or pad > 32:
        raise ValueError("bad padding")
    return d[:-pad]


def _aes_decrypt_packet(cipher_b64: str) -> tuple[bytes, str]:
    key = _b64key(AES_KEY)
    iv = key[:16]
    cipher = base64.b64decode(cipher_b64)
    plain = AES.new(key, AES.MODE_CBC, iv=iv).decrypt(cipher)
    plain = _pkcs7_unpad(plain)

    msg_len = struct.unpack(">I", plain[16:20])[0]
    xml_bytes = plain[20 : 20 + msg_len]
    receive_id = plain[20 + msg_len :].decode("utf-8", errors="ignore")
    return xml_bytes, receive_id


@app.get("/wecom/webhook", response_class=PlainTextResponse)
async def wecom_verify(request: Request):
    if not (TOKEN and AES_KEY and CORP_ID):
        raise HTTPException(status_code=500, detail="env not ready")

    qs = request.query_params
    msg_signature = qs.get("msg_signature", "")
    timestamp = qs.get("timestamp", "")
    nonce = qs.get("nonce", "")
    echostr = qs.get("echostr", "")

    expect = _wx_verify_sig(TOKEN, timestamp, nonce, echostr)
    if expect != msg_signature:
        raise HTTPException(status_code=403, detail="verify failed")

    try:
        msg, receive_id = _aes_decrypt_packet(echostr)
        if receive_id != CORP_ID:
            raise HTTPException(status_code=403, detail="corpid mismatch")
        return PlainTextResponse(msg.decode("utf-8", errors="ignore"))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="decrypt failed")


@app.post("/wecom/webhook", response_class=PlainTextResponse)
async def wecom_post(request: Request):
    if not (TOKEN and AES_KEY and CORP_ID):
        raise HTTPException(status_code=500, detail="env not ready")

    qs = request.query_params
    msg_signature = qs.get("msg_signature", "")
    timestamp = qs.get("timestamp", "")
    nonce = qs.get("nonce", "")

    body = await request.body()
    try:
        root_in = ET.fromstring(body)
        encrypt = root_in.findtext("Encrypt") or ""
    except Exception:
        encrypt = ""

    if encrypt:
        expect = _wx_verify_sig(TOKEN, timestamp, nonce, encrypt)
        if expect != msg_signature:
            raise HTTPException(status_code=403, detail="sign failed")
        try:
            plain_xml, receive_id = _aes_decrypt_packet(encrypt)
            if receive_id != CORP_ID:
                raise HTTPException(status_code=403, detail="corpid mismatch")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="decrypt failed")
    else:
        plain_xml = body

    try:
        r = ET.fromstring(plain_xml)
        content = r.findtext("Content") or ""
        relay_to_local(content)
    except Exception:
        pass

    return PlainTextResponse("success")