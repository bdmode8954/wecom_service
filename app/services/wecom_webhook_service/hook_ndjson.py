import os, json, xml.etree.ElementTree as ET
from datetime import datetime, timezone

NDJSON_PATH = os.getenv("WECOM_NDJSON", "/srv/wecom/shared/wecom_messages.ndjson")
os.makedirs(os.path.dirname(NDJSON_PATH), exist_ok=True)

def _append(obj: dict):
    row = dict(obj)
    if "ts" not in row:
        row["ts"] = datetime.now(timezone.utc).isoformat()
    with open(NDJSON_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def log_plain_xml(plain_xml: bytes | str, remote_ip: str = ""):
    if isinstance(plain_xml, bytes):
        plain_xml = plain_xml.decode("utf-8", errors="ignore")
    root = ET.fromstring(plain_xml)
    data = {
        "from_user": root.findtext("FromUserName") or "",
        "to_user":   root.findtext("ToUserName") or "",
        "msg_type":  root.findtext("MsgType") or "",
        "event":     root.findtext("Event") or "",
        "content":   root.findtext("Content") or "",
        "create_at": int(root.findtext("CreateTime") or "0"),
        "remote_ip": remote_ip or "",
    }
    _append(data)
