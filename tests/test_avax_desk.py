"""
اختبارات ديسك أفالانش — تتحقق من أن الدستور **مفروض فعلاً** في الكود.

تُشغَّل بطريقتين:
    python tests/test_avax_desk.py         (بلا أي اعتماد خارجي)
    python -m pytest tests/ -v             (إن توفّر pytest)

كل اختبار هنا يقابل مادة دستورية أو سلوكاً جوهرياً. اختبار يمرّ بلا معنى
أسوأ من اختبار غائب — لأن الأول يعطي ثقة زائفة.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from avax_desk import indicators as ind                      # noqa: E402
from avax_desk.cli import DeskRunner                          # noqa: E402
from avax_desk.config import DeskConfig, Limits               # noqa: E402
from avax_desk.contracts import (                             # noqa: E402
    Action,
    AgentOpinion,
    Direction,
    Evidence,
    RiskVerdict,
    now_iso,
)
from avax_desk.data.synthetic import SyntheticFeed            # noqa: E402
from avax_desk.desks.base import compute_features             # noqa: E402
from avax_desk.journal.store import JournalStore              # noqa: E402
from avax_desk.law import LawEngine, ROSTER_BY_ID             # noqa: E402
from avax_desk.risk.engine import RiskEngine                  # noqa: E402


def _ok_evidence(**kw) -> Evidence:
    base = dict(claim="TVL أفالانش يرتفع", source="defillama/avalanche",
                timestamp=now_iso(), kind="onchain", strength="high")
    base.update(kw)
    return Evidence(**base)


def _opinion(**kw) -> AgentOpinion:
    base = dict(
        agent_id="02", agent_name="وكيل التحليل الفني",
        thesis="البنية الفنية تميل للصعود مع محاذاة المتوسطات",
        evidence=[_ok_evidence(kind="technical")],
        confidence=70.0, horizon="أيام", invalidation="إغلاق دون EMA50",
        dissent="المؤشرات مشتقة من السعر نفسه", direction="bullish",
    )
    base.update(kw)
    return AgentOpinion(**base)


# ==========================================================================
# المادة 2.5 — رقم بلا مصدر = رقم مُختلق
# ==========================================================================

def test_evidence_requires_source():
    for bad_source in ["", "  ", "unknown", "غير معروف"]:
        try:
            _ok_evidence(source=bad_source)
            raise AssertionError(f"قبل دليلاً بمصدر غير صالح: {bad_source!r}")
        except ValueError:
            pass


def test_evidence_requires_timestamp():
    try:
        _ok_evidence(timestamp="")
        raise AssertionError("قبل دليلاً بلا طابع زمني")
    except ValueError:
        pass


def test_evidence_rejects_unknown_kind():
    try:
        _ok_evidence(kind="vibes")
        raise AssertionError("قبل نوع دليل غير معروف")
    except ValueError:
        pass


# ==========================================================================
# المادة 2 — عقد الرأي
# ==========================================================================

def test_confidence_out_of_range_rejected():
    for bad in (-1.0, 101.0, 250.0):
        try:
            _opinion(confidence=bad)
            raise AssertionError(f"قبل ثقة خارج النطاق: {bad}")
        except ValueError:
            pass


def test_opinion_without_invalidation_rejected_by_law():
    law = LawEngine()
    op = _opinion(invalidation="")
    violations = law.validate_opinion(op)
    codes = {v.code for v in violations}
    assert "MISSING_INVALIDATION" in codes, "المادة 2.2 غير مفروضة!"


def test_opinion_without_evidence_rejected():
    law = LawEngine()
    op = _opinion(evidence=[])
    codes = {v.code for v in law.validate_opinion(op)}
    assert "CONFIDENCE_WITHOUT_EVIDENCE" in codes, "المادة 2.3 غير مفروضة!"


def test_clean_opinion_passes_law():
    law = LawEngine()
    op = _opinion(metrics={"note": "عادي"})
    errors = [v for v in law.validate_opinion(op) if v.severity == "error"]
    assert not errors, f"رأي سليم رُفض: {[str(e) for e in errors]}"


def test_abstention_is_legal():
    """المادة 9.1 — الامتناع مشروع ولا يُعاقب."""
    law = LawEngine()
    op = AgentOpinion.abstain_opinion("07", "وكيل المعنويات", "لا بيانات معنويات موثوقة")
    errors = [v for v in law.validate_opinion(op) if v.severity == "error"]
    assert not errors, "الامتناع عُوقب — خرق المادة 9.1"


# ==========================================================================
# المادة 1 — فصل السلطات
# ==========================================================================

def test_knowledge_agent_cannot_issue_imperative():
    law = LawEngine()
    op = _opinion(thesis="اشترِ الآن قبل الانفجار")
    codes = {v.code for v in law.validate_opinion(op)}
    assert "IMPERATIVE_BUY" in codes, "المادة 1.2 غير مفروضة على وكيل معرفي!"


def test_knowledge_agent_cannot_recommend():
    law = LawEngine()
    op = _opinion(metrics={"recommendation": "LONG 5%"})
    codes = {v.code for v in law.validate_opinion(op)}
    assert "KNOWLEDGE_AGENT_RECOMMENDS" in codes, "المادة 1.2 غير مفروضة (توصية)!"


def test_risk_agent_market_thesis_rejected():
    law = LawEngine()
    op = _opinion(agent_id="11", agent_name="وكيل المخاطر",
                  metrics={"market_thesis": "أتوقع صعوداً"})
    codes = {v.code for v in law.validate_opinion(op)}
    assert "RISK_AGENT_MARKET_THESIS" in codes, "المادة 1.3 غير مفروضة!"


# ==========================================================================
# المادة 0.2 — منع التنفيذ
# ==========================================================================

def test_execution_attempt_detected():
    law = LawEngine()
    for text in ["تم إرسال الأمر إلى المنصة", "order submitted", "اربط محفظتك الآن"]:
        v = law.enforce_no_execution(text, "12")
        assert v, f"لم يُكتشف محاولة تنفيذ: {text!r} (المادة 0.2)"


def test_analysis_language_not_flagged():
    law = LawEngine()
    harmless = "خطة تنفيذ نظرية عبر VWAP على 5 شرائح دون إرسال أي أمر"
    assert not law.enforce_no_execution(harmless, "12"), "إنذار كاذب على نص تحليلي"


# ==========================================================================
# المادة 8.8 — لغة اليقين
# ==========================================================================

def test_certainty_language_flagged():
    law = LawEngine()
    for text in ["هذه صفقة مضمونة", "ربح مؤكد بلا أي مخاطر", "guaranteed return"]:
        v = law.scan_prohibited(text, "02")
        assert v, f"لم تُكتشف لغة يقين: {text!r}"


# ==========================================================================
# المادة 3 — هرمية الأدلة
# ==========================================================================

def test_evidence_arbitration_prefers_lower_tier():
    law = LawEngine()
    strong = _ok_evidence(kind="onchain", claim="تدفق المنصات سالب")
    weak = _ok_evidence(kind="sentiment", claim="التويتر متفائل")
    winner, loser = law.arbitrate_evidence([weak, strong])
    assert winner.tier == 1, "المادة 3.2 غير مفروضة: الدليل الأقوى لم يُرجَّح"
    assert loser.tier == 5

    conflict = law.arbitrate_conflict(strong, weak)
    assert conflict["winner_tier"] == 1
    assert "3.2" in conflict["rule"]


def test_evidence_tier_ordering():
    assert ind and LawEngine.evidence_tier_of("onchain") < LawEngine.evidence_tier_of("sentiment")
    assert LawEngine.evidence_tier_of("inference") == 7
    assert LawEngine.evidence_tier_of("nonexistent") == 7


def test_stale_evidence_reduces_confidence():
    """المادة 3.4 — البيانات القديمة تُخفَّض ثقتها."""
    fresh = _opinion(confidence=80.0)
    old_ts = "2020-01-01T00:00:00+00:00"
    stale = _opinion(confidence=80.0,
                     evidence=[_ok_evidence(kind="technical", timestamp=old_ts)])
    assert stale.net_confidence < fresh.net_confidence, \
        "الثقة لم تنخفض مع دليل قديم — المادة 3.4 معطلة"


# ==========================================================================
# المادة 4.4 — الإجماع المريب
# ==========================================================================

def test_groupthink_detected():
    law = LawEngine()
    ops = [_opinion(agent_id=f"0{i}", direction="bullish", confidence=70.0)
           for i in range(1, 8)]
    result = law.flag_groupthink(ops)
    assert result["flag"], "الإجماع التام لم يُكتشف — المادة 4.4 معطلة"
    assert result["agreement"] == 1.0


def test_split_opinions_not_flagged():
    law = LawEngine()
    ops = ([_opinion(agent_id=f"0{i}", direction="bullish") for i in range(1, 5)]
           + [_opinion(agent_id=f"1{i}", direction="bearish") for i in range(1, 5)])
    assert not law.flag_groupthink(ops)["flag"], "إنذار كاذب على آراء منقسمة"


# ==========================================================================
# المادة 4.1 — قانون التحقق
# ==========================================================================

def test_validation_requirements_enforced():
    law = LawEngine()
    v = law.require_validation({}, "03")
    codes = {x.code for x in v}
    for required in ("MISSING_OOS_TESTED", "MISSING_COSTS_MODELED",
                     "MISSING_CAPACITY_CHECKED", "MISSING_OVERFITTING_CHECKED"):
        assert required in codes, f"المادة 4.1 لا تفرض {required}"

    good = law.require_validation({
        "oos_tested": True, "costs_modeled": True,
        "capacity_checked": True, "overfitting_checked": True,
        "excess_vs_benchmark": 1.2,
    }, "03")
    assert not good, "رفض إشارة مستوفية للشروط"


def test_suspicious_performance_flagged():
    """المادة 4.2 — نتيجة تتجاوز 3 أضعاف المعيار = شبهة."""
    law = LawEngine()
    v = law.require_validation({
        "oos_tested": True, "costs_modeled": True,
        "capacity_checked": True, "overfitting_checked": True,
        "excess_vs_benchmark": 5.0,
    }, "03")
    assert any(x.code == "SUSPICIOUS_PERFORMANCE" for x in v), "المادة 4.2 غير مفروضة"


# ==========================================================================
# المادة 5 — سيادة المخاطر
# ==========================================================================

def _features_and_snapshot(seed: int = 11, scenario: str = "bull"):
    snap = SyntheticFeed(seed=seed, days=365, scenario=scenario).generate()
    return compute_features(snap), snap


def test_low_confidence_vetoed():
    feats, snap = _features_and_snapshot()
    engine = RiskEngine(DeskConfig())
    verdict = engine.evaluate(feats, snap, "bullish", confidence=40.0)
    assert verdict.veto, "لم يُنقض قرار بثقة 40 (المادة 5.3)"
    assert verdict.position_size_usd == 0.0, "حجم موجب رغم النقض!"
    assert any("5.3" in r for r in verdict.veto_reasons)


def test_neutral_direction_vetoed():
    feats, snap = _features_and_snapshot()
    verdict = RiskEngine(DeskConfig()).evaluate(feats, snap, "neutral", confidence=90.0)
    assert verdict.veto, "سُمح بمركز بلا اتجاه"


def test_daily_loss_limit_halts():
    """المادة 5.4 — تجاوز حد الخسارة اليومية = إيقاف."""
    feats, snap = _features_and_snapshot()
    cfg = DeskConfig(daily_pnl_pct=-2.5)
    verdict = RiskEngine(cfg).evaluate(feats, snap, "bullish", confidence=90.0)
    assert verdict.veto
    assert verdict.risk_level == "red"
    assert verdict.position_size_usd == 0.0


def test_risk_levels_thresholds():
    engine = RiskEngine(DeskConfig())
    assert engine.risk_level(0.0, 0.0)[0] == "green"
    assert engine.risk_level(-0.8, 0.0)[0] == "yellow"
    assert engine.risk_level(-1.6, 0.0)[0] == "orange"
    assert engine.risk_level(-2.5, 0.0)[0] == "red"
    assert engine.risk_level(0.0, -20.0)[0] == "red"


def test_max_position_limit_respected():
    """كان التأكيد مُعلَّقاً بـ`if not verdict.veto` فيسقط صامتاً لو انقلب الحكم."""
    feats, snap = _features_and_snapshot()
    limits = Limits()
    cfg = DeskConfig(capital_usd=10_000_000.0, limits=limits)
    verdict = RiskEngine(cfg).evaluate(feats, snap, "bullish", confidence=85.0)
    assert verdict.approved, "المخاطر لم توافق على مدخل سليم — التغطية ساقطة"
    assert verdict.max_position_pct <= limits.max_position_pct + 1e-6, \
        f"تجاوز حد المركز: {verdict.max_position_pct}% > {limits.max_position_pct}%"


def test_win_probability_is_conservative():
    assert RiskEngine.win_probability(50) < 0.50
    assert RiskEngine.win_probability(88) < 0.70
    assert RiskEngine.win_probability(0) >= 0.30


def test_stop_and_targets_direction_aware():
    engine = RiskEngine(DeskConfig())
    up = engine.suggest_stops(100.0, 4.0, "bullish")
    dn = engine.suggest_stops(100.0, 4.0, "bearish")
    assert up["stop"] < 100.0 < up["target1"] < up["target2"]
    assert dn["stop"] > 100.0 > dn["target1"] > dn["target2"]


def test_risk_verdict_serializes():
    feats, snap = _features_and_snapshot()
    verdict = RiskEngine(DeskConfig()).evaluate(feats, snap, "bullish", 80.0)
    assert isinstance(verdict, RiskVerdict)
    payload = json.loads(json.dumps(verdict.to_dict(), ensure_ascii=False))
    assert "limits_checked" in payload


# ==========================================================================
# المادة 7 — السجل وسلسلة الهاش
# ==========================================================================

def test_journal_chain_valid_and_tamper_detected():
    with tempfile.TemporaryDirectory() as tmp:
        store = JournalStore(Path(tmp) / "j.jsonl")
        for i in range(3):
            store.append({"cycle": i}, kind="test")
        assert store.verify_chain()["valid"], "سلسلة سليمة ظهرت مكسورة"
        assert store.verify_chain()["records"] == 3

        # تعديل خارجي على السجل يجب أن يُكشف (المادة 7.2)
        lines = (Path(tmp) / "j.jsonl").read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[0])
        row["payload"]["cycle"] = 999
        lines[0] = json.dumps(row, ensure_ascii=False)
        (Path(tmp) / "j.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

        store2 = JournalStore(Path(tmp) / "j.jsonl")
        result = store2.verify_chain()
        assert not result["valid"], "⛔ تعديل السجل لم يُكتشف — المادة 7.2 معطلة!"
        assert result["broken"], "لم تُسجَّل تفاصيل الكسر"


def test_agent_weights_penalize_repeat_failures():
    """المادة 7.4 — 3 أخطاء متكررة ⇒ تخفيض الوزن."""
    with tempfile.TemporaryDirectory() as tmp:
        store = JournalStore(Path(tmp) / "j.jsonl")
        store.append({"post_mortem": {"agent_scores": [
            {"agent_id": "02", "correct": False},
            {"agent_id": "02", "correct": False},
            {"agent_id": "02", "correct": False},
            {"agent_id": "03", "correct": True},
            {"agent_id": "03", "correct": True},
            {"agent_id": "03", "correct": True},
        ]}})
        weights = store.agent_weights()
        assert weights["02"] == 0.50, f"وزن الوكيل المخطئ = {weights['02']}"
        assert weights["03"] == 1.25, f"وزن الوكيل الدقيق = {weights['03']}"


# ==========================================================================
# الرياضيات
# ==========================================================================

def test_indicators_sanity():
    feats, snap = _features_and_snapshot()
    assert 0.0 <= feats["rsi14"] <= 100.0
    assert feats["vol_30d_ann_pct"] >= 0.0
    assert 0.0 <= feats["hurst"] <= 1.0
    assert -1.0 <= feats["obi"] <= 1.0
    assert feats["spread_bps"] > 0
    assert feats["atr14"] > 0
    assert feats["completeness"] == 1.0


def test_kelly_and_fractional_cap():
    assert abs(ind.kelly_fraction(0.5, 1.0)) < 1e-9        # لا حافة ⇒ لا صفقة
    assert ind.kelly_fraction(0.5, 1.0) == 0.0
    assert ind.kelly_fraction(0.6, 2.0) > 0
    assert ind.fractional_kelly(0.9, 5.0, 0.5, 0.10) <= 0.10, "كيلي المقيد تجاوز السقف"
    assert ind.fractional_kelly(0.1, 1.0, 0.5, 0.10) == 0.0, "كيلي سالب لم يُصفَّر"


def test_var_ordering():
    _, snap = _features_and_snapshot(seed=3, scenario="crisis")
    rets = ind.log_returns(snap.closes)
    var = ind.value_at_risk(rets, 0.95)
    assert var["var_hist_pct"] < 0
    assert var["cvar_pct"] <= var["var_hist_pct"], "CVaR يجب أن يكون أسوأ من VaR"


def test_deflated_sharpe_bounds():
    assert 0.0 <= ind.deflated_sharpe_ratio(1.0, 24, 200) <= 1.0
    low = ind.deflated_sharpe_ratio(0.3, 24, 200)
    high = ind.deflated_sharpe_ratio(3.0, 24, 200)
    assert high > low, "DSR لا يتزايد مع قوة الأداء"


def test_position_size_by_risk():
    r = ind.position_size_by_risk(1_000_000, 1.0, entry=100.0, stop=95.0)
    assert abs(r["risk_amount_usd"] - 10_000.0) < 1e-6
    assert abs(r["units"] - 2000.0) < 1e-6      # 10000 / 5
    assert abs(r["notional_usd"] - 200_000.0) < 1e-6


def test_hurst_regime_detection():
    """سلسلة اتجاهية ⇒ H > 0.5 ؛ سلسلة عائدة للمتوسط ⇒ H < 0.5 ؛ سير عشوائي ≈ 0.5."""
    import random

    up = [100.0 * (1.01 ** i) for i in range(200)]
    assert ind.hurst_exponent(up) > 0.5, "لم يُكتشف النظام الاتجاهي"

    # عملية Ornstein-Uhlenbeck: عودة قوية للمتوسط
    rng = random.Random(7)
    x, ou = 100.0, []
    for _ in range(400):
        x += -0.5 * (x - 100.0) + rng.gauss(0.0, 2.0)
        ou.append(x)
    assert ind.hurst_exponent(ou) < 0.5, "لم يُكتشف نظام العودة للمتوسط"

    # سير عشوائي: يجب أن يقترب من 0.5
    rng2 = random.Random(3)
    rw = [100.0]
    for _ in range(400):
        rw.append(rw[-1] + rng2.gauss(0.0, 1.0))
    assert 0.35 <= ind.hurst_exponent(rw) <= 0.65, "السير العشوائي لا يعطي H ≈ 0.5"

    # الخاصية الأهم: الترتيب
    assert ind.hurst_exponent(up) > ind.hurst_exponent(ou)


def test_correlation_bounds():
    a = [float(i) for i in range(50)]
    assert abs(ind.correlation(a, a) - 1.0) < 1e-9
    assert abs(ind.correlation(a, [-x for x in a]) + 1.0) < 1e-9


# ==========================================================================
# التكامل — دورة كاملة
# ==========================================================================

def test_full_cycle_produces_decision():
    cfg = DeskConfig(scenario="bull", seed=11, verbose=False)
    result = DeskRunner(cfg, write_journal=False).run()
    assert result["decision"]["action"] in {a.value for a in Action}
    assert 0.0 <= result["decision"]["confidence"] <= 100.0
    assert result["decision"]["strongest_dissent"], "المادة 6: لا قرار بلا رأي مخالف"
    assert result["risk"] is not None
    assert result["compliance"] is not None
    assert len(result["opinions"]) >= 12, "دورة ناقصة — وكلاء لم يعملوا"


def test_decision_never_exceeds_risk_limits():
    cfg = DeskConfig(scenario="bull", seed=11, capital_usd=1_000_000.0, verbose=False)
    result = DeskRunner(cfg, write_journal=False).run()
    risk = result["risk"]
    if risk["veto"]:
        assert result["decision"]["size_usd"] == 0.0, \
            "قرار بحجم موجب رغم نقض المخاطر — خرق المادة 5.1!"
    else:
        assert risk["max_position_pct"] <= 10.0 + 1e-6


def test_determinism_same_seed_same_result():
    a = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   write_journal=False).run()
    b = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   write_journal=False).run()
    assert a["decision"]["action"] == b["decision"]["action"]
    assert a["decision"]["confidence"] == b["decision"]["confidence"]
    assert a["proposal"]["score"] == b["proposal"]["score"]


def test_desk_is_responsive_to_regime():
    """نظام يوافق دائماً أو يمتنع دائماً نظام مكسور."""
    actions = []
    for seed in range(1, 7):
        for scenario in ("bull", "bear", "crisis"):
            r = DeskRunner(DeskConfig(scenario=scenario, seed=seed, verbose=False),
                           write_journal=False).run()
            actions.append(r["decision"]["action"])
    directional = sum(1 for a in actions if a in ("LONG", "SHORT"))
    assert directional > 0, f"الديسك لم يتخذ أي قرار اتجاهي في {len(actions)} دورة — مقياس مكسور"
    assert directional < len(actions), "الديسك وافق دائماً — لا يوجد رفض"


def test_halted_desk_abstains():
    cfg = DeskConfig(scenario="bull", seed=11, verbose=False)
    cfg.halt("اختبار إيقاف")
    result = DeskRunner(cfg, write_journal=False).run()
    assert result["decision"]["action"] == Action.ABSTAIN.value
    assert result["decision"]["size_usd"] == 0.0


def test_journal_written_and_verifiable():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "desk.jsonl"
        cfg = DeskConfig(scenario="bull", seed=11, verbose=False)
        DeskRunner(cfg, journal_path=path).run()
        store = JournalStore(path)
        assert store.verify_chain()["valid"]
        assert len(store.decisions()) == 1


def test_snapshot_serialization_safe():
    snap = SyntheticFeed(seed=1, days=100, scenario="chop").generate()
    payload = json.loads(json.dumps(snap.to_dict(), ensure_ascii=False, default=str))
    assert payload["closes"]["n"] == 101


# ==========================================================================
# إصلاحات مراجعة مستقلة — كل اختبار يثبّت ثغرة كانت مفتوحة
# ==========================================================================

def test_orange_level_adds_veto_reason():
    """ثغرة: مستوى برتقالي كان يصفّر الحجم بلا سبب نقض ⇒ قرار اتجاهي بحجم صفر."""
    feats, snap = _features_and_snapshot()
    cfg = DeskConfig(daily_pnl_pct=-1.6)
    v = RiskEngine(cfg).evaluate(feats, snap, "bullish", confidence=90.0)
    assert v.risk_level == "orange"
    assert v.veto, "مستوى برتقالي بلا نقض — الثغرة عادت!"
    assert v.position_size_usd == 0.0
    assert any("9.3" in r for r in v.veto_reasons), "لا سبب نقض مرتبط بالمادة 9.3"


def test_sector_concentration_limit_enforced():
    """المادة 5.3 — حد التركّز القطاعي 25% (كان معرّفاً وغير مستخدم ثم غير قابل للوصول)."""
    feats, snap = _features_and_snapshot()

    # مستنفد ⇒ نقض صريح
    v_exhausted = RiskEngine(DeskConfig(current_sector_exposure_pct=30.0)).evaluate(
        feats, snap, "bullish", confidence=90.0)
    assert v_exhausted.veto, "تعرّض قطاعي 30% لم يُوقف المركز رغم حد 25%"
    assert any("التركّز القطاعي" in r for r in v_exhausted.veto_reasons)

    # متاح جزئياً ⇒ المرشّح القطاعي يعمل فعلاً (ليس مجرد كود غير قابل للوصول)
    v_partial = RiskEngine(DeskConfig(current_sector_exposure_pct=24.0)).evaluate(
        feats, snap, "bullish", confidence=90.0)
    assert v_partial.approved, "مركز بسيط لم يُعتمد مع تعرّض قطاعي متاح"
    assert v_partial.computed_size_usd <= 10_000.0 + 1e-6, \
        f"حجم {v_partial.computed_size_usd} تجاوز الميزانية القطاعية المتبقية (1% من 1M)"

    # ولا مسار تجاوز عبر المخاطر
    assert v_partial.max_position_pct <= 10.0 + 1e-6

    # CLI يمرّر التعرّض فعلاً (كان دائماً 0.0 — الفرض غير قابل للوصول)
    import inspect
    from avax_desk import cli as cli_mod
    src = inspect.getsource(cli_mod.main)
    assert "current_sector_exposure_pct=args.sector_exposure" in src, \
        "CLI لا يمرّر التعرّض القطاعي — المادة 5.3 غير قابلة للوصول"


def test_halt_called_on_red_level():
    """المادة 5.4 — الإيقاف الآلي (كانت halt() معرّفة وبلا مستدعٍ)."""
    cfg = DeskConfig(scenario="bull", seed=11, daily_pnl_pct=-3.0, verbose=False)
    assert not cfg.halted
    result = DeskRunner(cfg, write_journal=False).run()
    assert cfg.halted, "الديسك لم يُوقف نفسه رغم خرق حد الخسارة (المادة 5.4)"
    assert result["decision"]["action"] == Action.ABSTAIN.value


def test_kelly_is_not_a_decorative_constraint():
    """كيلي كان مقصوصاً عند حد المركز نفسه ⇒ قيد شكلي دائماً."""
    engine = RiskEngine(DeskConfig())
    low = ind.fractional_kelly(engine.win_probability(65), 1.5, 0.5, 0.30)
    high = ind.fractional_kelly(engine.win_probability(88), 1.5, 0.5, 0.30)
    assert high > low, "كيلي لا يتغير مع الثقة — لا يزال قيداً شكلياً"
    assert high > 0.10, "كيلي لا يمكن أن يتجاوز حد المركز أصلاً"


def test_reward_risk_is_consistent():
    """تناقض: DEFAULT_REWARD_RISK=1.5 مقابل R:R=1.0 المشتق من suggest_stops."""
    engine = RiskEngine(DeskConfig())
    for direction in ("bullish", "bearish"):
        s = engine.suggest_stops(100.0, 4.0, direction)
        assert abs(s["reward_risk"] - engine.DEFAULT_REWARD_RISK) < 1e-9, \
            f"R:R غير متسق: {s['reward_risk']} ≠ {engine.DEFAULT_REWARD_RISK}"


def test_high_volatility_triggers_yellow():
    """المادة 9.3 — «أصفر: تقلب مرتفع أو بيانات ناقصة»."""
    feats, snap = _features_and_snapshot()
    feats = dict(feats)
    feats["vol_regime"] = "extreme"
    v = RiskEngine(DeskConfig()).evaluate(feats, snap, "bullish", confidence=90.0)
    assert v.risk_level == "yellow", "التقلب المتطرف لم يفعّل المستوى الأصفر"
    assert any("9.3" in n for n in v.notes)


def test_lookahead_audit_is_causal():
    """المادة 8.3 — تدقيق تسريب البيانات المستقبلية (كان بلا فحص إطلاقاً)."""
    from avax_desk.desks.validation import lookahead_audit
    _, snap = _features_and_snapshot()
    audit = lookahead_audit(snap.closes)
    assert audit["clean"], "رُصد تسرّب مستقبلي في تنفيذ الإشارة"
    assert audit["checked_points"] > 0


def test_capacity_analysis_real_computation():
    """المادة 4.1 — تحليل القدرة (كان مُثبَّتاً True بلا حساب)."""
    from avax_desk.desks.validation import capacity_analysis
    ok = capacity_analysis(adv_usd=80e6, daily_vol_fraction=0.025, spread_bps=3.0, fee_bps=5.0)
    assert ok["capacity_usd"] > 0
    assert ok["binding"] in ("market_impact", "participipation_limit")

    # تكلفة أساسية تتجاوز الميزانية ⇒ قدرة صفر
    bad = capacity_analysis(adv_usd=80e6, daily_vol_fraction=0.025, spread_bps=200.0, fee_bps=50.0)
    assert bad["capacity_usd"] == 0.0


def test_compliance_blocks_fabrication_markers():
    """المادتان 8.1 و8.2 — كان الكاشف معرّفاً وبلا مسار تشغيل."""
    law = LawEngine()
    for text in ["المصدر غير معروف لكن الرقم دقيق",
                 "كما توقّعنا سابقاً بعد الحدث كان واضحاً"]:
        assert law.scan_prohibited(text, "05", codes={"FABRICATION_MARKER", "HINDSIGHT_MARKER"}), \
            f"لم يُكتشف النمط الصامت: {text!r}"

    cfg = DeskConfig(scenario="bull", seed=11, verbose=False)
    result = DeskRunner(cfg, write_journal=False).run()
    codes = {v["code"] for v in (result["compliance"] or {}).get("violations", [])}
    assert result["compliance"] is not None
    # الوكيل 09 يجب أن يكون قد أجرى الفحوص الأربعة فعلياً
    v09 = result["opinions"]["09"]["metrics"]
    for key in ("oos_tested", "costs_modeled", "capacity_checked", "overfitting_checked"):
        assert v09.get(key) is True, f"فحص {key} لم يُجرَ فعلياً (المادة 4.1)"


def test_journal_writes_markdown_summary():
    """المادة 7.1 — «JSON + ملخص Markdown»."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "desk.jsonl"
        DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   journal_path=path).run()
        summary = Path(tmp) / "SUMMARY.md"
        assert summary.exists(), "لم يُكتب ملخّص Markdown (المادة 7.1)"
        text = summary.read_text(encoding="utf-8")
        assert "سلامة السلسلة" in text and "أوزان الوكلاء" in text


