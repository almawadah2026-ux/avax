"""
أداة فحص الوكيل 10 (محامي الشيطان) — التحقق من ادعاءات الإجماع.

تُشغَّل على آراء الوكلاء 01–08 كما وردت في دورة manual-desk-run، وتُنتج:
  1. مخرج `law.flag_groupthink` الحقيقي على هذه الدورة.
  2. منطق إجماع الوكيل 10 كما هو في `desks/validation.py::RedTeamAgent`.
  3. الاتجاه والثقة الميكانيكيان الناتجان (direction_from_score / confidence_from).
  4. مقارنة `best_tier` المُعلن من كل وكيل مع الطبقة القابلة للتحقق من أنواع أدلته.
  5. خصم المنشأ في `BaseAgent.ev` لبيانات غير حيّة.

التشغيل:  python tools/redteam_10_consensus_check.py   (من جذر المستودع)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from avax_desk.contracts import Evidence  # noqa: E402
from avax_desk.desks.base import confidence_from, direction_from_score  # noqa: E402
from avax_desk.law import LawEngine  # noqa: E402

AS_OF = "2026-09-20T20:00:00Z"

# (agent_id, direction, abstain, confidence, best_tier_مُعلن, [أنواع كل أدلته كما وردت])
ROWS = [
    ("01", "neutral", True, 52, 2, ["derived"] * 7 + ["market", "market", "inference", "derived"]),
    ("02", "neutral", True, 32, 1, ["derived", "derived", "technical", "derived", "market",
                                    "market", "derived", "onchain", "sentiment", "inference"]),
    ("03", "neutral", True, 58, 2, ["derived"] * 7 + ["market", "inference", "inference", "inference"]),
    ("04", "neutral", True, 30, 1, ["derived", "inference", "inference", "inference", "onchain",
                                    "onchain", "derived", "market", "sentiment", "derived",
                                    "onchain", "derived", "sentiment", "inference", "inference"]),
    ("05", "neutral", True, 35, 3, ["inference", "derived", "inference", "derived", "derived",
                                    "derived", "inference", "derived", "inference", "inference",
                                    "inference"]),
    ("06", "neutral", False, 42, 1, ["market", "derived", "derived", "derived", "inference",
                                     "derived", "derived", "inference", "onchain", "inference",
                                     "inference"]),
    ("07", "neutral", True, 35, 1, ["inference", "inference", "sentiment", "derived", "derived",
                                    "inference", "onchain", "market", "derived"]),
    ("08", "neutral", True, 24, 1, ["inference", "derived", "market", "derived", "derived",
                                    "derived", "derived", "derived", "inference", "sentiment",
                                    "onchain"]),
]

#: حارس المنشأ في BaseAgent.ev: عندما لا يكون source == "live" تُعاد
#: onchain/market إلى derived (الطبقة 3) وتُخفَّض القوة عن high.
GUARD = {"onchain": "derived", "market": "derived"}


def build(agent_id: str, direction: str, abstain: bool, conf: float, kind: str):
    from avax_desk.contracts import AgentOpinion

    ev = Evidence(
        claim=f"[{agent_id}] ادّعاء تمثيلي بنوع {kind} — اللقطة manual-desk-run",
        source="manual-desk-run",
        timestamp=AS_OF,
        kind=kind,
        strength="medium",
    )
    return AgentOpinion(
        agent_id=agent_id,
        agent_name=f"وكيل {agent_id}",
        thesis="رأي الدورة كما ورد",
        evidence=[ev],
        confidence=conf,
        horizon="—",
        invalidation="—",
        dissent="—",
        direction=direction,
        abstain=abstain,
        abstain_reason="نقص بيانات" if abstain else None,
    )


def main() -> int:
    ops = [build(r[0], r[1], r[2], r[3], r[5][0]) for r in ROWS]
    law = LawEngine()

    print("=" * 74)
    print("1) law.flag_groupthink على آراء الدورة (المادة 4.4)")
    print("   ", law.flag_groupthink(ops))

    print("\n2) منطق إجماع الوكيل 10 — desks/validation.py سطور 425-435، 470-471")
    knowledge = [o for o in ops if not o.abstain]
    print(f"    آراء معرفية غير ممتنعة = {[o.agent_id for o in knowledge]}")
    bulls = [o for o in knowledge if o.direction == "bullish"]
    bears = [o for o in knowledge if o.direction == "bearish"]
    consensus_dir = "bullish" if len(bulls) >= len(bears) else "bearish"
    print(f"    bulls={len(bulls)} bears={len(bears)}  ⇒ consensus_dir={consensus_dir!r}"
          "   ← تعادل 0-0 يُحسم إلى bullish")

    score = (-1.0 if consensus_dir == "bullish" else 1.0) * 0.45
    direction = direction_from_score(score, 0.01)
    print(f"    score={score}  dead_zone=0.01  ⇒ direction={direction!r}")
    for c in (1.0, 0.5, 0.3):
        print(f"    confidence_from(score, {direction!r}, completeness={c}) = "
              f"{confidence_from(score, direction, c)}")

    print("\n3) الاتجاهات المُعلنة إجمالاً")
    from collections import Counter
    print("   ", dict(Counter(o.direction for o in ops)),
          f"| ممتنعون = {sum(1 for o in ops if o.abstain)}/{len(ops)}")

    print("\n4) طبقة الدليل: المُعلن مقابل القابل للاحتساب مقابل ما بعد حارس المنشأ")
    print(f"    {'وكيل':<5}{'مُعلن':<7}{'من الأنواع':<12}{'بعد الحارس':<12}{'حكم'}")
    inflated = 0
    for aid, _d, _a, _c, declared, kinds in ROWS:
        from_kinds = min(Evidence(claim="x", source="manual-desk-run",
                                  timestamp=AS_OF, kind=k).tier for k in kinds)
        after_guard = min(Evidence(claim="x", source="manual-desk-run", timestamp=AS_OF,
                                   kind=GUARD.get(k, k)).tier for k in kinds)
        ok = declared == after_guard
        inflated += 0 if ok else 1
        verdict = "مطابق" if ok else f"مُتضخّم ({declared}→{after_guard})"
        print(f"    {aid:<5}{declared:<7}{from_kinds:<12}{after_guard:<12}{verdict}")
    print(f"    ⇒ {inflated}/8 وكيل يُعلن طبقة أفضل من الطبقة القابلة للاحتساب بعد الحارس")

    print("\n5) حارس المنشأ في BaseAgent.ev — source != 'live' ⇒ onchain/market → derived")
    print("    مصادر اللقطة المعرّفة في الكود: 'live' فقط (data/live.py:72,94)؛ "
          "الافتراضي 'synthetic' (data/models.py:81)")
    print("    'manual-desk-run' != 'live' ⇒ الحارس ينطبق ⇒ لا دليل طبقة 1 أو 2 في الدورة")
    print("    تناقض قابل للفحص: أدلة الدورة تحمل kind=onchain/market بلا بادئة "
          "'[محاكاة — ليست بيانات شبكة حقيقية]'")
    print("    ⇒ إمّا أن اللقطة كانت 'live' (فتسقط حجة 'أمثلة منهجية')، أو أن الحارس لم يُنفَّذ")
    print("    ⇒ منشأ ادعاءات الطبقة 1-2 غير قابل للحسم من الحزمة (المادة 2.5 و3.3)")

    print("\n6) أثر انعدام الآراء الاتجاهية على المنسّق")
    print("    orchestrator.propose: active = [] ⇒ agreement=0, base_conf=0, "
          "confidence=0.0 (سطر 97-98)")

    audit_math()
    return 0


def audit_math() -> None:
    """تدقيق حسابي لأرقام الوكلاء — كل سطر قابل لإعادة الإنتاج من اللقطة وحدها."""
    import math

    P, RV, SPR, ADV, OI, TVL, DEX, FR, NET = 115.5, 0.556, 1.7, 535e6, 430e6, 1003.9e6, 140e6, 0.00023, -22e6
    sd = RV / math.sqrt(365)
    print("\n7) تدقيق حسابي (كل القيم من لقطة manual-desk-run)")

    def chk(tag: str, calc: float, stated: float, tol: float = 0.02) -> bool:
        ok = abs(calc - stated) <= tol * max(1.0, abs(stated))
        print(f"    {'✔' if ok else '✘'} {tag}: محتسب={calc:.6g} | مُعلن={stated:.6g}")
        return ok

    chk("01 سبريد بالدولار (1.7bps×115.5)", P * SPR / 1e4, 0.0196)
    chk("01 bps لكل √ثانية (σ_يومي_bps/√86400)", sd * 1e4 / math.sqrt(86400), 0.990)
    chk("01 زمن تعادل السبريد (1.7/0.990)²", (SPR / (sd * 1e4 / math.sqrt(86400))) ** 2, 2.95)
    chk("01 حصة DEX من الحجم", DEX / ADV * 100, 26.2, 0.01)
    chk("01 سقف المادة 5.3 (5%×ADV)", 0.05 * ADV, 26_750_000, 0.001)
    chk("01 التمويل السنوي (×3×365)", FR * 3 * 365 * 100, 25.2, 0.01)
    chk("01 OI/ADV", OI / ADV, 0.80)
    chk("01 OI/TVL %", OI / TVL * 100, 42.8, 0.01)
    chk("01 عتبة 1.5× OI/ADV", 1.5 * ADV, 802_500_000, 0.001)

    chk("02 سعر قبل 7 أيام", P / 1.078, 107.14, 0.001)
    chk("02 σ أسبوعي % (√365)", RV * math.sqrt(7 / 365) * 100, 7.70, 0.01)
    chk("02 z أسبوعي", 7.8 / (RV * math.sqrt(7 / 365) * 100), 1.01, 0.02)
    chk("02 z شهري", 21.4 / (RV * math.sqrt(30 / 365) * 100), 1.34, 0.02)
    z7_252 = 7.8 / (RV * math.sqrt(5 / 252) * 100)
    z30_252 = 21.4 / (RV * math.sqrt(21 / 252) * 100)
    print(f"    ⚠ 02 صف الحساسية √252 مُعلن 0.84σ/1.12σ — نافذة تقويمية مع سنة تداولية")
    print(f"      وبمطابقة النافذة (5 و21 شمعة): z7={z7_252:.2f} و z30={z30_252:.2f} "
          f"⇒ الخلاصة (z<1.5) تصمد")
    print(f"    ⚠ 02 «6.06 وحدة σ يومية» وصف إزاحة بالـ σ اليومي؛ "
          f"الـ z المطابق للنافذة = 1.34σ — وحدة العرض لا الدلالة")

    chk("03 VaR 99% (% من السعر)", 2.326 * sd * 100, 6.77, 0.01)
    chk("03 CVaR 99% (%)", 2.665 * sd * 100, 7.755, 0.01)
    chk("03 R² من 0.71", 0.71 ** 2, 0.504, 0.01)
    base = 0.214 / 0.556
    print(f"    ✘ 03 «√21 ⇒ 1.96»: 0.385×√21 = {base*math.sqrt(21):.3f} "
          f"و 0.385×√30 = {base*math.sqrt(30):.3f} ⇒ 1.96 يحتاج √26={base*math.sqrt(26):.3f}")
    print(f"    ✘ 03 «√(365/30) ⇒ 4.70»: 0.385×√(365/30) = {base*math.sqrt(365/30):.3f} "
          f"؛ و4.70 قابل لإعادة الإنتاج بطريقة أخرى: "
          f"(0.214×365/30)/0.556 = {(0.214*365/30)/0.556:.3f} ⇒ الصيغة المُعلنة لا تُنتجه")

    chk("06 تصفية 10× (MMR=0.5%)", P * (1 - 1 / 10 + 0.005), 104.53, 0.001)
    chk("06 تصفية 50× (MMR=0.5%)", P * (1 - 1 / 50 + 0.005), 113.77, 0.001)
    chk("06 التمويل اليومي/σ اليومي %", (FR * 3) / sd * 100, 2.37, 0.01)
    chk("06 APR/RV", FR * 3 * 365 / RV, 0.45, 0.02)
    chk("06 تمويل يوم / سبريد ذهاب وعودة", FR * 3 / (2 * SPR / 1e4), 2.03, 0.02)
    chk("06 OI بالعملة (AVAX)", OI / P, 3.72e6, 0.01)
    print("    ⚠ 06 خريطة التصفية مُعلنة بمركزين عشريين من معامل مفترض MMR=0.5% "
          "(غير موجود في اللقطة)")

    chk("08 Kelly f* = 0.214/0.556²", 0.214 / 0.556 ** 2, 0.69, 0.01)
    chk("08 العائد بعد التمويل/التقلب", (0.214 - 0.252 * 30 / 365) / 0.556, 0.348, 0.01)
    print("    ✘ 08 يُعلن في الادّعاء نفسه «≈0.31» و«≈0.348» — فرق 12% بلا منهج معلن للرقم الأول")
    print(f"    ✘ 08 يفترض عرضاً متداولاً 60–64M AVAX — لا وجود له في اللقطة؛ "
          f"TVL/MCap = {TVL/(60e6*P)*100:.2f}% إلى {TVL/(64e6*P)*100:.2f}% "
          f"⇒ 14.4% هو حد النطاق لا نقطة")
    print(f"    ✔ 04/05 تدفق −22M$ = {abs(NET)/ADV*100:.2f}% من الحجم اليومي — مطابق")
    print(f"    ✔ 05 TVL بالعملة الأصلية: 1.061/1.078 = {1.061/1.078:.4f} ⇒ −1.6%")


if __name__ == "__main__":
    raise SystemExit(main())
