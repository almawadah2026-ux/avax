"""
مسبار عدائي — يحاول كسر ديسك أفالانش.
كل فحص مستقل ويطبع النتيجة بدل أن يرفع استثناءً.
"""
import math
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from avax_desk import indicators as ind
from avax_desk.cli import DeskRunner
from avax_desk.config import DeskConfig
from avax_desk.contracts import AgentOpinion, Evidence, now_iso
from avax_desk.law import LawEngine
from avax_desk.risk.engine import RiskEngine

results = []


def probe(name, fn):
    try:
        out = fn()
        results.append(("OK", name, out))
    except Exception as exc:  # noqa: BLE001
        results.append(("CRASH", name, f"{type(exc).__name__}: {exc}"))
        traceback.print_exc(limit=3)


# ── P1: هل تتسرب الحالة بين دورتين على نفس المُشغّل؟ ──────────────────────
def p1():
    cfg = DeskConfig(scenario="bull", seed=11, daily_pnl_pct=-3.0, verbose=False)
    r = DeskRunner(cfg, write_journal=False)
    r1 = r.run()
    r2 = r.run()          # نفس الكائن، نفس المحرك، نفس السجل
    return {
        "run1_halted": cfg.halted,
        "run2_halted": cfg.halted,
        "run1_action": r1["decision"]["action"],
        "run2_action": r2["decision"]["action"],
        "run1_law_total": r1["law_audit"]["total"],
        "run2_law_total": r2["law_audit"]["total"],
        "run1_action_clean_cfg": "n/a",
    }


# ── P2: config نظيف بعده الصفر ثم دورة ثانية ─────────────────────────────
def p2():
    cfg = DeskConfig(scenario="bull", seed=11, daily_pnl_pct=-3.0, verbose=False)
    a = DeskRunner(cfg, write_journal=False).run()
    cfg2 = DeskConfig(scenario="bull", seed=11, daily_pnl_pct=0.0, verbose=False)
    b = DeskRunner(cfg2, write_journal=False).run()
    return {"with_loss": a["decision"]["action"], "no_loss_fresh_cfg": b["decision"]["action"]}


# ── P3: رأس مال صفري / ضئيل / ضخم ────────────────────────────────────────
def p3():
    out = {}
    for cap in (0.0, 1.0, 1e12):
        try:
            r = DeskRunner(DeskConfig(scenario="bull", seed=11, capital_usd=cap,
                                      verbose=False), write_journal=False).run()
            out[cap] = (r["decision"]["action"], r["decision"]["size_usd"],
                        r["risk"]["max_position_pct"])
        except Exception as exc:  # noqa: BLE001
            out[cap] = f"{type(exc).__name__}: {exc}"
    return out


# ── P4: سلاسل تاريخية قصيرة جداً ─────────────────────────────────────────
def p4():
    out = {}
    for days in (5, 20, 40, 60, 100):
        try:
            r = DeskRunner(DeskConfig(scenario="bull", seed=11, days=days,
                                      verbose=False), write_journal=False).run()
            comp = r["compliance"]
            out[days] = (r["decision"]["action"],
                         len(comp["violations"]) if comp else None,
                         comp["blocked"] if comp else None)
        except Exception as exc:  # noqa: BLE001
            out[days] = f"{type(exc).__name__}: {exc}"
    return out


# ── P5: بذور سالبة/صفرية ─────────────────────────────────────────────────
def p5():
    out = {}
    for seed in (-5, 0, 1):
        try:
            r = DeskRunner(DeskConfig(scenario="auto", seed=seed, verbose=False),
                           write_journal=False).run()
            out[seed] = r["decision"]["action"]
        except Exception as exc:  # noqa: BLE001
            out[seed] = f"{type(exc).__name__}: {exc}"
    return out


# ── P6: قيم متطرفة للمخاطر ───────────────────────────────────────────────
def p6():
    out = {}
    for pnl, dd in ((-100.0, 0.0), (0.0, 100.0), (-99.0, -99.0), (50.0, 0.0)):
        try:
            r = DeskRunner(DeskConfig(scenario="bull", seed=11, daily_pnl_pct=pnl,
                                      current_drawdown_pct=dd, verbose=False),
                           write_journal=False).run()
            out[(pnl, dd)] = (r["decision"]["action"], r["risk"]["risk_level"])
        except Exception as exc:  # noqa: BLE001
            out[(pnl, dd)] = f"{type(exc).__name__}: {exc}"
    return out