# ==========================================================================
# الجولة الثانية — ثغرات كشفها التدقيق العدائي
# ==========================================================================

def test_no_directional_decision_without_risk_approval():
    """🔴 حرج: كان يمكن أن يصدر LONG بحجم صفر مع approved=False و veto=False."""
    for cap in (0.0, 0.01, 1.0, 50.0, 500.0):
        r = DeskRunner(DeskConfig(scenario="bull", seed=11, capital_usd=cap,
                                  verbose=False), write_journal=False).run()
        rk = r["risk"]
        act = r["decision"]["action"]
        size = r["decision"]["size_usd"]
        if not rk["approved"]:
            assert act == Action.ABSTAIN.value, (
                f"قرار اتجاهي ({act}) رغم approved=False — الثغرة عادت!")
            assert size == 0.0
        # لا قرار اتجاهي بحجم صفري مهما كان رأس المال
        if act in (Action.LONG.value, Action.SHORT.value):
            assert size >= 100.0, (
                f"قرار اتجاهي بحجم ${size} — أدنى من الحد القابل للتنفيذ")


def test_risk_verdict_is_internally_consistent():
    feats, snap = _features_and_snapshot()
    for cap in (0.0, 1_000.0, 1_000_000.0):
        v = RiskEngine(DeskConfig(capital_usd=cap)).evaluate(feats, snap, "bullish", 80.0)
        if v.approved:
            assert v.position_size_usd > 0, "اعتماد بحجم صفري"
            assert not v.veto, "اعتماد مع نقض"
        else:
            assert v.position_size_usd == 0.0, "حجم موجب دون اعتماد"


