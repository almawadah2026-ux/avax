"""
طبقة التحقق — الوكيلان 09 و 10.

وظيفتهما **الشك المنظم**. لا ينتجان فرضية سوقية، بل يفحصان فرضيات الآخرين
ويفنّدانها (المادة 4.3). غيابهما يعني ديسكاً يصدّق نفسه.
"""

from __future__ import annotations

from typing import Any

from .. import indicators as ind
from ..contracts import Authority, Layer, Strength
from ..law import ROSTER_BY_ID
from .base import AgentContext, BaseAgent


# ==========================================================================
# محرك تحقق مصغّر — اختبار حقيقي لا ادّعاء
# ==========================================================================

def capacity_analysis(adv_usd: float, daily_vol_fraction: float, spread_bps: float,
                      fee_bps: float, max_participation_pct: float = 5.0,
                      cost_budget_bps: float = 20.0) -> dict[str, Any]:
    """
    تحليل القدرة (Capacity) — المادة 4.1.

    السؤال: ما أكبر حجم يمكن تداوله قبل أن يلتهم أثر السوق الحافة؟

    النموذج (قانون الجذر التربيعي):
        التكلفة(Q) = رسوم + نصف السبريد + Y·σ·sqrt(Q/ADV)·10⁴   [نقطة أساس]

    نحلّ لـ Q عند سقف تكلفة معلن، ثم نقصّها بحد المشاركة الأقصى.
    """
    y = 0.5
    base_cost = fee_bps + spread_bps / 2.0
    if daily_vol_fraction <= 0 or adv_usd <= 0:
        return {"capacity_usd": 0.0, "reason": "بيانات سيولة أو تقلب غير صالحة"}

    allowed_impact = cost_budget_bps - base_cost
    if allowed_impact <= 0:
        return {
            "capacity_usd": 0.0,
            "base_cost_bps": round(base_cost, 3),
            "reason": f"التكلفة الأساسية ({base_cost:.2f} نقطة) تتجاوز ميزانية التكلفة",
        }

    impact_fraction = allowed_impact / 10_000.0
    ratio = (impact_fraction / (y * daily_vol_fraction)) ** 2      # Q / ADV
    q_impact = ratio * adv_usd
    q_participation = adv_usd * max_participation_pct / 100.0
    capacity = min(q_impact, q_participation)
    return {
        "capacity_usd": capacity,
        "binding": "market_impact" if q_impact <= q_participation else "participipation_limit",
        "impact_limited_usd": q_impact,
        "participation_limited_usd": q_participation,
        "base_cost_bps": round(base_cost, 3),
        "cost_budget_bps": cost_budget_bps,
    }


def lookahead_audit(closes: list[float], fast: int = 20, slow: int = 50) -> dict[str, Any]:
    """
    تدقيق تسرّب البيانات المستقبلية (Look-ahead Bias) — المادة 8.3.

    المنهج: نقارن **الإشارة التزايدية** (تُبنى من البادئة `closes[0..t]` فقط)
    بالإشارة **الدفعية** المحسوبة من السلسلة الكاملة عند الموضع t.

    ⚠️ **اختبار ذاتي إلزامي (Negative Control):** الاختبار السابق كان تحصيل حاصل —
    يقارن دالة سببية بدالة سببية، فينجح دائماً ولا يمكن أن يفشل. الآن يُختبر
    الكاشف نفسه على مُقدِّر **مُسرِّب عمداً**: إن لم يكشفه، فالأداة معطّلة
    ويُعاد `clean=False` مع سبب صريح. بلا هذا الاختبار الذاتي، «اجتياز» الفحص
    لا يعني شيئاً.
    """
    if len(closes) < slow + 10:
        return {"clean": False, "checked_points": 0,
                "reason": "عينة غير كافية للتدقيق (المادة 8.3)"}

    batch_fast = ind.ema_series(closes, fast)
    batch_slow = ind.ema_series(closes, slow)

    mismatches = 0
    checked = 0
    for i in range(slow + 5, len(closes), 5):
        checked += 1
        inc_fast = ind.ema_series(closes[: i + 1], fast)[-1]
        inc_slow = ind.ema_series(closes[: i + 1], slow)[-1]
        if abs(inc_fast - batch_fast[i]) > 1e-9 or abs(inc_slow - batch_slow[i]) > 1e-9:
            mismatches += 1

    # -- الاختبار الذاتي: مُقدِّر مُسرِّب عمداً (يستخدم نافذة مستقبلية) --
    def _leaky(series: list[float]) -> list[float]:
        out = []
        for i in range(len(series)):
            window = series[i: i + 5] or [series[-1]]
            out.append(sum(window) / len(window))
        return out

    leaky_batch = _leaky(closes)
    leaky_detected = 0
    for i in range(slow + 5, len(closes), 5):
        if abs(_leaky(closes[: i + 1])[-1] - leaky_batch[i]) > 1e-9:
            leaky_detected += 1
    self_test_ok = leaky_detected > 0

    clean = (mismatches == 0) and self_test_ok
    if not self_test_ok:
        note = "⛔ الأداة نفسها معطّلة: لم تكشف مُقدِّراً مُسرِّباً عمداً — لا قيمة لاجتيازها"
    elif mismatches == 0:
        note = "كل الإشارات سببية، والكاشف أثبت قدرته على الكشف (اختبار ذاتي ناجح)"
    else:
        note = f"⚠️ رُصد تسرّب في {mismatches} نقطة (خرق المادة 8.3)"

    return {
        "clean": clean,
        "checked_points": checked,
        "mismatches": mismatches,
        "self_test_passed": self_test_ok,
        "leak_detected_in_self_test": leaky_detected,
        "note": note,
    }


