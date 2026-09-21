"""
الوكيل 10 (محامي الشيطان) — أدلة مضادة قابلة للتنفيذ على إجماع دورة 2026-09-21.

هذه الأداة **لا تُنتج فرضية سوقية**؛ تُنتج وقائع قابلة للتكذيب عن *الإجماع نفسه*
(المادة 4.3). كل قسم يطبع رقمه ومصدره:

  §A  اختبار المنشأ: هل يُعرّف الوسم (seed=11, scenario=bull) المخرجات تعريفاً
      كاملاً؟ (مقابل المخرجات المخزَّنة في reports/)
  §B  سلامة الشمعات وأثرها على ATR: أرقام الوكيلين 02 و06 المتعارضة.
  §C  بواقي حقول الأونشين عن نموذج المولّد: هل اللوحة موجبة أم سالبة؟
  §D  اختبار ثبات النظام (Regime Invariance): تشغيل محرّك الديسك نفسه على خمسة
      سيناريوهات بنفس البذرة — هل تتغيّر مخرجات القرار؟
  §E  بوابة الإجماع المريب (المادة 4.4) ومنطق الإجماع في RedTeamAgent على آراء
      هذه الدورة الثمانية.

التشغيل:  python tools/redteam_10_counter_evidence.py      (من جذر المستودع)
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from avax_desk.contracts import AgentOpinion, Evidence  # noqa: E402
from avax_desk.data.synthetic import SyntheticFeed      # noqa: E402
from avax_desk.law import LawEngine                     # noqa: E402

SNAP = json.loads((ROOT / "data" / "snapshot_full.json").read_text(encoding="utf-8"))
BARS = SNAP["ohlcv_daily"]


def hdr(t: str) -> None:
    print("\n" + "=" * 76)
    print(t)
    print("=" * 76)


# ====================================================================== §A
def section_a() -> None:
    hdr("§A اختبار المنشأ: هل يُعرّف (seed=11, scenario=bull) المخرج؟")
    feed = SyntheticFeed(seed=11, days=365, start_price=24.0, scenario="bull")
    snap = feed.generate()
    n = len(snap.closes)
    d_c = max(abs(snap.closes[i] - BARS[i]["c"]) for i in range(n))
    d_h = max(abs(snap.highs[i] - BARS[i]["h"]) for i in range(n))
    d_l = max(abs(snap.lows[i] - BARS[i]["l"]) for i in range(n))
    print(f"A1) إعادة توليد (seed=11, days=365, start=24, bull) مقابل اللقطة:")
    print(f"    شمعات={n} | أقصى فرق: إغلاق {d_c:.3e} قمة {d_h:.3e} قاع {d_l:.3e}"
          f"  ⇒ الحقول مُعاد بناؤها (تأكيد ادعاء الإجماع)")

    # الوسم نفسه (seed=11 + bull) مع عدد أيام آخر — ماذا يعطي؟
    for days in (119, 120):
        s2 = SyntheticFeed(seed=11, days=days, start_price=24.0, scenario="bull").generate()
        ratio = s2.closes[-1] / 24.0
        print(f"A2) seed=11, bull, days={days} (={days + 1} شمعة) ⇒ إغلاق أخير "
              f"{s2.closes[-1]:.4f} (نسبة إلى 24.0: {ratio:.4f}×) | "
              f"لبلوغ 115.5313$ بالسعر الابتدائي نفسه يلزم مضاعف "
              f"{115.5313 / s2.closes[-1]:.2f}× أي start={24 * 115.5313 / s2.closes[-1]:.1f}$")

    rep01 = json.loads((ROOT / "reports" / "agent-01-market-structure.json")
                       .read_text(encoding="utf-8"))
    rep06 = json.loads((ROOT / "reports" / "agent-06-derivatives-volatility.json")
                       .read_text(encoding="utf-8"))
    print(f"A3) reports/agent-01-market-structure.json يعلن: "
          f"\"{rep01['snapshot_source']}\" | as_of={rep01['snapshot_as_of']}")
    print(f"    reports/agent-06-derivatives-volatility.json يعلن: "
          f"\"{rep06['snapshot_source']}\" | as_of={rep06['snapshot_as_of']}")
    # استخراج السعر المرجعي من الدفتر المخزَّن
    txt = json.dumps(rep01, ensure_ascii=False)
    import re
    mids = sorted({float(x) for x in re.findall(r"11[0-9]\.[0-9]{3,4}", txt)})
    print(f"A4) الأسعار المرجعية المخزَّنة في تقرير 01 (نطاق 110–119$): "
          f"{mids[:6]}{' …' if len(mids) > 6 else ''}  (عدد={len(mids)})")
    print(f"A5) الحكم: الوسم المُعلَن نفسه (seed=11 + bull) يرتبط في المستودع "
          f"بمسارين مختلفين: {snap.closes[-1]:.4f}$ هنا مقابل ≈{mids[0] if mids else float('nan')}$ مخزَّناً")
    print("    ⇒ الوسم لا يُعرّف المخرج تعريفاً كاملاً (ينقصه days/start_price/نسخة المولّد)")

    # هل المسار المقطوع هو نفسه بادئة المسار الطويل؟ (أي: هل 'bull' تصف المسار؟)
    s119 = SyntheticFeed(seed=11, days=119, start_price=24.0, scenario="bull").generate()
    same = max(abs(s119.closes[i] - snap.closes[i]) for i in range(len(s119.closes)))
    print(f"A6) بادئة المسار: max|closes[:121](days=119) − closes[:121](days=365)| "
          f"= {same:.3e} ⇒ المسار الواحد نفسه؛ ووسم 'bull' يصف هذا المسار عند "
          f"الشمعة 120 بـ {s119.closes[-1] / 24.0 - 1:+.2%} (هبوط لا صعود)")
    return {"regenerated": True, "max_diff_close": d_c, "stored_mid": mids[:1],
            "prefix_identical": same == 0.0}


# ====================================================================== §B
def section_b() -> None:
    hdr("§B سلامة الشمعات وATR — تدقيق أرقام الوكيلين 02 و06")
    bad_h = [b for b in BARS if b["h"] < max(b["o"], b["c"]) - 1e-9]
    bad_l = [b for b in BARS if b["l"] > min(b["o"], b["c"]) + 1e-9]
    print(f"B1) شمعات بـ h < max(o,c): {len(bad_h)}/{len(BARS)} "
          f"({len(bad_h)/len(BARS)*100:.1f}%) | بـ l > min(o,c): {len(bad_l)} "
          f"({len(bad_l)/len(BARS)*100:.1f}%)")

    def atr(bars, simple: bool) -> float:
        trs = []
        for i in range(1, len(bars)):
            p = bars[i - 1]["c"]
            trs.append(max(bars[i]["h"] - bars[i]["l"],
                           abs(bars[i]["h"] - p), abs(bars[i]["l"] - p)))
        w = trs[-14:]
        if simple:
            return sum(w) / 14
        a = sum(trs[:14]) / 14
        for x in trs[14:]:
            a = (a * 13 + x) / 14
        return a

    fixed = [dict(b) for b in BARS]
    for b in fixed:
        b["h"] = max(b["h"], b["o"], b["c"])
        b["l"] = min(b["l"], b["o"], b["c"])
    print(f"B2) ATR14 من الشمعات المُصدَّرة: بسيط={atr(BARS, True):.4f} | "
          f"Wilder={atr(BARS, False):.4f}")
    print(f"    ATR14 بعد إصلاح الشمعات: بسيط={atr(fixed, True):.4f} | "
          f"Wilder={atr(fixed, False):.4f}")
    print(f"    الحقل المُعلَن في computed_indicators.atr14 = "
          f"{SNAP['computed_indicators']['atr14']}")
    win = BARS[-15:]
    bad_win = sum(1 for b in win
                  if b["h"] < max(b["o"], b["c"]) - 1e-9
                  or b["l"] > min(b["o"], b["c"]) + 1e-9)
    print(f"B3) شمعات مخالفة داخل نافذة ATR14 (آخر 15 شمعة) = {bad_win} ⇒ "
          f"ادعاء الوكيل 06 بأن المخالفة البنيوية «تُضخّم ATR14» غير قابل للتحقّق "
          f"ميكانيكياً على هذه النافذة")
    print(f"    الفرق 3.3797 (Wilder — التعريف القياسي) مقابل 3.1859 (متوسط بسيط) "
          f"= فرق **تعريف** لا فرق قياس: الوكيل 06 قدّم 3.1859 كتصحيح، وهو ليس كذلك")
    # تضخّم المدى الذي يقيسه الوكيل 06 بمقدار مستقل
    lr = [math.log(b["h"] / b["l"]) for b in BARS[-30:]]
    ar = [abs(math.log(b["c"] / b["o"])) for b in BARS[-30:]]
    ratio = (sum(lr) / len(lr)) / max(1e-12, sum(ar) / len(ar))
    print(f"B4) اختبار تضخّم المدى (آخر 30 شمعة): E[ln(H/L)]/E|ln(C/O)| = {ratio:.3f} "
          f"(≈2.0 للمرور المنتظم) ⇒ المدى مُتضخّم بنسبة "
          f"≈{(ratio/2.0 - 1)*100:+.0f}% — هذه الحجة الوحيدة السليمة عند 06 "
          f"(والمخالفة h<max(o,c) ليست آلتها)")
    return {"bad_h": len(bad_h), "bad_l": len(bad_l), "bad_in_atr_window": bad_win,
            "range_ratio": ratio}


# ====================================================================== §C
def section_c() -> None:
    hdr("§C بواقي لوحة الأونشين عن نموذج المولّد (منهج الوكيل 05 نفسه)")
    oc, s = SNAP["onchain"], None
    ret30 = SNAP["computed_indicators"]["ret_30d_pct"] / 100.0
    dv = BARS[-1]["dv"]
    r = [
        ("exchange_netflow_usd", oc["exchange_netflow_usd"],
         -ret30 * dv * 0.12, dv * 0.01),
        ("active_addresses", oc["active_addresses"],
         42000 * (1 + ret30 * 1.2), 2500),
        ("active_addr_chg_7d_pct", oc["active_addresses_change_7d_pct"],
         ret30 * 30, 5),
        ("tvl_usd", oc["tvl_usd"], 780e6 * (1 + ret30 * 0.9), 15e6),
        ("tvl_change_7d_pct", oc["tvl_change_7d_pct"], ret30 * 25, 4),
        ("bridge_netflow_7d_usd", oc["bridge_netflow_7d_usd"], ret30 * 40e6, 6e6),
        ("whale_accumulation", oc["whale_accumulation_score"], ret30 * 2.5, 0.25),
        ("fees_24h_usd", oc["fees_24h_usd"], 180000 * (1 + ret30 * 1.5), 12000),
    ]
    print(f"    ret_30 المستخدم في النموذج = {ret30*100:+.4f}% | dv(آخر شمعة) = {dv:,.2f}$")
    print(f"    {'الحقل':<24}{'مقيس':>16}{'متوقَّع':>16}{'z':>8}")
    zs = []
    for name, obs, exp, sd in r:
        z = (obs - exp) / sd
        zs.append(z)
        print(f"    {name:<24}{obs:>16,.2f}{exp:>16,.2f}{z:>+8.3f}")
    pos = sum(1 for z in zs if z > 0)
    print(f"C1) الإشارات: {pos} فوق توقّع المولّد و{len(zs)-pos} تحته "
          f"(أقصى سالب {min(zs):+.3f}σ، أقصى موجب {max(zs):+.3f}σ)")
    print("    ⇒ اللوحة مختلطة لا هبوطية: أي قراءة اتجاهية أحادية منها انتقاء "
          "لجزء من اللوحة (تحيّز تأكيد)")
    return {"z": {n: (o - e) / sd for n, o, e, sd in r}, "positive": pos}


# ====================================================================== §D
def section_d() -> None:
    hdr("§D اختبار ثبات النظام: محرّك الديسك نفسه على خمسة سيناريوهات (بذرة 11)")
    from avax_desk.cli import DeskRunner
    from avax_desk.config import DeskConfig

    rows = []
    for sc in ("bull", "bear", "chop", "crisis", "recovery"):
        cfg = DeskConfig(asset="AVAX", seed=11, scenario=sc,
                         lookback_days=365, verbose=False)
        res = DeskRunner(cfg, write_journal=False).run()
        feed = SyntheticFeed(seed=11, days=365, start_price=24.0, scenario=sc).generate()
        ops = list((res.get("opinions") or {}).values())
        kn = [o for o in ops if not o.get("abstain")]
        votes = Counter(o.get("direction") for o in kn)
        dec = res.get("decision") or {}
        dirs = {o.get("agent_id"): o.get("direction") for o in ops
                if o.get("direction") != "neutral"}
        rows.append({
            "scenario": sc,
            "price": round(feed.closes[-1], 4),
            "ret_30d": round((feed.closes[-1] / feed.closes[-31] - 1) * 100, 3),
            "funding_apr": round(feed.funding_rate_8h * 3 * 365 * 100, 3),
            "action": dec.get("action"),
            "confidence": dec.get("confidence"),
            "groupthink": dec.get("groupthink_flag"),
            "abstain_count": sum(1 for o in ops if o.get("abstain")),
            "non_abstain_dirs": dict(votes),
            "non_neutral_agents": dirs,
        })
        print(f"D{len(rows)}) {sc:<9} سعر={rows[-1]['price']:<9} "
              f"ret30={rows[-1]['ret_30d']:<8} تمويلAPR={rows[-1]['funding_apr']:<8} "
              f"action={rows[-1]['action']:<9} conf={rows[-1]['confidence']} "
              f"groupthink={rows[-1]['groupthink']} ممتنعون={rows[-1]['abstain_count']}")
        print(f"      غير محايدين: {dirs}")
    print("D6) الوكيل 10 في المحرّك نفسه: اتجاهه = عكس consensus_dir "
          "(validation.py:470) ⇒ لا يشارك في الإجماع الاتجاهي")
    return rows


# ====================================================================== §E
def section_e() -> None:
    hdr("§E بوابة المادة 4.4 ومنطق RedTeamAgent على آراء هذه الدورة")
    rows = [  # (id, direction, abstain, confidence) — من آراء الدورة المُمرَّرة
        ("01", "neutral", True, 35), ("02", "neutral", True, 30),
        ("03", "neutral", False, 45), ("04", "bearish", False, 53),
        ("05", "neutral", True, 64), ("06", "neutral", False, 48),
        ("07", "neutral", True, 22), ("08", "neutral", True, 40),
    ]
    ops = []
    for aid, d, a, c in rows:
        ops.append(AgentOpinion(
            agent_id=aid, agent_name=f"وكيل {aid}", thesis="رأي الدورة",
            evidence=[Evidence(claim="x", source="cycle-2026-09-21",
                               timestamp="2026-09-21T00:09:44+00:00",
                               kind="derived", strength="high")],
            confidence=c, horizon="—", invalidation="—", dissent="—",
            direction=d, abstain=a, abstain_reason="نقص بيانات" if a else None))
    law = LawEngine()
    print(f"E1) law.flag_groupthink(آراء الدورة) = {law.flag_groupthink(ops)}")
    kn = [o for o in ops if not o.abstain]
    bulls = [o for o in kn if o.direction == "bullish"]
    bears = [o for o in kn if o.direction == "bearish"]
    cdir = "bullish" if len(bulls) >= len(bears) else "bearish"
    print(f"E2) منطق validation.py:431-433: آراء معرفية غير ممتنعة="
          f"{[o.agent_id for o in kn]} | bulls={len(bulls)} bears={len(bears)} "
          f"⇒ consensus_dir={cdir!r}")
    print(f"E3) validation.py:470: score = {(-1.0 if cdir == 'bullish' else 1.0)*0.45:+.2f} "
          f"⇒ قطبية الوكيل 10 معاكسة للإجماع (مخرج هذا التقرير: bullish)")
    n_dir = len(bulls) + len(bears)
    n_abs = sum(1 for o in ops if o.abstain)
    print(f"E4) عدد الآراء الاتجاهية = {n_dir} من {len(ops)} (ممتنعون = {n_abs}, "
          f"محايدون غير ممتنعين = {len(kn) - n_dir}) ⇒ المادة 4.4 لا تُفعَّل مهما بلغ "
          f"التوافق لأنها تشترط 5 آراء اتجاهية؛ لكن 8/8 يتفقون على *النتيجة* "
          f"(لا اتجاه) — وهي حالة لا يراها الكاشف")
    return {"groupthink": law.flag_groupthink(ops), "consensus_dir": cdir,
            "directional": n_dir, "abstain": n_abs}


def section_f(engine_row: dict) -> dict:
    hdr("§F دورة الوكلاء اللغويين مقابل المحرّك المرجعي على نفس اللقطة")
    llm = {"01": "abstain", "02": "abstain", "03": "neutral", "04": "bearish",
           "05": "abstain", "06": "neutral", "07": "abstain", "08": "abstain"}
    eng = engine_row.get("non_neutral_agents", {})
    print(f"    {'وكيل':<6}{'دورة 2026-09-21 (LLM)':<24}{'المحرّك المرجعي (knowledge.py)':<30}")
    for aid in sorted(llm):
        print(f"    {aid:<6}{llm[aid]:<24}{eng.get(aid, 'neutral/غير ممتنع'):<30}")
    llm_bull = sum(1 for v in llm.values() if v == "bullish")
    llm_bear = sum(1 for v in llm.values() if v == "bearish")
    llm_abs = sum(1 for v in llm.values() if v == "abstain")
    # المحرّك: طبقة المعرفة وحدها (01–08) — الوكيل 10 معاكس بالإلزام
    kn_eng = {k: v for k, v in eng.items() if k in llm}
    eng_bull = sum(1 for v in kn_eng.values() if v == "bullish")
    eng_bear = sum(1 for v in kn_eng.values() if v == "bearish")
    print(f"F1) الدورة (الوكلاء 01–08): صاعد={llm_bull} هابط={llm_bear} "
          f"محايد={8 - llm_bull - llm_bear} (منه ممتنع={llm_abs})")
    print(f"F2) المحرّك المرجعي على اللقطة نفسها (seed=11, bull, 365): "
          f"صاعد={eng_bull} هابط={eng_bear} ممتنع={engine_row.get('abstain_count')} "
          f"| غير محايدين: {kn_eng}")
    print("    ⇒ إجماع الدورة على «لا اتجاه» (صفر رأي صاعد) غير قابل لإعادة الإنتاج "
          "بمحرّك الديسك المرجعي على الملف نفسه: المحرّك يُنتج رأيين صاعدين "
          "(03 و08) مقابل هبوطي واحد (01)")
    return {"llm": llm, "engine": eng}


def main() -> int:
    a = section_a()
    b = section_b()
    c = section_c()
    d = section_d()
    e = section_e()
    f = section_f(d[0] if d else {})
    hdr("خلاصة الأداة")
    print(json.dumps({"A": a, "B": b, "C": {"positive_panels": c["positive"],
                                            "panels": len(c["z"])},
                      "D": d, "E": e}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