def test_drawdown_sign_is_agnostic():
    """🔴 حرج: `--drawdown 20` (القراءة الطبيعية) كانت تُعطي مستوى أخضر وحماية معطّلة."""
    engine = RiskEngine(DeskConfig())
    assert engine.risk_level(0.0, 20.0)[0] == "red", "تراجع موجب 20% لم يُفعّل الأحمر"
    assert engine.risk_level(0.0, -20.0)[0] == "red", "تراجع سالب 20% لم يُفعّل الأحمر"
    assert engine.risk_level(0.0, 8.0)[0] == "yellow"
    assert engine.risk_level(0.0, -8.0)[0] == "yellow"
    assert engine.risk_level(0.0, 2.0)[0] == "green"

    # وعلى مستوى الدورة الكاملة
    r = DeskRunner(DeskConfig(scenario="bull", seed=11, current_drawdown_pct=20.0,
                              verbose=False), write_journal=False).run()
    assert r["risk"]["risk_level"] == "red"
    assert r["decision"]["action"] == Action.ABSTAIN.value


def test_post_decision_audit_runs():
    """🔴 حرج: قرار المنسّق (14) كان لا يُدقَّق إطلاقاً من وكيل الالتزام (13)."""
    r = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   write_journal=False).run()
    post = r.get("post_decision_audit")
    assert post is not None, "لا تدقيق بعدي للقرار — ثغرة الحوكمة عادت"
    assert post["audited"] is True
    assert "valid" in post
    assert post["checked"] > 0, "التدقيق البعدي لم يفحص شيئاً"
    codes = {v["code"] for v in post["violations"] if v["severity"] == "error"}
    assert not codes, f"القرار أنتج مخالفات حرجة في التدقيق البعدي: {codes}"