def mini_backtest(closes: list[float], fee_bps: float = 5.0, slippage_bps: float = 3.0,
                  fast: int = 20, slow: int = 50) -> dict[str, Any]:
    """
    اختبار تاريخي لإشارة **مركّبة** تحاكي مكوّنات الديسك السعرية، مع تكاليف كاملة.

    لماذا إشارة مركّبة لا EMA واحدة؟
        الديسك لا يتداول بـ EMA(20/50) بل بمزيج موزون من الاتجاه والزخم والعودة
        للمتوسط. اختبار قاعدة واحدة يقيس شيئاً آخر، ويُنتج حكماً غير ذي صلة.
        هنا نبني إشارة بنفس بنية الوكيلين 02 و03:

            S = 0.60·sign(EMA20 − EMA50) + 0.30·sign(Mom30) + 0.10·(−sign(Z30))

        هذا **تقريب معلن** لا مطابقة كاملة — الدستور يمنع ادّعاء غير صحيح (المادة 3.3).

    التكاليف: رسوم + انزلاق تُخصم عند كل تغيّر في الإشارة (Turnover).
    """
    n = len(closes)
    if n < slow + 60:
        return {"ok": False, "reason": f"عينة غير كافية ({n} نقطة، المطلوب {slow+60})"}

    ef = ind.ema_series(closes, fast)
    es = ind.ema_series(closes, slow)

    positions: list[int] = []
    for i in range(n):
        if i < slow + 5:
            positions.append(0)
            continue
        s = 0.0
        s += 0.60 * (1.0 if ef[i] >= es[i] else -1.0)
        base = closes[i - 30]
        if base > 0:
            s += 0.30 * (1.0 if closes[i] / base - 1.0 > 0 else -1.0)
        window = closes[i - 30: i + 1]
        sd = ind.stdev(window)
        if sd > 0:
            z = (closes[i] - ind.mean(window)) / sd
            s += 0.10 * (-1.0 if z > 0 else 1.0)
        positions.append(1 if s > 0.15 else (-1 if s < -0.15 else 0))

    cost_rate = (fee_bps + slippage_bps) / 10_000.0

    rets: list[float] = []
    trades = 0
    for i in range(slow + 6, n):
        prev = closes[i - 1]
        if prev <= 0:
            continue
        r = closes[i] / prev - 1.0
        p = positions[i - 1]
        turnover_cost = cost_rate * abs(positions[i - 1] - positions[i - 2])
        if positions[i - 1] != positions[i - 2]:
            trades += 1
        rets.append(p * r - turnover_cost)

    if len(rets) < 60:
        return {"ok": False, "reason": "عدد عوائد غير كافٍ"}

    split = int(len(rets) * 0.70)
    is_r, oos_r = rets[:split], rets[split:]
    is_sharpe = ind.annualized_sharpe(is_r)
    oos_sharpe = ind.annualized_sharpe(oos_r)

    # عدد المحاولات: كل وكيل يحاول إيجاد نمط ⇒ تصحيح للمقارنات المتعددة
    n_trials = max(2, 8 * 3)
    # ⚠️ DSR يعمل على شارب **لكل فترة** لا المُسنَّن سنوياً (تصحيح وحدات).
    annualization = 365 ** 0.5
    dsr = ind.deflated_sharpe_ratio(
        sharpe_obs=is_sharpe / annualization,
        n_trials=n_trials,
        n_obs=len(is_r),
        skew=0.0,
        kurtosis=4.0,       # الكريبتو ذو ذيول سمينة
    )
    sharpe_decay = ind.sharpe_decay_ratio(is_sharpe, oos_sharpe)

    equity, eq = [], 1.0
    for r in rets:
        eq *= (1 + r)
        equity.append(eq)
    dd = ind.max_drawdown(equity)

    # المادة 4.2 — «أي نتيجة بربح يتجاوز 3 أضعاف المعيار المرجعي تُصنَّف مشتبهاً بها».
    # المعيار المرجعي = الشراء والاحتفاظ (Buy & Hold) على نفس النافذة.
    # كان الحقل `excess_vs_benchmark` مُعلناً في `require_validation` ولا يُحسَب أبداً،
    # فكانت المادة 4.2 بلا فرض.
    bh_start = closes[slow + 6] if len(closes) > slow + 6 else closes[0]
    bh_return = (closes[-1] / bh_start - 1.0) if bh_start > 0 else 0.0
    strategy_return = eq - 1.0
    if abs(bh_return) > 1e-6:
        excess = strategy_return / bh_return if bh_return > 0 else 0.0
    else:
        excess = float("inf") if strategy_return > 0.05 else 0.0

    return {
        "ok": True,
        "signal": "composite(EMA20/50 60% + Mom30 30% + Z30 10%)",
        "n_obs": len(rets),
        "n_trials": n_trials,
        "trades": trades,
        "is_sharpe": round(is_sharpe, 4),
        "oos_sharpe": round(oos_sharpe, 4),
        "benchmark_buy_hold_pct": round(bh_return * 100.0, 3),
        "strategy_return_pct": round(strategy_return * 100.0, 3),
        "excess_vs_benchmark": (round(excess, 4) if excess != float("inf") else 99.0),
        "sharpe_decay": round(sharpe_decay, 4),
        "deflated_sharpe": round(dsr, 4),
        "dsr_units": "شارب لكل فترة (مُحوَّل من السنوي بالقسمة على √365)",
        "max_dd_pct": round(dd["max_dd_pct"], 3),
        "total_return_pct": round((eq - 1) * 100.0, 3),
        "costs_modeled": {"fee_bps": fee_bps, "slippage_bps": slippage_bps},
        "caveat": ("تقريب معلن لمكوّنات الديسك السعرية — لا مطابقة كاملة (المادة 3.3). "
                   "`sharpe_decay` نسبة انحلال بسيطة وليست PBO. "
                   "DSR تقديري: بلا عامل تباين المحاولات sqrt(V[SR_n])."),
    }


