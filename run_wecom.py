#!/usr/bin/env python3
import os, sys, importlib, importlib.util, uvicorn, pathlib
os.environ.setdefault("WECOM_APP", "app.services.wecom_webhook_service.app:app")


# 运行时根目录：服务器优先用 /srv/wecom/current；本地用项目目录
SERVER_BASE = pathlib.Path("/srv/wecom/current")
LOCAL_BASE = pathlib.Path(__file__).resolve().parent

BASE = SERVER_BASE if SERVER_BASE.exists() else LOCAL_BASE

# 确保搜索路径包含 BASE 和 BASE/app（兼容两种结构）
for p in [str(BASE), str(BASE / "app")]:
    if p not in sys.path:
        sys.path.insert(0, p)


# 允许用环境变量显式指定模块:attr，例如  WECOM_APP_MODULE=app.services.wecom_webhook_service.app:app
ENV_OVERRIDE = os.getenv("WECOM_APP_MODULE")

# 1) 优先按“文件路径”兜底导入
CAND_FILES = [
    BASE / "app" / "services" / "wecom_webhook_service" / "app.py",
    BASE / "services" / "wecom_webhook_service" / "app.py",  # 备选
]

# 2) 其次按“模块名:属性”导入
CAND_MODULES = [
    "app.services.wecom_webhook_service.app:app",
    "services.wecom_webhook_service.app:app",
    "wecom_webhook_service.app:app",
    "app:app",
    "main:app",
]

def load_by_file(fp: pathlib.Path):
    if not fp.exists():
        return None
    spec = importlib.util.spec_from_file_location(fp.stem, fp)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "app", None)

def load_by_module(s: str):
    mod_name, attr = (s.split(":", 1) + ["app"])[:2]
    m = importlib.import_module(mod_name)
    return getattr(m, attr)

app = None
picked = None

# A) 环境变量优先
if ENV_OVERRIDE and app is None:
    try:
        app = load_by_module(ENV_OVERRIDE)
        picked = f"ENV:{ENV_OVERRIDE}"
    except Exception as e:
        print("ENV override import failed:", e)

# B) 文件路径兜底
if app is None:
    for fp in CAND_FILES:
        try:
            tmp = load_by_file(fp)
            if tmp is not None:
                app = tmp
                picked = f"FILE:{fp}"
                break
        except Exception as e:
            print("file import failed:", fp, e)

# C) 模块名候选
if app is None:
    for s in CAND_MODULES:
        try:
            app = load_by_module(s)
            picked = f"MOD:{s}"
            break
        except Exception:
            continue

assert app is not None, f"未找到 FastAPI app；请检查路径 / 模块。尝试过文件: {CAND_FILES}；模块: {[ENV_OVERRIDE] + CAND_MODULES}"

print(f"[wecom] 使用入口: {picked}")
uvicorn.run(app, host="127.0.0.1", port=8012, timeout_keep_alive=5, log_level="info")