def test_audit_log_resets_between_runs():
    from avax_desk.law import Violation
    runner = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                        write_journal=False)
    runner.law.audit_log.append(Violation("9.9", "INJECTED", "مخالفة محقونة"))
    a = runner.run()
    b = runner.run()
    assert a["law_audit"]["total"] == b["law_audit"]["total"], \
        "سجل المخالفات يتراكم بين الدورات — تقارير التدقيق ملوّثة"


def test_hindsight_marker_has_no_false_positive():
    """إيجابية كاذبة: النمط كان يطابق كلمة hindsight المجرّدة (تعريفاً لا ادّعاءً)."""
    law = LawEngine()
    benign = ["نحسب Hindsight Bias كمقياس معايرة",
              "التحيّز الاسترجاعي (Hindsight Bias) خطأ شائع"]
    for text in benign:
        assert not law.scan_prohibited(text, "15", codes={"HINDSIGHT_MARKER"}), \
            f"إيجابية كاذبة على نص تعريفي: {text!r}"

    guilty = ["in hindsight the entry was obviously wrong",
              "معرفة لاحقة: with hindsight"]
    for text in guilty:
        assert law.scan_prohibited(text, "15", codes={"HINDSIGHT_MARKER"}), \
            f"لم يُكتشف ادّعاء استرجاعي صريح: {text!r}"