# ── P7: دقة _norm_ppf مقابل قيم مرجعية ───────────────────────────────────
def p7():
    ref = {0.50: 0.0, 0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263, 0.999: 3.0902}
    return {p: (round(ind._norm_ppf(p), 4), v) for p, v in ref.items()}


# ── P8: صحة risk_of_ruin ─────────────────────────────────────────────────
def p8():
    # p=0.6, b=1, risk 5%: حافة موجبة ⇒ خطر إفلاس منخفض
    return {
        "p0.6_b1_risk5%": round(ind.risk_of_ruin(0.6, 1.0, 0.05), 6),
        "p0.6_b1_risk50%": round(ind.risk_of_ruin(0.6, 1.0, 0.50), 6),
        "p0.5_b1_risk5%": round(ind.risk_of_ruin(0.5, 1.0, 0.05), 6),
        "p0.4_b1_risk5%": round(ind.risk_of_ruin(0.4, 1.0, 0.05), 6),
        "p0.9_b3_risk1%": round(ind.risk_of_ruin(0.9, 3.0, 0.01), 6),
    }


# ── P9: صحة kelly يدوياً ─────────────────────────────────────────────────
def p9():
    p, b = 0.6, 2.0
    manual = p - (1 - p) / b
    return {"manual": round(manual, 6), "code": round(ind.kelly_fraction(p, b), 6),
            "half_capped": round(ind.fractional_kelly(p, b, 0.5, 0.30), 6)}


# ── P10: حالات حدّية في المؤشرات ─────────────────────────────────────────
def p10():
    out = {}
    cases = {
        "empty": [],
        "one": [100.0],
        "constant": [100.0] * 50,
        "zeros": [0.0] * 50,
        "negative": [-5.0, -4.0, -3.0] * 20,
        "nan": [float("nan")] * 30,
        "inf": [float("inf")] * 30,
    }
    for name, series in cases.items():
        row = {}
        for fn_name, fn in (("rsi", lambda s: ind.rsi(s)),
                            ("hurst", lambda s: ind.hurst_exponent(s)),
                            ("half_life", lambda s: ind.half_life_ou(s)),
                            ("realized_vol", lambda s: ind.realized_vol(s)),
                            ("zscore", lambda s: ind.zscore(s)),
                            ("max_dd", lambda s: ind.max_drawdown(s)["max_dd_pct"]),
                            ("sharpe", lambda s: ind.annualized_sharpe(s)),
                            ("ulcer", lambda s: ind.ulcer_index(s))):
            try:
                v = fn(series)
                bad = isinstance(v, float) and (math.isnan(v) or math.isinf(v))
                row[fn_name] = f"{v}" + ("  ⚠️NaN/Inf" if bad else "")
            except Exception as exc:  # noqa: BLE001
                row[fn_name] = f"CRASH {type(exc).__name__}"
        out[name] = row
    return out


# ── P11: هل يمكن أن يصدر LONG مع compliance غير متوافق؟ ──────────────────
def p11():
    found = []
    for sc in ("bull", "bear", "chop", "crisis", "recovery"):
        for seed in range(1, 26):
            r = DeskRunner(DeskConfig(scenario=sc, seed=seed, verbose=False),
                           write_journal=False).run()
            comp = r["compliance"] or {}
            act = r["decision"]["action"]
            if act in ("LONG", "SHORT") and not comp.get("compliant", True):
                found.append((sc, seed, act, [v["code"] for v in comp["violations"]
                                              if v["severity"] == "error"]))
    return {"count": len(found), "samples": found[:5]}


# ── P12: هل يمكن أن يصدر قرار بحجم موجب مع نقض؟ ──────────────────────────
def p12():
    found = []
    for sc in ("bull", "bear", "chop", "crisis", "recovery"):
        for seed in range(1, 26):
            r = DeskRunner(DeskConfig(scenario=sc, seed=seed, verbose=False),
                           write_journal=False).run()
            risk = r["risk"]
            if risk["veto"] and r["decision"]["size_usd"] > 0:
                found.append((sc, seed, r["decision"]["size_usd"]))
    return {"count": len(found), "samples": found[:5]}


