"""Run with: python -m skycast  (or: python -m skycast report Kolkata)"""
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if len(sys.argv) > 2 and sys.argv[1] == "report":
    from .graph import run
    s = run(" ".join(sys.argv[2:]))
    print(json.dumps({k: s.get(k) for k in ("city", "current", "analysis", "advice", "notes")}, indent=2, ensure_ascii=False))
else:
    import uvicorn
    uvicorn.run("skycast.server:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