def test_tier_weights_have_single_source_of_truth():
    """
    أوزان هرمية الأدلة يجب أن تكون معرّفة في موضع واحد، وأن تتطابق مع ما تجمعه
    `weighted_evidence_score`. (كانت وثائق الوكلاء 13/14 تذكر أوزاناً مختلفة.)
    """
    from avax_desk.contracts import Evidence
    code_weights = {1: 1.00, 2: 0.95, 3: 0.90, 4: 0.80, 5: 0.65, 6: 0.50, 7: 0.30}
    text = (ROOT / "src" / "avax_desk" / "indicators.py").read_text(encoding="utf-8")
    for tier, w in code_weights.items():
        assert f"{tier}: {w:.2f}" in text, f"وزن الطبقة {tier} غير موجود بصيغته المتوقعة"

    # وكلاء المعرفة: طبقة الأدلة تُشتق من نوع الدليل لا من رقم يدوي
    assert Evidence(claim="x", source="s", timestamp=now_iso(), kind="onchain").tier == 1
    assert Evidence(claim="x", source="s", timestamp=now_iso(), kind="inference").tier == 7


def test_abstain_does_not_bypass_prohibited_scan():
    """ثغرة: الامتناع كان يعود قبل كل فحوص المادة 8، فيمرّ نص محرّم بلا عقاب."""
    law = LawEngine()
    op = AgentOpinion(
        agent_id="07", agent_name="وكيل المعنويات",
        thesis="اشترِ الآن — صفقة مضمونة بلا أي مخاطر 100%",
        evidence=[], confidence=0.0, horizon="—", invalidation="—", dissent="—",
        direction="neutral", abstain=True, abstain_reason="لا بيانات",
    )
    codes = {v.code for v in law.validate_opinion(op)}
    assert codes, "الامتناع أعفى الرأي من فحص السلوك المحرّم (المادة 8)"


def test_bogus_source_rejected_without_false_positive():
    """المادة 2.5 — 'مصدر غير معروف' كان يمرّ؛ و'c-chain/active' لا يجوز رفضه."""
    for bad in ["غير معروف", "مصدر غير معروف", "unknown", "N/A", "n/a", "TBD",
                "lorem ipsum", "placeholder"]:
        try:
            _ok_evidence(source=bad)
            raise AssertionError(f"قُبل مصدر وهمي: {bad!r}")
        except ValueError:
            pass
    # مسارات حقيقية تحتوي تسلسلات شبيهة لا تُرفض
    for good in ["synthetic-sim/c-chain/active-addresses", "defillama/avalanche-tvl",
                 "alternative.me/fear-greed", "binance/none-of-your-business-v2"]:
        _ok_evidence(source=good)


def test_blocked_decision_has_zero_size():
    """ثغرة: القرار المحجوب كان يحتفظ بحجم مخاطر موجب ويُطبع تحت «الامتناع»."""
    # حالة إيقاف أحمر
    cfg = DeskConfig(scenario="bull", seed=11, daily_pnl_pct=-3.0, verbose=False)
    r = DeskRunner(cfg, write_journal=False).run()
    assert r["decision"]["action"] == Action.ABSTAIN.value
    assert r["decision"]["size_usd"] == 0.0, \
        f"قرار ممتنع بحجم ${r['decision']['size_usd']} — تناقض"

    # حالة حجب بسبب ثقة منخفضة: الحجم المحسوب يبقى موثّقاً بينما المعتمد صفر
    for seed in range(1, 25):
        rr = DeskRunner(DeskConfig(scenario="chop", seed=seed, verbose=False),
                        write_journal=False).run()
        if (rr["decision"]["action"] == Action.ABSTAIN.value
                and rr["risk"]["computed_size_usd"] > 0):
            assert rr["decision"]["size_usd"] == 0.0, \
                "قرار ممتنع احتفظ بالحجم المحسوب كأنه معتمد"
            return
    raise AssertionError("لم تُوجد حالة اختبار مناسبة (حجب بحجم محسوب موجب)")