# ── P13: هل يتجاوز الحجم أي حدّ؟ ─────────────────────────────────────────
def p13():
    worst = 0.0
    worst_case = None
    for sc in ("bull", "bear", "chop", "crisis", "recovery"):
        for seed in range(1, 41):
            for cap in (100_000.0, 1_000_000.0, 50_000_000.0):
                r = DeskRunner(DeskConfig(scenario=sc, seed=seed, capital_usd=cap,
                                          verbose=False), write_journal=False).run()
                pct = (r["risk"] or {}).get("max_position_pct", 0.0)
                if pct > worst:
                    worst, worst_case = pct, (sc, seed, cap, r["decision"]["action"])
    return {"max_position_pct_seen": round(worst, 4), "case": worst_case,
            "limit": 10.0, "breach": worst > 10.0 + 1e-6}


# ── P14: هل يمكن تفادي "المنطقة الميتة" بإشارة ضعيفة؟ ───────────────────
def p14():
    cfg = DeskConfig(scenario="bull", seed=11, verbose=False)
    r = DeskRunner(cfg, write_journal=False).run()
    prop = r["proposal"]
    # ثقة مُدّعاة يدوياً من المكوّنات
    supporters = [r["opinions"][a] for a in prop["supporters"]]
    base = sum(o["net_confidence"] for o in supporters) / len(supporters) if supporters else 0
    signal = min(1.0, abs(prop["score"]) / 0.50)
    manual = 0.45 * base + 0.30 * 100 * prop["agreement"] + 0.25 * 100 * signal
    return {"reported": prop["confidence"], "manual_before_penalties": round(manual, 3),
            "penalties": prop["penalties"], "base_conf": round(base, 3),
            "agreement": prop["agreement"], "signal_strength": round(signal, 4)}


# ── P15: كسر سلسلة السجل — حذف سجل من المنتصف ────────────────────────────
def p15():
    import tempfile
    from avax_desk.journal.store import JournalStore
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "j.jsonl"
        s = JournalStore(p)
        for i in range(5):
            s.append({"i": i})
        lines = p.read_text(encoding="utf-8").splitlines()
        del lines[2]                                   # حذف من المنتصف
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        s2 = JournalStore(p)
        return s2.verify_chain()

    return None


# ── P16: إعادة ترتيب السجلات ─────────────────────────────────────────────
def p16():
    import tempfile
    from avax_desk.journal.store import JournalStore
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "j.jsonl"
        s = JournalStore(p)
        for i in range(5):
            s.append({"i": i})
        lines = p.read_text(encoding="utf-8").splitlines()
        lines[1], lines[3] = lines[3], lines[1]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return JournalStore(p).verify_chain()


# ── P17: إلحاق سجل مزيّف في النهاية ──────────────────────────────────────
def p17():
    import json as _json
    import tempfile
    from avax_desk.journal.store import JournalStore
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "j.jsonl"
        s = JournalStore(p)
        s.append({"i": 0})
        rows = [_json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
        forged = dict(rows[-1])
        forged["record_id"] = "JRN-FORGED"
        forged["payload"] = {"i": 999}
        # الهاش القديم مُعاد استخدامه ⇒ يجب أن يُكشف
        with p.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(forged, ensure_ascii=False) + "\n")
        return JournalStore(p).verify_chain()


# ── P18: الدوال المعرّفة وبلا مستدعٍ ─────────────────────────────────────
def p18():
    import re
    src = Path(__file__).resolve().parents[1] / "src"
    defs = {}
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for m in re.finditer(r"^(?:    )?def (\w+)", text, re.M):
            name = m.group(1)
            if name.startswith("__"):
                continue
            defs.setdefault(name, []).append(py.name)
    # ابحث عن الاستخدام في كل المشروع (بما فيه الاختبارات والأدوات والوثائق)
    root = Path(__file__).resolve().parents[1]
    corpus = ""
    for f in list(root.rglob("*.py")) + list(root.rglob("*.md")) + list(root.rglob("*.js")):
        if "__pycache__" in str(f):
            continue
        try:
            corpus += f.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    unused = []
    for name, files in sorted(defs.items()):
        # عدد مرات الظهور بعد التعريف نفسه
        occurrences = len(re.findall(rf"\b{re.escape(name)}\b", corpus))
        if occurrences <= len(files):
            unused.append((name, files[0]))
    return unused


