"""
فحص صلاحية المفاتيح قبل أي بناء.
لا يطبع أي سرّ — فقط نتيجة الاتصال.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")


def load_env(path: Path = ROOT / ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


ENV = load_env()
results: list[tuple[str, str, str]] = []


def probe(name: str, url: str, headers: dict[str, str], expect=None) -> None:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
        ok = True
        detail = f"HTTP {status}"
        if expect:
            try:
                data = json.loads(body)
                detail += " | " + expect(data)
            except Exception:  # noqa: BLE001
                detail += " | (استجابة غير JSON)"
    except urllib.error.HTTPError as e:
        ok = False
        snippet = e.read().decode("utf-8", "replace")[:180]
        detail = f"HTTP {e.code} — {snippet}"
    except Exception as e:  # noqa: BLE001
        ok = False
        detail = f"{type(e).__name__}: {e}"
    results.append(("✅" if ok else "❌", name, detail))


# ── 1) CoinMarketCap ────────────────────────────────────────────────────
for label, key_name in (("CMC (32)", "CMC_API_KEY"), ("CMC (64)", "CMC_API_KEY_ALT")):
    key = ENV.get(key_name, "")
    if not key:
        continue
    probe(
        f"{label} quotes/latest AVAX",
        "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol=AVAX&convert=USD",
        {"X-CMC_PRO_API_KEY": key, "Accept": "application/json"},
        lambda d: (f"AVAX = ${d['data']['AVAX']['quote']['USD']['price']:.4f}"
                   if d.get("data") else "لا بيانات"),
    )

# ── 2) GitHub ───────────────────────────────────────────────────────────
gh = ENV.get("GITHUB_TOKEN", "")
if gh:
    probe("GitHub /user", "https://api.github.com/user",
          {"Authorization": f"Bearer {gh}", "Accept": "application/vnd.github+json",
           "User-Agent": "avax-desk"},
          lambda d: f"المستخدم: {d.get('login')}")
    probe("GitHub repo access", "https://api.github.com/repos/almawadah2026-ux/avax",
          {"Authorization": f"Bearer {gh}", "Accept": "application/vnd.github+json",
           "User-Agent": "avax-desk"},
          lambda d: (f"الوصول: {d.get('full_name')} | private={d.get('private')} "
                     f"| default={d.get('default_branch')}"))

# ── 3) Supabase ─────────────────────────────────────────────────────────
sb_url = ENV.get("SUPABASE_URL", "").rstrip("/")
if sb_url:
    pub = ENV.get("SUPABASE_PUBLISHABLE_KEY", "")
    svc = ENV.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if pub:
        probe("Supabase REST (publishable)", f"{sb_url}/rest/v1/",
              {"apikey": pub, "Accept": "application/json"},
              lambda d: "استجابة صالحة")
    if svc:
        probe("Supabase REST (service_role) — فحص الجداول",
              f"{sb_url}/rest/v1/?select=*",
              {"apikey": svc, "Authorization": f"Bearer {svc}", "Accept": "application/json"},
              lambda d: f"عدد الجداول المرئية: {len(d)}")
        probe("Supabase Auth admin (service_role)",
              f"{sb_url}/auth/v1/admin/users",
              {"apikey": svc, "Authorization": f"Bearer {svc}", "Accept": "application/json"},
              lambda d: f"عدد المستخدمين: {len(d.get('users', []))}")

# ── التقرير ─────────────────────────────────────────────────────────────
print("=" * 78)
print("  فحص المفاتيح والاتصالات")
print("=" * 78)
for icon, name, detail in results:
    print(f"\n{icon} {name}")
    print(f"     {detail}")
print("\n" + "=" * 78)
ok = sum(1 for r in results if r[0] == "✅")
print(f"  نجح: {ok}/{len(results)}")
print("=" * 78)