def test_risk_verdict_contract_enforced():
    """العقد كان بلا تحقق — يمكن بناء حكم متناقض."""
    from avax_desk.contracts import RiskVerdict
    for bad in (dict(approved=True, veto=True, position_size_usd=1000.0),
                dict(approved=True, veto=False, position_size_usd=0.0),
                dict(approved=False, veto=True, position_size_usd=500.0)):
        try:
            RiskVerdict(**bad)
            raise AssertionError(f"قُبل حكم مخاطر متناقض: {bad}")
        except ValueError:
            pass
    RiskVerdict(approved=True, veto=False, position_size_usd=1000.0)   # سليم
    RiskVerdict(approved=False, veto=True, position_size_usd=0.0)      # سليم


def test_lookahead_audit_self_test_can_fail():
    """الأداة كانت تحصيل حاصل؛ الآن يجب أن تُثبت قدرتها على الكشف."""
    from avax_desk.desks.validation import lookahead_audit
    _, snap = _features_and_snapshot()
    audit = lookahead_audit(snap.closes)
    assert audit["clean"]
    assert audit["self_test_passed"], "الاختبار الذاتي للكاشف فشل"
    assert audit["leak_detected_in_self_test"] > 0, \
        "الكاشف لم يكتشف مُقدِّراً مُسرِّباً عمداً — لا قيمة لاجتيازه"


# ==========================================================================
# الجولة الثالثة — إغلاق الثغرات الحرجة المتبقية
# ==========================================================================

def test_validation_is_verified_independently():
    """R1: كان `require_validation` يتلقى شهادة الوكيل 09 عن نفسه — دائري."""
    import inspect
    from avax_desk.desks import control as ctl
    src = inspect.getsource(ctl.ComplianceAgent)
    assert "_verify_validation_independently" in src, "لا يوجد تحقق مستقل"
    assert "capacity_analysis" in src and "lookahead_audit" in src, \
        "التحقق المستقل لا يعيد حساب الفحوص"

    # دورة سليمة ⇒ التحقق المستقل لا يجد تلاعباً
    r = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   write_journal=False).run()
    codes = {v["code"] for v in (r["compliance"] or {}).get("violations", [])}
    assert not (codes & {"VALIDATION_SELF_REPORT_MISMATCH", "CAPACITY_SELF_REPORT_MISMATCH",
                         "BACKTEST_STRUCTURE_INCOMPLETE", "OOS_CLAIM_WITHOUT_RUN"}), \
        f"التحقق المستقل رصد مخالفة في دورة سليمة: {codes}"


def test_primary_evidence_conflict_rule():
    """R2: المادة 3.2 — دليل الطبقة 1 يجب أن يرجّح على الأضعف، لا أن يُهمَل."""
    law = LawEngine()

    def _op(aid, direction, kind, conf):
        return AgentOpinion(
            agent_id=aid, agent_name=aid, thesis="فرضية اختبارية واضحة ورقمية",
            evidence=[_ok_evidence(kind=kind, source=f"test/{aid}")],
            confidence=conf, horizon="أيام", invalidation="شرط إبطال واضح",
            dissent="مخالف", direction=direction)

    ops = [_op("05", "bearish", "onchain", 80),
           _op("02", "bullish", "technical", 80),
           _op("03", "bullish", "technical", 80),
           _op("04", "bullish", "technical", 80)]
    res = law.primary_evidence_conflict(ops, "bullish")
    assert res["conflict"], "المادة 3.2 غير مفروضة: دليل الطبقة 1 خسر أمام ثلاثة من الطبقة 4"
    assert res["tier"] == 1 and res["agent_id"] == "05"
    assert "3.2" in res["rule"]

    # بلا دليل أولي ⇒ لا تعارض
    ops2 = [_op("02", "bearish", "technical", 80), _op("03", "bullish", "technical", 80)]
    assert not law.primary_evidence_conflict(ops2, "bullish")["conflict"]

    # دليل أولي منخفض الثقة لا يوقف القرار
    ops3 = [_op("05", "bearish", "onchain", 30), _op("03", "bullish", "technical", 80)]
    assert not law.primary_evidence_conflict(ops3, "bullish")["conflict"]


def test_orchestrator_evidence_is_not_original():
    """المادة 1.4 — المنسّق لا يُنتج دليلاً أصلياً."""
    r = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   write_journal=False).run()
    op14 = r["opinions"].get("14") or {}
    srcs = [e["source"] for e in op14.get("evidence", [])]
    assert srcs, "رأي المنسّق بلا أدلة"
    assert all(s.startswith("aggregation/") for s in srcs), \
        f"أدلة أصلية في رأي المنسّق — خرق المادة 1.4: {srcs}"
    codes = {v["code"] for v in (r["post_decision_audit"] or {}).get("violations", [])}
    assert "ORCHESTRATOR_PRODUCED_EVIDENCE" not in codes


def test_excess_vs_benchmark_is_computed():
    """المادة 4.2 — كان الحقل مُعلناً في require_validation ولا يُحسَب أبداً."""
    r = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   write_journal=False).run()
    bt = r["opinions"]["09"]["metrics"]["backtest"]
    for key in ("benchmark_buy_hold_pct", "strategy_return_pct", "excess_vs_benchmark"):
        assert key in bt, f"الحقل {key} غير محسوب"
    assert isinstance(bt["excess_vs_benchmark"], (int, float))


def test_dissent_source_is_recorded():
    """المادة 6.3 — كان الحقل لا يفرغ أبداً (نص احتياطي مبرمج) فالفحص شكلي."""
    r = DeskRunner(DeskConfig(scenario="bull", seed=11, verbose=False),
                   write_journal=False).run()
    src = r["decision"].get("dissent_source")
    assert src in ("agent", "fallback", "none"), f"مصدر مخالف غير معروف: {src}"
    law = LawEngine()
    v = law.validate_decision_completeness(["01"], [], "نص احتياطي", dissent_source="fallback")
    assert any(x.code == "DISSENT_IS_FALLBACK" for x in v), \
        "الرأي المخالف الاحتياطي لم يُرصد"


def test_aggregate_exposure_blocks_splitting():
    """المادة 8.7 — الالتفاف على الحدود بتقسيم المراكز."""
    limits = Limits()
    # عشرة مراكز بـ9% = 90% من رأس المال، وكل واحد «تحت الحد» منفرداً
    positions = [{"notional_usd": 90_000.0, "sector": "layer-1"} for _ in range(10)]
    v = LawEngine.aggregate_exposure_violations(
        positions, 90_000.0, "layer-1", 1_000_000.0, limits)
    codes = {x.code for x in v}
    assert "AGGREGATE_EXPOSURE_EXCEEDED" in codes, "التعرّض الكلي غير مفحوص"
    assert "SECTOR_EXPOSURE_EXCEEDED" in codes, "التعرّض القطاعي غير مفحوص"

    # وضع سليم
    clean = LawEngine.aggregate_exposure_violations([], 50_000.0, "layer-1", 1_000_000.0, limits)
    assert not [x for x in clean if x.severity == "error"]


def test_loss_not_disclosed_is_caught():
    """المادة 8.4 — إخفاء الخسائر."""
    import inspect
    from avax_desk.desks import control as ctl
    src = inspect.getsource(ctl.ComplianceAgent.audit_decision)
    assert "LOSS_NOT_DISCLOSED" in src, "لا فحص لإخفاء الخسائر (المادة 8.4)"


