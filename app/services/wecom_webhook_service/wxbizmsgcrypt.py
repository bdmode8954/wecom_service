# wxbizmsgcrypt.py — 企业微信加解密（标准库版，无 lxml 依赖）
import base64, hashlib, struct
from Crypto.Cipher import AES
import xml.etree.ElementTree as ET

class ValidateException(Exception): ...
class FormatException(Exception): ...

def _pkcs7_unpad(b: bytes) -> bytes:
    if not b:
        raise FormatException("empty")
    pad = b[-1]
    if pad < 1 or pad > 32:
        raise FormatException("bad pad")
    return b[:-pad]

def _sha1(token: str, ts: str, nonce: str, encrypt: str) -> str:
    arr = [token, ts, nonce, encrypt]
    arr.sort()
    return hashlib.sha1("".join(arr).encode("utf-8")).hexdigest()

class WXBizMsgCrypt:
    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        if not token or not encoding_aes_key or not corp_id:
            raise ValidateException("missing envs")
        if len(encoding_aes_key) != 43:
            raise ValidateException("EncodingAESKey must be 43 chars")
        self.key = base64.b64decode(encoding_aes_key + "=")
        self.iv = self.key[:16]
        self.token = token
        self.corp_id = corp_id

    def _decrypt(self, encrypt_b64: str) -> bytes:
        ct = base64.b64decode(encrypt_b64)
        cipher = AES.new(self.key, AES.MODE_CBC, iv=self.iv)
        plain = cipher.decrypt(ct)
        return _pkcs7_unpad(plain)

    # GET 验证 URL
    def VerifyURL(self, msg_signature: str, timestamp: str, nonce: str, echostr: str):
        sig = _sha1(self.token, timestamp, nonce, echostr)
        if sig != msg_signature:
            return -40001, None  # signature invalid
        try:
            plain = self._decrypt(echostr)
            # 解析明文结构: 16字节随机 + 4字节长度 + 内容 + CorpID
            msg_len = struct.unpack(">I", plain[16:20])[0]
            content = plain[20:20 + msg_len]
            corp    = plain[20 + msg_len:].decode("utf-8")
            if corp != self.corp_id:
                return -40005, None
            return 0, content.decode("utf-8")
        except Exception:
            return -40007, None  # decrypt error

    # POST 解密 XML
    def DecryptMsg(self, cipher_xml: bytes, msg_signature: str, timestamp: str, nonce: str):
        # 用标准库解析加密 XML，取 <Encrypt>
        root = ET.fromstring(cipher_xml)
        enc_node = root.find("Encrypt")
        if enc_node is None or not enc_node.text:
            return -40002, None
        encrypt = enc_node.text.strip()

        sig = _sha1(self.token, timestamp, nonce, encrypt)
        if sig != msg_signature:
            return -40001, None

        try:
            content = self._decrypt(encrypt)
            # 16 随机 + 4 长度 + 明文XML + CorpID
            msg_len = struct.unpack(">I", content[16:20])[0]
            xml_bytes = content[20:20+msg_len]
            corp = content[20+msg_len:].decode("utf-8")
            if corp != self.corp_id:
                return -40005, None
            return 0, xml_bytes.decode("utf-8")
        except Exception:
            return -40007, None
