"""Start DRCV: python run.py  → http://127.0.0.1:8000"""
import os
import threading
import webbrowser

import uvicorn

if __name__ == "__main__":
    host = os.getenv("DRCV_HOST", "127.0.0.1")
    port = int(os.getenv("DRCV_PORT", "8000"))
    url = f"http://{'localhost' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}"
    print(f"\n  Digital Record Context Verification\n  Opening {url}  (first start prepares the synthetic demo data, ~20s)\n")
    if os.getenv("DRCV_NO_BROWSER") != "1":
        threading.Timer(4.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