def test_hurst_is_correct_after_fix():
    """R6: كان خط مستقيم يُعطي H=0.5 (سير عشوائي) وموجة جيبية H=0.76."""
    import random
    line = [100.0 + 2.0 * i for i in range(300)]
    assert ind.hurst_exponent(line) > 0.9, "الخط المستقيم ليس اتجاهياً — المقياس مقلوب"

    rng = random.Random(3)
    rw = [100.0]
    for _ in range(500):
        rw.append(rw[-1] + rng.gauss(0.0, 1.0))
    assert 0.40 <= ind.hurst_exponent(rw) <= 0.60, "السير العشوائي لا يعطي H ≈ 0.5"

    rng2 = random.Random(7)
    x, ou = 100.0, []
    for _ in range(500):
        x += -0.5 * (x - 100.0) + rng2.gauss(0.0, 2.0)
        ou.append(x)
    assert ind.hurst_exponent(ou) < 0.5, "عملية OU ليست عائدة للمتوسط"


def test_snapshot_series_are_aligned():
    """R8: كان len(closes)=201 و len(volumes)=200 ⇒ إزاحة شمعة في ميزات الحجم."""
    s = SyntheticFeed(seed=1, days=100, scenario="chop").generate()
    assert len(s.closes) == len(s.volumes) == len(s.dollar_volumes), \
        "السلاسل غير محاذاة — الميزات المرتبطة بالحجم مُزاحة"
    f = compute_features(s)
    assert f["length_aligned"] is True


def test_completeness_detects_bad_data():
    """R10: كان الاكتمال 100% لسلسلة حجوم كلها أصفار."""
    s = SyntheticFeed(seed=1, days=365, scenario="bull").generate()
    good = compute_features(s)["completeness"]
    assert good == 1.0, f"بيانات سليمة أعطت اكتمالاً {good}"

    s.dollar_volumes = [0.0] * len(s.dollar_volumes)
    s.volumes = [0.0] * len(s.volumes)
    assert compute_features(s)["completeness"] < 1.0, \
        "سلسلة حجوم صفرية اعتُبرت بيانات مكتملة"

    short = SyntheticFeed(seed=1, days=70, scenario="bull").generate()
    assert compute_features(short)["completeness"] < 1.0, \
        "سلسلة قصيرة اعتُبرت مكتملة"


def test_halt_persists_across_runners():
    """R20: المادة 5.4 — «يتوقف آلياً لبقية اليوم» كان في الذاكرة فقط."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "j.jsonl"
        from avax_desk.config import DeskConfig as DC
        DeskRunner(DC(scenario="bull", seed=11, daily_pnl_pct=-3.0, verbose=False),
                   journal_path=path).run()
        assert (Path(tmp) / "halt_state.json").exists(), "لم تُحفظ حالة الإيقاف"

        r2 = DeskRunner(DC(scenario="bull", seed=11, daily_pnl_pct=0.0, verbose=False),
                        journal_path=path).run()
        assert r2["decision"]["action"] == Action.ABSTAIN.value
        assert r2["decision"]["abstention_kind"] == "halted", \
            "الإيقاف لم يُستعد في تشغيل جديد"

        cfg = DC(scenario="bull", seed=11, daily_pnl_pct=0.0, verbose=False)
        cfg.resume("اختبار")
        r3 = DeskRunner(cfg, journal_path=path).run()
        assert r3["decision"]["abstention_kind"] != "halted", "--resume لم يرفع الإيقاف"


def test_constitution_fingerprint_tracks_amendment():
    """المادة 10.1 — تعديل الدستور يجب أن يُكشف."""
    with tempfile.TemporaryDirectory() as tmp:
        store = JournalStore(Path(tmp) / "j.jsonl")
        const = Path(tmp) / "CONSTITUTION.md"
        const.write_text("v1", encoding="utf-8")
        first = store.constitution_fingerprint(const)
        assert first["sha256"] and first["previous"] is None and first["changed"] is False

        store.append({"constitution_fingerprint": {"sha256": first["sha256"]}})
        same = store.constitution_fingerprint(const)
        assert same["changed"] is False

        const.write_text("v2 بلا وثيقة تصحيحية", encoding="utf-8")
        changed = store.constitution_fingerprint(const)
        assert changed["changed"] is True, "تعديل الدستور لم يُكتشف"
        assert "10.1" in changed["note"]


def test_abstention_rate_is_measured():
    """المادة 9.2 — كان حكم «60% امتناع = نجاح» بلا أي قياس."""
    with tempfile.TemporaryDirectory() as tmp:
        store = JournalStore(Path(tmp) / "j.jsonl")
        for i in range(4):
            store.append({"decision": {"decision_id": f"D{i}", "action":
                                       "ABSTAIN" if i < 3 else "LONG",
                                       "abstention_kind": "no_edge" if i < 3 else ""}})
        summary = store.summary()
        assert summary["abstention_rate"] == 0.75
        assert summary["abstention_kinds"].get("no_edge") == 3
        assert "9.2" in summary["abstention_note"]


def test_abstention_has_no_supporting_evidence_requirement():
    """المادة 6.3: «قرار اتجاهي بلا مؤيد» خطأ — أما الامتناع فلا مؤيد له بطبيعته."""
    law = LawEngine()
    directional = law.validate_decision_completeness([], [], "مخالف", "agent", directional=True)
    assert any(x.code == "NO_SUPPORTING_EVIDENCE" for x in directional), \
        "قرار اتجاهي بلا مؤيد لم يُرصد"

    abstain = law.validate_decision_completeness([], [], "مخالف", "agent", directional=False)
    assert not any(x.code == "NO_SUPPORTING_EVIDENCE" for x in abstain), \
        "امتناع بلا اتجاه عوقب على غياب المؤيدين — إنذار كاذب"

    # وفي دورة كاملة: صفر مخالفات عبر السيناريوهات
    for sc in ("bull", "bear", "crisis"):
        r = DeskRunner(DeskConfig(scenario=sc, seed=3, verbose=False),
                       write_journal=False).run()
        post = r.get("post_decision_audit") or {}
        errs = [v["code"] for v in post.get("violations", []) if v["severity"] == "error"]
        assert not errs, f"دورة {sc} أنتجت مخالفة بعدية: {errs}"

    # أنواع الامتناع مصنّفة
    kinds = set()
    for seed in range(1, 15):
        r = DeskRunner(DeskConfig(scenario="chop", seed=seed, verbose=False),
                       write_journal=False).run()
        k = r["decision"].get("abstention_kind")
        if k:
            kinds.add(k)
    assert kinds, "لا نوع امتناع مسجّل"
    assert kinds <= {"no_edge", "risk_veto", "compliance_block", "halted"}, \
        f"نوع امتناع غير معروف: {kinds}"


def test_roster_is_single_source_of_truth():
    """
    S6: الكشف كان مكرّراً في 4 مواضع وانحرفت النسخة المحلية فعلاً
    (19 عدم تطابق في name_en/name_ar لم تُكتشف).
    """
    import avax_desk.desks as desks
    from avax_desk.desks._binding import audit_implementations
    from avax_desk.desks.control import CONTROL_AGENTS
    from avax_desk.desks.knowledge import KNOWLEDGE_AGENTS
    from avax_desk.desks.memory import MEMORY_AGENTS
    from avax_desk.desks.orchestrator import DECISION_AGENTS
    from avax_desk.desks.validation import VALIDATION_AGENTS

    # الربط جرى عند الاستيراد
    binding = desks.ROSTER_BINDING
    assert binding.get("error") is None, f"فشل ربط الكشف: {binding.get('error')}"
    assert binding["count"] == 15, f"عدد الوكلاء المربوطين {binding['count']} لا 15"
    assert not binding["unregistered_classes"], \
        f"أصناف بلا كشف: {binding['unregistered_classes']}"

    # كل صنف يطابق الكشف حرفياً
    for cls in (*KNOWLEDGE_AGENTS, *VALIDATION_AGENTS, *CONTROL_AGENTS,
                *DECISION_AGENTS, *MEMORY_AGENTS):
        ref = ROSTER_BY_ID[str(cls.id)]
        assert cls.name_ar == ref.name_ar, f"[{cls.id}] name_ar انحرف عن الكشف"
        assert cls.name_en == ref.name_en, f"[{cls.id}] name_en انحرف عن الكشف"
        assert cls.file == ref.file, f"[{cls.id}] file انحرف عن الكشف"
        assert cls.layer == ref.layer, f"[{cls.id}] layer انحرف عن الكشف"
        assert cls.authority == ref.authority, f"[{cls.id}] authority انحرف عن الكشف"

    # تدقيق التنفيذ: لا وكيل في الكشف بلا صنف
    impl = audit_implementations()
    assert impl["ok"], (f"تدقيق التنفيذ فاشل: ناقص={impl['missing_implementations']} "
                        f"طبقة خاطئة={impl['wrong_layer']} زائد={impl['extra_implementations']}")
    assert impl["implemented_classes"] == 15


def test_audit_roster_checks_all_contractual_fields():
    """`audit_roster` كان يفحص layer/authority فقط فيُعلن اتساقاً كاذباً."""
    from avax_desk.registry import audit_roster
    audit = audit_roster()
    assert audit["ok"]
    for field in ("name_ar", "name_en", "file", "outputs"):
        assert field in audit["fields_checked"], f"الحقل {field} غير مفحوص"

    # وتقرير الاتساق يجمع المحورين
    from avax_desk.registry import consistency_report
    report = consistency_report()
    assert "ملفات الوكلاء" in report and "أصناف التنفيذ" in report


def test_external_anchor_detects_tail_truncation():
    """S1: اقتطاع الذيل كان غير مكشوف تماماً — المرساة الخارجية تكشفه."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "j.jsonl"
        store = JournalStore(p)
        for i in range(5):
            store.append({"i": i})
        assert store.verify_chain()["valid"], "سلسلة سليمة ظهرت مكسورة"
        assert (Path(tmp) / "anchor.json").exists(), "لم تُكتب المرساة"

        # اقتطاع الذيل: حذف آخر سجلين
        lines = p.read_text(encoding="utf-8").splitlines()
        p.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
        v = JournalStore(p).verify_chain()
        assert not v["valid"], "اقتطاع الذيل لم يُكتشف"
        assert v["tail_truncated"], "علم اقتطاع الذيل لم يُرفع"
        assert "اقتطاع" in v["broken"][0]["issue"]


