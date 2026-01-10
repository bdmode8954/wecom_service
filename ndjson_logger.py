import os, json
from datetime import datetime, timezone
NDJSON_PATH = os.getenv("WECOM_NDJSON", "/srv/wecom/shared/wecom_messages.ndjson")

def append_ndjson(obj: dict):
    """把 dict 作为一行 NDJSON 追加到文件里（UTF-8、尽量不抛错）"""
    try:
        row = dict(obj)
        if "ts" not in row:
            row["ts"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(NDJSON_PATH), exist_ok=True)
        with open(NDJSON_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        # 不影响主流程
        pass
