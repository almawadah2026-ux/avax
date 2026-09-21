"""تحقق من إصلاحات الجولة الرابعة: كيلي، تركيب التخفيضات، المرساة."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from avax_desk.cli import DeskRunner
from avax_desk.config import DeskConfig
from avax_desk.risk.engine import RiskEngine

print("=== تحليل إلزام كيلي (إفصاح صادق) ===")
a = RiskEngine.kelly_binding_analysis()
print(f"  سقف المركز: {a['max_position_notional']:,.0f} دولار | "
      f"حد الدخول: {a['min_confidence']}")
print(f"  يقيّد داخل نطاق الثقات المؤهلة: {a['kelly_binds_in_eligible_range']}")
print(f"  يقيّد فقط تحت حد الدخول     : {a['kelly_binds_only_below_min_confidence']}")
for r in a["rows"]:
    mark = "يقيّد" if r["binds"] else "لا يقيّد"
    elig = "مؤهل" if r["eligible_for_entry"] else "غير مؤهل"
    print(f"    ثقة {r['confidence']:>3} [{elig}]: كيلي = {r['kelly_notional']:>10,.0f}"
          f"  ->  {mark}")
print(f"  الملاحظة: {a['note']}")

print("\n=== تركيب التخفيضات ===")
for sc, pnl in (("crisis", 0.0), ("crisis", -1.6), ("bull", 0.0)):
    r = DeskRunner(DeskConfig(scenario=sc, seed=3, daily_pnl_pct=pnl, verbose=False),
                   write_journal=False).run()
    rk = r["risk"]
    lc = rk["limits_checked"]
    print(f"  [{sc} pnl={pnl}] مستوى={rk['risk_level']} "
          f"مضاعف={lc['level_multiplier']} جودة={lc['quality_haircut']} "
          f"مكوّن={lc['composed_multiplier']} كيلي_ملزم={lc['kelly_binding']}")
    for n in rk["notes"]:
        if "متراكب" in n or "كيلي ليس" in n:
            print(f"      {n}")

print("\n=== مصفوفة كيلي المرجعية (سقف 0.30 موحّد) ===")
for row in RiskEngine.kelly_table()[:4]:
    print(f"  ثقة {row['confidence']}: كامل={row['kelly_full_pct']}% "
          f"نصف_مقيّد={row['kelly_half_capped_pct']}%")
