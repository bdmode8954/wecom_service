import os, json
from datetime import datetime, timezone

NDJSON_PATH = os.getenv("WECOM_NDJSON", "/srv/wecom/shared/wecom_messages.ndjson")
os.makedirs(os.path.dirname(NDJSON_PATH), exist_ok=True)

def append_ndjson(obj: dict):
    row = dict(obj)
    if "ts" not in row:
        row["ts"] = datetime.now(timezone.utc).isoformat()
    with open(NDJSON_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