def test_external_anchor_detects_full_rewrite():
    """إعادة كتابة الملف كاملاً بإعادة حساب الهاشات — كانت غير مكشوفة."""
    import copy as _copy
    from avax_desk.contracts import JournalRecord as JR

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "j.jsonl"
        store = JournalStore(p)
        for i in range(3):
            store.append({"i": i})

        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
        rows[1] = _copy.deepcopy(rows[1])
        rows[1]["payload"]["i"] = 999
        rebuilt, prev = [], "GENESIS"
        for r in rows:
            rec = JR(record_id=r["record_id"], sequence=r["sequence"],
                     payload=r["payload"], previous_hash=prev, timestamp=r["timestamp"])
            rec.seal()
            rebuilt.append(rec.to_dict())
            prev = rec.record_hash
        p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rebuilt) + "\n",
                     encoding="utf-8")

        v = JournalStore(p).verify_chain()
        assert not v["valid"], "إعادة الكتابة الكاملة لم تُكتشف بالمرساة"
        assert v["rewritten"] or v["tail_truncated"]


def test_journal_limits_are_documented_honestly():
    """لا يجوز أن يدّعي السجل حماية لا يملكها."""
    with tempfile.TemporaryDirectory() as tmp:
        store = JournalStore(Path(tmp) / "j.jsonl")
        assert "اقتطاع" in store._limits_text(), "حدود الحماية غير موثّقة"
        signed = JournalStore(Path(tmp) / "j2.jsonl", secret="k")
        assert "HMAC" in signed._limits_text()


def test_kelly_binding_is_disclosed_honestly():
    """
    رفع سقف كيلي إلى 0.30 لم يجعله مُلزِماً — وهذا يجب أن يكون **مُعلناً** لا مُخفى.
    (المدقّق رصد أن الإصلاح السابق كان سطحياً.)
    """
    analysis = RiskEngine.kelly_binding_analysis()
    eligible = [r for r in analysis["rows"] if r["eligible_for_entry"]]
    assert eligible, "لا صفوف مؤهلة في التحليل"
    # الحقيقة الحالية: كيلي لا يقيّد داخل النطاق المؤهل
    assert analysis["kelly_binds_in_eligible_range"] is False
    assert analysis["kelly_binds_only_below_min_confidence"] is True
    assert "لا يقيّد" in analysis["note"]
    # والجدول المرجعي يستخدم السقف نفسه المستخدم في evaluate
    table = RiskEngine.kelly_table([65])
    assert abs(table[0]["kelly_half_capped_pct"] - 10.417) < 0.01, \
        "سقف الجدول المرجعي لا يطابق سقف evaluate"


def test_composed_reduction_is_disclosed():
    """مضاعف المستوى × خصم الجودة يتضاعفان — يجب إعلان التركيب لا تركه مفاجئاً."""
    feats, snap = _features_and_snapshot()
    feats = dict(feats)
    feats["vol_regime"] = "extreme"          # ⇒ أصفر ×0.5
    cfg = DeskConfig(capital_usd=1_000_000.0)
    v = RiskEngine(cfg).evaluate(feats, snap, "bullish", confidence=85.0)
    lc = v.limits_checked
    assert lc["level_multiplier"] == 0.5
    assert lc["quality_haircut"] in (0.5, 1.0)
    assert lc["composed_multiplier"] == round(
        lc["level_multiplier"] * lc["quality_haircut"], 4)
    if lc["quality_haircut"] < 1.0:
        assert any("متراكب" in n for n in v.notes), \
            "التخفيضان المتراكبان لم يُعلنا"
        assert lc["composed_multiplier"] < 0.5, "التركيب لم يُطبَّق"


def test_veto_reason_sites_are_counted():
    """عدد مواقع أسباب النقض موثّق — يُرصد انحرافه."""
    import inspect
    from avax_desk.risk import engine as eng
    src = inspect.getsource(eng)
    count = src.count("veto_reasons.append")
    assert count >= 13, f"مواقع أسباب النقض {count} — أقل مما هو موثّق"


# ==========================================================================
# تشغيل بلا pytest
# ==========================================================================

def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed, failed = 0, []
    width = max(len(n) for n, _ in tests)
    print("═" * 78)
    print(f"  تشغيل {len(tests)} اختباراً لديسك أفالانش")
    print("═" * 78)
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  ✅ {name:<{width}}")
        except Exception as exc:                       # noqa: BLE001
            failed.append((name, exc))
            print(f"  ❌ {name:<{width}}  ← {type(exc).__name__}: {exc}")
    print("─" * 78)
    print(f"  نجح: {passed}/{len(tests)}   |   فشل: {len(failed)}")
    for name, exc in failed:
        print(f"    ❌ {name}: {exc}")
    print("═" * 78)
    return 0 if not failed else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")       # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    raise SystemExit(_run_all())
