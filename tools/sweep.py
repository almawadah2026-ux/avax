"""
مسح سيناريوهات — يختبر سلوك الديسك عبر أنظمة سوقية مختلفة.

الغرض: التأكد أن الفريق **يغيّر رأيه** بتغيّر السوق، وأن آلية المنع تعمل.
نظام يوافق دائماً أو يمتنع دائماً نظام مكسور.

الاستخدام:
    python tools/sweep.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from avax_desk.cli import DeskRunner           # noqa: E402
from avax_desk.config import DeskConfig        # noqa: E402


SCENARIOS = ["bull", "bear", "chop", "crisis", "recovery"]
SEEDS = [1, 2, 3]


def main() -> int:
    rows = []
    for scenario in SCENARIOS:
        for seed in SEEDS:
            cfg = DeskConfig(scenario=scenario, seed=seed, verbose=False)
            runner = DeskRunner(cfg, write_journal=False)
            res = runner.run()
            d = res["decision"]
            rows.append((
                scenario, seed, d["action"], d["confidence"],
                res["proposal"]["direction"], res["proposal"]["score"],
                (res.get("risk") or {}).get("position_size_usd", 0.0),
                (res.get("risk") or {}).get("veto", True),
                (res.get("compliance") or {}).get("compliant", False),
                ((res.get("opinions") or {}).get("09") or {}).get("metrics", {}).get("validated", False),
            ))

    print()
    print("═" * 112)
    print("  مسح السيناريوهات — هل يتغيّر القرار؟")
    print("═" * 112)
    print(f"  {'السيناريو':<10} {'بذرة':<5} {'القرار':<9} {'ثقة':>6} {'اتجاه':<9} "
          f"{'درجة':>8} {'حجم$':>12} {'نقض':<5} {'التزام':<6} {'تحقق':<6}")
    print("─" * 112)
    for r in rows:
        print(f"  {r[0]:<10} {r[1]:<5} {r[2]:<9} {r[3]:>6.1f} {r[4]:<9} "
              f"{r[5]:>8.3f} {r[6]:>12,.0f} {'نعم' if r[7] else 'لا':<5} "
              f"{'سليم' if r[8] else 'حجب':<6} {'نعم' if r[9] else 'لا':<6}")
    print("═" * 112)

    actions = {}
    for r in rows:
        actions[r[2]] = actions.get(r[2], 0) + 1
    print(f"  توزيع القرارات: {actions}")
    lonshort = sum(v for k, v in actions.items() if k in ("LONG", "SHORT"))
    print(f"  قرارات اتجاهية: {lonshort}/{len(rows)}  |  امتناع: {len(rows)-lonshort}/{len(rows)}")
    if lonshort == 0:
        print("  ⚠️ لم يصدر أي قرار اتجاهي — قد تكون الحدود متحفظة أكثر من اللازم")
    if lonshort == len(rows):
        print("  ⚠️ كل الدورات أنتجت قراراً اتجاهياً — قد تكون الحدود متساهلة أكثر من اللازم")
    print("═" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