# ==========================================================================
# 09 — وكيل التحقق والاختبار
# ==========================================================================

class ValidationAgent(BaseAgent):
    """
    لا ينتج اتجاهاً. ينتج **حكماً على جودة الإشارة** ومُعامِلات خصم للوكلاء.

    سلطته سلبية: يستطيع إبطال نتيجة، لا إصدار توصية (المادة 1.1).
    """

    id, name_ar, name_en = "09", "وكيل التحقق والاختبار", "Validation & Backtest Agent"
    layer, authority, domain = Layer.VALIDATION, Authority.ADVISORY, "validation"
    horizon = "—"
    file = "agents/09-validation-backtest.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        s = ctx.snapshot
        price = f["price"]
        knowledge = ctx.knowledge_opinions()

        bt = mini_backtest(
            s.closes,
            fee_bps=s.taker_fee_bps * 2,
            slippage_bps=ind.clamp(f["spread_bps"] / 2.0, 1.0, 15.0),
        )

        # -- خصم الوكلاء بحسب قوة أدلتهم --------------------------------
        discounts: dict[str, float] = {}
        heuristic_agents: list[str] = []
        for op in knowledge:
            tier = op.best_tier
            discount = 1.0
            if tier >= 5:
                discount = 0.55          # معنويات: طبقة ضعيفة
            elif tier == 4:
                discount = 0.75          # فني بحت: وصفي لا تنبؤي
            if len(op.evidence) < 3:
                discount *= 0.85         # دليل ناقص
            if op.metrics.get("note", "").startswith("بيانات لحظية"):
                discount *= 0.80         # بيانات سريعة التلاشي
            discounts[op.agent_id] = round(discount, 3)
            if tier >= 4:
                heuristic_agents.append(op.agent_id)

        n = bt.get("n_obs", 0)
        sample_ok = n >= 200
        dsr = float(bt.get("deflated_sharpe", 0.0))
        decay = float(bt.get("sharpe_decay", 1.0))

        # -- تدقيق التسرّب المستقبلي (المادة 8.3) -------------------------
        la = lookahead_audit(s.closes)

        # -- تحليل القدرة الحقيقي (المادة 4.1) ----------------------------
        daily_vol_fraction = max(1e-6, f["vol_30d_ann_pct"] / 100.0 / (365 ** 0.5))
        cap = capacity_analysis(
            adv_usd=float(s.avg_volume_30d_usd or s.volume_24h_usd or 0.0),
            daily_vol_fraction=daily_vol_fraction,
            spread_bps=float(f["spread_bps"]),
            fee_bps=float(s.taker_fee_bps),
            max_participation_pct=ctx.config.limits.max_market_participation_pct,
        )
        intended_position = ctx.config.capital_usd * ctx.config.limits.max_position_pct / 100.0
        capacity_ok = cap.get("capacity_usd", 0.0) >= intended_position

        # -- الحكم النهائي على الإشارة الإجمالية --------------------------
        validated = bool(
            bt.get("ok")
            and sample_ok
            and bt.get("oos_sharpe", -1) > 0
            and dsr > 0.60
            and decay < 0.50
            and la.get("clean")
        )

        evidence = [
            self.ev(ctx, f"عدد نقاط العينة {n} (الحد الأدنى المقبول 200)", "backtest/sample-size",
                    "derived", Strength.HIGH.value, float(n)),
            self.ev(ctx, f"نسبة شارب داخل العينة {bt.get('is_sharpe')} مقابل خارجها {bt.get('oos_sharpe')}",
                    "backtest/ema-20-50-walkforward", "derived", Strength.HIGH.value, bt.get("oos_sharpe")),
            self.ev(ctx, f"Deflated Sharpe Ratio = {dsr:.3f} (شارب لكل فترة، "
                         f"{bt.get('n_trials')} محاولة) — تقديري بلا عامل تباين المحاولات",
                    "backtest/deflated-sharpe", "derived", Strength.HIGH.value, dsr),
            self.ev(ctx, f"انحلال شارب من داخل العينة إلى خارجها = {decay:.3f} "
                         f"(نسبة انحلال بسيطة — **وليست PBO**)",
                    "backtest/sharpe-decay", "derived", Strength.HIGH.value, decay),
            self.ev(ctx, f"التكاليف المُنمذجة: رسوم {bt.get('costs_modeled')}", "backtest/cost-model",
                    "derived", Strength.HIGH.value, None),
            self.ev(ctx, f"وكلاء يعتمدون على أدلة من الطبقة 4 أو أضعف: {', '.join(heuristic_agents) or 'لا أحد'}",
                    "audit/evidence-tier-scan", "derived", Strength.HIGH.value, None),
            self.ev(ctx, f"تحليل القدرة: أقصى حجم قابل للتداول ${cap.get('capacity_usd', 0)/1e6:.2f}M "
                         f"(القيد: {cap.get('binding', '—')}) مقابل مركز مقصود "
                         f"${intended_position/1e6:.2f}M ⇒ {'كافٍ' if capacity_ok else 'غير كافٍ'}",
                    "validation/capacity-analysis", "derived", Strength.HIGH.value,
                    cap.get("capacity_usd")),
            self.ev(ctx, f"تدقيق التسرّب المستقبلي (المادة 8.3): "
                         f"{la.get('checked_points', 0)} نقطة مفحوصة، "
                         f"{la.get('mismatches', 0)} حالة تسرّب ⇒ "
                         f"{'سببي بالكامل' if la.get('clean') else 'مشكوك فيه'}",
                    "validation/lookahead-audit", "derived", Strength.HIGH.value, None),
            self.ev(ctx, f"أقصى تراجع في الاختبار {bt.get('max_dd_pct')}% بإجمالي عائد "
                         f"{bt.get('total_return_pct')}% و{bt.get('trades')} صفقة",
                    "backtest/equity-curve", "derived", Strength.MEDIUM.value, bt.get("max_dd_pct")),
        ]

        thesis = (
            f"الإشارة الإجمالية {'اجتازت' if validated else 'لم تجتز'} قانون التحقق (المادة 4.1): "
            f"DSR={dsr:.3f}، انحلال شارب={decay:.3f}، شارب خارج العينة={bt.get('oos_sharpe')}، "
            f"عينة {n} نقطة. " + ("" if sample_ok else "العينة دون الحد الأدنى.")
        )
        invalidation = (
            "يُبطل هذا الحكم إذا تغيّر حجم العينة أو نافذة الاختبار، أو إذا تبين أن قاعدة "
            "EMA(20/50) غير ممثلة لطبيعة الإشارات المستخدمة فعلياً — وعندها يلزم اختبار مخصص "
            "لكل إشارة على حدة."
        )
        dissent = (
            "أقوى ما يخالف هذا الحكم: قاعدة EMA الوحيدة لا تمثّل تعقيد القرار المجمّع، فقد يجتاز "
            "الاختبار البسيط وتفشل الإشارة المركّبة (أو العكس). كذلك Walk-forward بنافذة واحدة "
            "ليس دليلاً قاطعاً، و90 يوماً خارج العينة قد لا تكفي لدورة سوق كاملة."
        )
        notes = []
        if not sample_ok:
            notes.append(f"⛔ عينة {n} دون الحد الأدنى 200 — كل الإشارات الإحصائية مشكوك فيها")
        if bt.get("sharpe_decay", 0) > 0.6:
            notes.append(f"⛔ انهيار حاد في شارب من داخل العينة إلى خارجها "
                         f"({bt.get('sharpe_decay')}) — مؤشر كلاسيكي على Overfitting")
        if dsr < 0.60:
            notes.append(f"⚠️ DSR {dsr:.3f} دون 0.60 — لا يمكن تمييز الأداء عن الصدفة")
        if decay > 0.5:
            notes.append(f"⚠️ انحلال شارب {decay:.3f} — الأداء خارج العينة يهبط بشدة "
                         f"(مؤشر على إفراط في التوفيق، وليس مقياس PBO)")
        if not la.get("self_test_passed"):
            notes.append("⛔ الاختبار الذاتي لتدقيق التسرّب فشل — لا قيمة لاجتيازه")
        if not capacity_ok:
            notes.append(f"⚠️ حجم المركز المقصود يتجاوز قدرة السوق الاستيعابية "
                         f"(${cap.get('capacity_usd', 0)/1e6:.2f}M)")
        if not la.get("clean"):
            notes.append("⛔ اختبار التسرّب المستقبلي فشل — الإشارة غير سببية (المادة 8.3)")
        notes.append("ℹ️ هذا اختبار الحد الأدنى — لا يُغني عن اختبار مخصص لكل إشارة")

        return self.make(
            ctx,
            score=0.0,
            thesis=thesis,
            evidence=evidence,
            invalidation=invalidation,
            dissent=dissent,
            metrics={
                "validated": validated,
                "oos_tested": bool(bt.get("ok")),
                "costs_modeled": bool(bt.get("ok")),
                "capacity_checked": bool(cap.get("capacity_usd", 0.0) > 0),
                "overfitting_checked": bool(bt.get("ok")),
                "lookahead_clean": bool(la.get("clean")),
                "backtest": bt,
                "capacity": cap,
                "capacity_ok": capacity_ok,
                "lookahead_audit": la,
                "agent_discounts": discounts,
                "heuristic_agents": heuristic_agents,
            },
            notes=notes,
        )