# ── P19: هل تستخدم كل الحقول؟ ────────────────────────────────────────────
def p19():
    import re
    root = Path(__file__).resolve().parents[1]
    models = (root / "src" / "avax_desk" / "data" / "models.py").read_text(encoding="utf-8")
    fields = re.findall(r"^    (\w+):\s", models, re.M)
    corpus = ""
    for f in root.rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        corpus += f.read_text(encoding="utf-8")
    unused = [f for f in fields
              if len(re.findall(rf"\b{re.escape(f)}\b", corpus)) <= 1]
    return {"total_fields": len(fields), "possibly_unused": unused}


# ── P20: DeskConfig مشترك بين دورتين — هل halted يبقى؟ ───────────────────
def p20():
    cfg = DeskConfig(scenario="bull", seed=11, daily_pnl_pct=-3.0, verbose=False)
    DeskRunner(cfg, write_journal=False).run()
    halted_after_1 = cfg.halted
    cfg.daily_pnl_pct = 0.0            # المستخدم صحّح الحالة
    r2 = DeskRunner(cfg, write_journal=False).run()
    return {"halted_after_run1": halted_after_1,
            "halted_after_fix": cfg.halted,
            "run2_action": r2["decision"]["action"],
            "note": "إيقاف دائم لا يُرفع — لا مسار لإلغاء الإيقاف"}


# ── P21: live feed بلا شبكة ──────────────────────────────────────────────
def p21():
    from avax_desk.data.live import LiveFeed
    f = LiveFeed(days=30, timeout=0.001)
    snap = f.fetch()
    return {"source": snap.source, "degraded": len(f.degraded),
            "meta": snap.meta.get("fallback_reason", "")[:80],
            "warning": snap.meta.get("warning", "")[:60]}


# ── P22: حالة config.halted ابتدائياً True ───────────────────────────────
def p22():
    cfg = DeskConfig(scenario="bull", seed=11)
    cfg.halted = True
    r = DeskRunner(cfg, write_journal=False).run()
    return {"action": r["decision"]["action"], "size": r["decision"]["size_usd"],
            "rationale": r["decision"]["rationale"][:160]}


PROBES = [
    ("P1  تسرب الحالة بين دورتين على نفس المُشغّل", p1),
    ("P2  config نظيف بعد إيقاف", p2),
    ("P3  رأس مال صفري/ضئيل/ضخم", p3),
    ("P4  سلاسل تاريخية قصيرة", p4),
    ("P5  بذور سالبة/صفرية", p5),
    ("P6  قيم مخاطر متطرفة", p6),
    ("P7  دقة _norm_ppf", p7),
    ("P8  صحة risk_of_ruin", p8),
    ("P9  صحة kelly", p9),
    ("P10 حالات حدّية في المؤشرات", p10),
    ("P11 LONG مع التزام غير متوافق", p11),
    ("P12 قرار بحجم موجب مع نقض", p12),
    ("P13 تجاوز حد المركز", p13),
    ("P14 تحقق صيغة الثقة", p14),
    ("P15 حذف سجل من المنتصف", p15),
    ("P16 إعادة ترتيب السجلات", p16),
    ("P17 إلحاق سجل مزيّف", p17),
    ("P18 دوال معرّفة بلا مستدعٍ", p18),
    ("P19 حقول غير مستخدمة", p19),
    ("P20 إيقاف دائم لا يُرفع", p20),
    ("P21 live بلا شبكة", p21),
    ("P22 halted ابتدائي", p22),
]

for name, fn in PROBES:
    probe(name, fn)

print("=" * 100)
print("  نتائج المسبار العدائي")
print("=" * 100)
for status, name, out in results:
    icon = "✅" if status == "OK" else "💥"
    print(f"\n{icon} {name}")
    if status == "CRASH":
        print(f"    {out}")
    elif isinstance(out, dict):
        for k, v in out.items():
            print(f"    {k}: {v}")
    elif isinstance(out, list):
        for v in out[:20]:
            print(f"    {v}")
        if not out:
            print("    (لا شيء)")
    else:
        print(f"    {out}")
print("\n" + "=" * 100)
