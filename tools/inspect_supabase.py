"""فحص مخطط Supabase القائم — للقراءة فقط، لا يعدّل شيئاً."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


ENV = load_env()
URL = ENV["SUPABASE_URL"].rstrip("/")
SVC = ENV["SUPABASE_SERVICE_ROLE_KEY"]
H = {"apikey": SVC, "Authorization": "Bearer " + SVC, "Accept": "application/json"}


def get(path: str):
    req = urllib.request.Request(URL + path, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__error": e.code, "__body": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:  # noqa: BLE001
        return {"__error": type(e).__name__, "__body": str(e)[:300]}


print("=" * 78)
print("  مخطط Supabase القائم (قراءة فقط)")
print("=" * 78)

tables = get("/rest/v1/")
if isinstance(tables, list):
    print(f"\nعدد الجداول المرئية: {len(tables)}\n")
    for t in sorted(tables):
        row = get(f"/rest/v1/{t}?select=*&limit=1")
        if isinstance(row, list):
            cols = list(row[0].keys()) if row else []
            cnt = get(f"/rest/v1/{t}?select=*")
            total = len(cnt) if isinstance(cnt, list) else "?"
            print(f"  ▸ {t}  (صفوف: {total})")
            print(f"      أعمدة: {', '.join(cols) if cols else '— (فارغ)'}")
        else:
            print(f"  ▸ {t}  ⚠️ {row}")
else:
    print("تعذّر جلب قائمة الجداول:", tables)

print("\n" + "=" * 78)
