"""
تطبيق مخطط قاعدة البيانات على Supabase عبر Management API.

الواجهة المستخدمة: `POST /v1/projects/{ref}/database/query` برمز الإدارة (`sbp_…`).
هذه هي الطريقة الرسمية لتنفيذ DDL بلا CLI.

الاستخدام:
    python tools/apply_schema.py            # يطبّق المخطط
    python tools/apply_schema.py --check    # يفحص الحالة فقط
"""

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
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


ENV = load_env()
PROJECT_REF = ENV["SUPABASE_URL"].rstrip("/").split("//")[-1].split(".")[0]
ACCESS_TOKEN = ENV["SUPABASE_ACCESS_TOKEN"]
MGMT = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"


def run_sql(sql: str, timeout: float = 90.0):
    body = json.dumps({"query": sql}).encode("utf-8")
    req = urllib.request.Request(
        MGMT, data=body, method="POST",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return True, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check() -> None:
    ok, res = run_sql("""
        select table_name from information_schema.tables
        where table_schema='public' and table_type='BASE TABLE'
        order by table_name;
    """)
    if not ok:
        print("❌ تعذّر الفحص:", res)
        return
    names = [r["table_name"] for r in (res or [])]
    print(f"الجداول في public: {len(names)}")
    for n in names:
        print("  ▸", n)


def main() -> int:
    if "--check" in sys.argv:
        check()
        return 0

    sql = (ROOT / "src" / "avax_desk" / "backend" / "schema.sql").read_text(encoding="utf-8")
    print(f"المشروع: {PROJECT_REF}")
    print(f"حجم المخطط: {len(sql.splitlines())} سطراً")
    print("جارٍ التطبيق…")
    ok, res = run_sql(sql)
    if not ok:
        print("❌ فشل التطبيق:", res)
        return 1
    print("✅ طُبِّق المخطط")
    check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