# ==========================================================================
# 10 — محامي الشيطان
# ==========================================================================

class RedTeamAgent(BaseAgent):
    """
    لا يقدّم فرضية سوقية (المادة 1.3). مهمته الوحيدة: بناء أقوى حجة ضد الإجماع.

    إن لم يجد حجة مضادة، عليه تصريح مكتوب بذلك مع تبرير (المادة 4.3).
    """

    id, name_ar, name_en = "10", "محامي الشيطان", "Red Team Agent"
    layer, authority, domain = Layer.VALIDATION, Authority.ADVISORY, "falsification"
    horizon = "—"
    file = "agents/10-red-team.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        knowledge = [o for o in ctx.knowledge_opinions() if not o.abstain]
        if not knowledge:
            return AgentOpinion.abstain_opinion(
                self.id, self.name_ar, "لا آراء معرفية لفنّدها"
            )

        bulls = [o for o in knowledge if o.direction == "bullish"]
        bears = [o for o in knowledge if o.direction == "bearish"]
        consensus_dir = "bullish" if len(bulls) >= len(bears) else "bearish"
        consensus_side = bulls if consensus_dir == "bullish" else bears
        minority_side = bears if consensus_dir == "bullish" else bulls

        # أقوى دليل في صف الأقلية = نقطة الهجوم
        attack_evidence: list[tuple[str, str, str]] = []
        for op in minority_side:
            for e in op.evidence:
                attack_evidence.append((op.agent_id, e.claim, e.tier_label))
        attack_evidence.sort(key=lambda t: t[2])

        # نقاط الضعف البنيوية في الإجماع
        weaknesses: list[str] = []
        tiers = [op.best_tier for op in consensus_side]
        if tiers and min(tiers) >= 4:
            weaknesses.append(
                "كل الأدلة المؤيدة للإجماع من الطبقة 4 أو أضعف (فنية/معنويات) — "
                "لا يوجد دليل أونشين أو سوقي مباشر يسندها (المادة 3.1)"
            )
        if len(consensus_side) >= 5:
            weaknesses.append(
                f"الإجماع يضم {len(consensus_side)} وكيلاً من أصل {len(knowledge)} — "
                "قرب من الإجماع التام الذي يصنّفه الدستور إشارة إنذار لا ثقة (المادة 4.4)"
            )
        stale = [e.claim for op in consensus_side for e in op.evidence if e.staleness(24.0)]
        if stale:
            weaknesses.append(f"{len(stale)} دليل مؤيد قديم تجاوز 24 ساعة — قيمته التحليلية منخفضة")

        structural = self._structural_risks(ctx)
        weaknesses.extend(structural)

        if not weaknesses:
            weaknesses.append(
                "لم يُرصد ضعف بنيوي في الإجماع — تصريح صريح مطلوب بذلك (المادة 4.3). "
                "هذا لا يعني صحة الرأي، بل أن الأدلة متماسكة نسبياً."
            )

        score = -1.0 if consensus_dir == "bullish" else 1.0
        score *= 0.45  # محامي الشيطان لا يعلن ثقة عالية — دوره إثارة الشك لا الدخول

        evidence = [
            self.ev(ctx, f"الإجماع الحالي {consensus_dir} بـ {len(consensus_side)} وكيل، "
                         f"والأقلية {len(minority_side)} وكيل",
                    "audit/opinion-census", "derived", Strength.HIGH.value, float(len(consensus_side))),
        ]
        for aid, claim, tier_label in attack_evidence[:4]:
            evidence.append(self.ev(ctx, f"دليل معارض من الوكيل {aid}: {claim} ({tier_label})",
                                    "redteam/cross-examination", "derived", Strength.MEDIUM.value, None))
        for i, w in enumerate(weaknesses[:4], 1):
            evidence.append(self.ev(ctx, f"نقطة ضعف {i}: {w}", "redteam/structural-scan",
                                    "derived", Strength.HIGH.value, None))

        pre_mortem = self._pre_mortem(ctx)
        thesis = (
            f"الحجة المضادة للإجماع {consensus_dir}: {weaknesses[0][:150]}"
        )
        invalidation = (
            f"يُبطل هذا التفنيد إذا ظهر دليل من الطبقة 1 أو 2 (أونشين أو سوق متعدد المنصات) "
            f"يؤكد الاتجاه {consensus_dir} بشكل مستقل عن السعر، أو إذا انضم وكيلان على الأقل "
            f"من الأقلية إلى الإجماع بدليل جديد."
        )
        dissent = (
            "أقوى ما يخالف رأيي: دوري هو الشك، وأقوم بتحليل غير متماثل — أنا لا أوازن بين "
            "الحجتين بل أبني واحدة. لهذا لا يجوز استخدام رأيي وحده لإلغاء قرار، بل لإجبار "
            "المنسّق على تبرير قراره صراحةً."
        )

        return self.make(
            ctx,
            score=score,
            thesis=thesis,
            evidence=evidence,
            invalidation=invalidation,
            dissent=dissent,
            metrics={
                "consensus_direction": consensus_dir,
                "consensus_count": len(consensus_side),
                "minority_count": len(minority_side),
                "weaknesses": weaknesses,
                "pre_mortem": pre_mortem,
                "counter_thesis": (
                    f"إذا كان الإجماع {consensus_dir}، فالسيناريو المضاد هو "
                    f"{'هبوط حاد' if consensus_dir == 'bullish' else 'صعود مفاجئ'} "
                    f"مدفوعاً بـ: {pre_mortem[0] if pre_mortem else 'تغيّر في السيولة'}"
                ),
            },
            dead_zone=0.01,
            notes=["ℹ️ رأي محامي الشيطان يُسجَّل إلزامياً في القرار (المادة 6)"],
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _structural_risks(ctx: AgentContext) -> list[str]:
        """سيناريوهات فشل بنيوية خاصة بمنظومة أفالانش."""
        s, f = ctx.snapshot, ctx.features
        risks: list[str] = []
        if s.staking_ratio_pct > 65:
            risks.append(
                f"نسبة الاستيكينج {s.staking_ratio_pct:.1f}% مرتفعة — أي موجة فك استيكينج "
                "جماعية ستضخ معروضاً كبيراً دفعة واحدة (فترة فك الاستيكينج قيد زمني)"
            )
        if s.btc_corr_30d > 0.80:
            risks.append(
                f"الارتباط بـ BTC {s.btc_corr_30d:.2f} — AVAX لا يتحرك باستقلال؛ "
                "أي صدمة في BTC تُلغي التحليل الخاص بأفالانش"
            )
        if s.unlock_pct_next_30d > 3.0:
            risks.append(f"فك قفل {s.unlock_pct_next_30d:.2f}% خلال 30 يوماً — ضغط بيعي مبرمج ومعروف مسبقاً")
        if f["vol_regime"] in ("high", "extreme"):
            risks.append(f"نظام تقلب {f['vol_regime']} — الأوقاف القريبة ستُضرب بسهولة (Stop Hunting)")
        if s.tvl_usd < 500e6:
            risks.append(f"TVL {s.tvl_usd/1e6:.0f}M$ — قاعدة سيولة رقيقة نسبياً، خطر خروج جماعي")
        if s.venues < 5:
            risks.append(f"{s.venues} منصات فقط — خطر اعتماد على منصة واحدة (مخاطرة طرف مقابل)")
        if s.funding_rate_8h > 0.0004:
            risks.append(f"تمويل موجب مرتفع ({s.funding_rate_8h*100:.4f}%/8h) — تكلفة حمل المراكز الشرائية")
        return risks

    @staticmethod
    def _pre_mortem(ctx: AgentContext) -> list[str]:
        """تحليل الفشل المسبق: لو خسرنا، فلماذا غالباً؟"""
        s, f = ctx.snapshot, ctx.features
        return [
            f"تصفية جماعية (Cascade) نتيجة تراكم مراكز مرفوعة، خصوصاً مع تمويل {s.funding_rate_8h*100:+.4f}%",
            f"خروج سيولة من الجسور وسحبها من C-Chain (صافي الجسور حالياً {s.bridge_netflow_7d_usd/1e6:+.1f}M$)",
            "صدمة ماكرو (تغيّر مفاجئ في العائد الحقيقي أو الدولار) تُلغي الإشارة الفنية تماماً",
            f"اتساع السبريد وانعدام العمق عند التقلب — التكلفة تلتهم الحافة (سبريد حالي {f['spread_bps']:.1f} نقطة)",
            "فشل تقني/أمني (توقف شبكة فرعية أو اختراق جسر) لا يظهر في أي مؤشر سعري مسبق",
        ]


VALIDATION_AGENTS: tuple[type[BaseAgent], ...] = (ValidationAgent, RedTeamAgent)
