"""تشخيص: لماذا يرفض Supabase المفتاح العام؟ وهل يمكن للواجهة القراءة مباشرة؟"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

ENV: dict[str, str] = {}
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        ENV[k.strip()] = v.strip()

URL = ENV["SUPABASE_URL"].rstrip("/")
PUB = ENV["SUPABASE_PUBLISHABLE_KEY"]
SVC = ENV["SUPABASE_SERVICE_ROLE_KEY"]


def probe(label: str, url: str, headers: dict[str, str]) -> None:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(body)
                n = len(data) if isinstance(data, list) else "كائن"
            except Exception:  # noqa: BLE001
                n = body[:80]
            print(f"✅ {label}\n     HTTP {r.status} | البيانات: {n}")
    except urllib.error.HTTPError as e:
        print(f"❌ {label}\n     HTTP {e.code} — {e.read().decode('utf-8','replace')[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ {label}\n     {type(e).__name__}: {e}")


print("=" * 78)
print("  تشخيص وصول المفتاح العام")
print("=" * 78)

# 1) publishable في ترويسة apikey فقط
probe("publishable كـ apikey على v_run_summary",
      f"{URL}/rest/v1/v_run_summary?select=*&limit=2",
      {"apikey": PUB, "Accept": "application/json"})

# 2) publishable في Authorization أيضاً
probe("publishable كـ apikey + Bearer",
      f"{URL}/rest/v1/v_run_summary?select=*&limit=2",
      {"apikey": PUB, "Authorization": f"Bearer {PUB}", "Accept": "application/json"})

# 3) على جدول مباشر
probe("publishable على desk_runs",
      f"{URL}/rest/v1/desk_runs?select=id&limit=2",
      {"apikey": PUB, "Accept": "application/json"})

# 4) service_role للمقارنة
probe("service_role على v_run_summary (مرجع)",
      f"{URL}/rest/v1/v_run_summary?select=*&limit=2",
      {"apikey": SVC, "Authorization": f"Bearer {SVC}", "Accept": "application/json"})

# 5) هل توجد مفاتيح anon قديمة؟
probe("service_role على قائمة مفاتيح المشروع",
      "https://api.supabase.com/v1/projects/misoilandgmiyigyytxv/api-keys",
      {"Authorization": f"Bearer {ENV['SUPABASE_ACCESS_TOKEN']}",
       "Accept": "application/json",
       "User-Agent": "avax-desk/1.0"})

print("=" * 78)
