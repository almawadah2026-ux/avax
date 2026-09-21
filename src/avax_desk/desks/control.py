"""
طبقة الضبط — الوكلاء 11 و 12 و 13.

هنا تُمارَس السلطة السلبية: **المنع**. لا أحد في هذه الطبقة يقرر ماذا نتداول،
لكن كل واحد منهم يستطيع إيقاف ما قرره غيره.
"""

from __future__ import annotations

import math
from typing import Any

from .. import indicators as ind
from ..contracts import (
    Action,
    AgentOpinion,
    Authority,
    ComplianceReport,
    Direction,
    ExecutionPlan,
    Layer,
    RiskLevel,
    Strength,
)
from ..law import ROSTER_BY_ID, Violation
from ..risk.engine import RiskEngine
from .base import AgentContext, BaseAgent


# ==========================================================================
# 11 — وكيل المخاطر
# ==========================================================================

class RiskManagerAgent(BaseAgent):
    """
    صاحب حق النقض (المادة 5.1).

    محرّم عليه تقديم فرضية سوقية (المادة 1.3). إن فعل، فقد استقلاليته.
    """

    id, name_ar, name_en = "11", "وكيل المخاطر", "Risk Manager Agent"
    layer, authority, domain = Layer.CONTROL, Authority.VETO, "risk"
    horizon = "—"
    file = "agents/11-risk-manager.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        engine = RiskEngine(ctx.config)
        ctx.shared["risk_engine"] = engine

        proposal = ctx.shared.get("proposal") or {}
        direction = proposal.get("direction", "neutral")
        confidence = float(proposal.get("confidence", 0.0))
        validation = ctx.shared.get("validation", {})
        compliance = ctx.shared.get("compliance")

        verdict = engine.evaluate(
            features=ctx.features,
            snapshot=ctx.snapshot,
            direction=direction,
            confidence=confidence,
            compliance_ok=True if compliance is None else bool(compliance.compliant),
            compliance_notes=[] if compliance is None else list(compliance.notes),
            strategy_metrics={
                "validated": bool(validation.get("validated", False)),
                "oos_tested": bool(validation.get("oos_tested", False)),
                "costs_modeled": bool(validation.get("costs_modeled", False)),
                "capacity_checked": bool(validation.get("capacity_checked", False)),
                "overfitting_checked": bool(validation.get("overfitting_checked", False)),
            },
        )
        ctx.shared["risk_verdict"] = verdict

        # المادة 5.4 — «عند تجاوز حد الخسارة اليومية، يتوقف الديسك آلياً لبقية اليوم».
        # كان `DeskConfig.halt()` معرّفاً وبلا مستدعٍ: الإيقاف يقع ضمناً بالنقض لا فعلاً.
        if verdict.risk_level == RiskLevel.RED.value and not ctx.config.halted:
            ctx.config.halt(
                f"خسارة يومية {ctx.config.daily_pnl_pct:.2f}% / تراجع "
                f"{ctx.config.current_drawdown_pct:.2f}% — المادة 5.4"
            )

        stress = engine.stress_test(ctx.features, verdict.computed_size_usd)

        evidence = [
            self.ev(ctx, f"مستوى الإنذار {verdict.risk_level} — خسارة يومية "
                         f"{ctx.config.daily_pnl_pct:.2f}% وتراجع {ctx.config.current_drawdown_pct:.2f}%",
                    "risk/limit-monitor", "derived", Strength.HIGH.value, ctx.config.daily_pnl_pct),
            self.ev(ctx, f"حجم المركز المحسوب ${verdict.computed_size_usd:,.0f} "
                         f"(المعتمد ${verdict.position_size_usd:,.0f}) — القيد الملزم: "
                         f"{verdict.limits_checked.get('binding_constraint')}",
                    "risk/position-sizing", "derived", Strength.HIGH.value, verdict.computed_size_usd),
            self.ev(ctx, f"احتمال النجاح المستخدم {verdict.limits_checked.get('win_probability_used')} "
                         f"بمعدل ربح/خسارة {verdict.limits_checked.get('reward_risk_used')} "
                         f"(كيلي مقيد بنصف القيمة)",
                    "risk/kelly-fractional", "derived", Strength.HIGH.value,
                    verdict.limits_checked.get("win_probability_used")),
            self.ev(ctx, f"وقف الخسارة عند {verdict.stop_loss_pct:.2f}% من سعر الدخول "
                         f"(مضاعف ATR {ctx.config.limits.atr_stop_multiple})",
                    "risk/atr-stop", "derived", Strength.HIGH.value, verdict.stop_loss_pct),
            self.ev(ctx, f"اختبار الضغط: أسوأ سيناريو تاريخي {stress['scenario_var95']:,.0f}$، "
                         f"وسيناريو انهيار 40% {stress['scenario_flash_crash_40pct']:,.0f}$",
                    "risk/stress-test", "derived", Strength.MEDIUM.value,
                    stress["scenario_flash_crash_40pct"]),
            self.ev(ctx, f"المخاطرة الفعلية لكل صفقة {verdict.risk_per_trade_pct:.3f}% "
                         f"(الحد {ctx.config.limits.max_risk_per_trade_pct}%)",
                    "risk/trade-risk", "derived", Strength.HIGH.value, verdict.risk_per_trade_pct),
        ]

        if verdict.veto:
            thesis = "🚫 **نقض** — " + "؛ ".join(verdict.veto_reasons[:3])
            direction_out = Direction.NEUTRAL.value
            score = 0.0
        else:
            thesis = (
                f"✅ موافقة مشروطة: حجم ${verdict.position_size_usd:,.0f} "
                f"({verdict.max_position_pct:.2f}%) بوقف {verdict.stop_loss_pct:.2f}% "
                f"ومخاطرة {verdict.risk_per_trade_pct:.3f}% لكل صفقة."
            )
            direction_out = Direction.NEUTRAL.value   # المخاطر لا يعلن اتجاهاً
            score = 0.0

        invalidation = (
            "يُبطل هذا الحكم (ويصبح النقض إلزامياً) إذا: تجاوزت الخسارة اليومية "
            f"{ctx.config.limits.max_daily_loss_pct}%، أو تجاوز التراجع "
            f"{ctx.config.limits.max_drawdown_pct}%، أو اتسع السبريد فوق 25 نقطة أساس، "
            "أو هبطت سيولة السوق دون قدرة استيعاب المركز."
        )
        dissent = (
            "أقوى ما يخالف هذا الحكم: نماذج المخاطرة كلها مبنية على توزيعات تاريخية، "
            "والأصول الرقمية تُنتج أحداثاً خارج أي توزيع مُقدَّر (Black Swans). "
            "كل الأرقام هنا **تقديرات لا ضمانات**، وأي انهيار جسري أو توقف منصة يتجاوز "
            "كل ما يحسبه هذا المحرك."
        )

        notes = list(verdict.notes)
        if verdict.veto:
            notes.insert(0, "⛔ النقض نافذ ولا يجوز تجاوزه (المادة 5.1)")
        notes.append(f"ℹ️ مرجع دستوري: المادة 5 (سيادة المخاطر) والمواد 5.3/5.4/5.5")

        op = self.make(
            ctx, score, thesis, evidence, invalidation, dissent,
            metrics={
                "veto": verdict.veto,
                "approved": verdict.approved,
                "risk_level": verdict.risk_level,
                "position_size_usd": verdict.position_size_usd,
                "stop_loss_pct": verdict.stop_loss_pct,
                "risk_per_trade_pct": verdict.risk_per_trade_pct,
                "binding_constraint": verdict.limits_checked.get("binding_constraint"),
                "stress_test": stress,
                "veto_reasons": verdict.veto_reasons,
                # ملاحظة: لا يُدرج أي حقل "market_thesis" — المادة 1.3
            },
            dead_zone=1.0,
            notes=notes,
        )
        op.direction = direction_out
        op.confidence = 95.0 if verdict.veto else 80.0   # ثقة في الحكم المخاطري لا في السوق
        return op


# ==========================================================================
# 12 — وكيل التنفيذ
# ==========================================================================

class ExecutionAgent(BaseAgent):
    """
    يخطط **ورقياً فقط**. لا يرسل أي أمر (المادة 0.2).
    """

    id, name_ar, name_en = "12", "وكيل التنفيذ", "Execution Agent"
    layer, authority, domain = Layer.CONTROL, Authority.ADVISORY, "execution"
    horizon = "تنفيذي"
    file = "agents/12-execution.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        s = ctx.snapshot
        f = ctx.features
        verdict = ctx.shared.get("risk_verdict")
        notional = float(getattr(verdict, "position_size_usd", 0.0)) if verdict else 0.0

        adv = max(1.0, s.avg_volume_30d_usd or s.volume_24h_usd)
        max_part = ctx.config.limits.max_market_participation_pct
        spread = f["spread_bps"]
        daily_vol = max(0.002, f["vol_30d_ann_pct"] / 100.0 / math.sqrt(365))

        if notional <= 0:
            plan = ExecutionPlan(method="لا تنفيذ", slices=0, participation_pct=0.0,
                                 venue_notes=["لا مركز معتمد من المخاطر — لا خطة تنفيذ"])
            return self.make(
                ctx, 0.0,
                "لا خطة تنفيذ: لا يوجد حجم معتمد من وكيل المخاطر.",
                [self.ev(ctx, "حجم المركز المعتمد = 0", "risk/verdict", "derived", Strength.HIGH.value, 0.0)],
                "يُبطل هذا إذا اعتمد وكيل المخاطر حجماً موجباً.",
                "لا خلاف — غياب الحجم يستلزم غياب الخطة.",
                metrics={"plan": plan.to_dict()}, dead_zone=1.0,
                notes=["ℹ️ التنفيذ تابع للمخاطر لا مستقل عنها"],
            )

        # كم يوماً نحتاج بمشاركة قصوى مسموحة؟
        days_needed = notional / max(1.0, adv * max_part / 100.0)
        days_needed = ind.clamp(days_needed, 0.25, 20.0)
        slices = int(ind.clamp(math.ceil(days_needed * 8), 2, 80))

        participation = ind.clamp(notional / max(1.0, adv * days_needed) * 100.0, 0.01, max_part)

        # أثر السوق بقانون الجذر التربيعي + نصف السبريد
        slice_notional = notional / slices
        impact = ind.market_impact_sqrt(slice_notional, adv, daily_vol) * 10_000.0
        # تحويل الأثر اليومي إلى أفق التنفيذ
        impact_total_bps = impact * math.sqrt(days_needed)
        slippage_bps = spread / 2.0 + impact_total_bps
        fee_bps = s.taker_fee_bps if days_needed < 2 else s.maker_fee_bps
        total_cost_usd = notional * (slippage_bps + fee_bps) / 10_000.0

        method = "TWAP" if days_needed <= 1.0 else ("VWAP" if days_needed <= 5 else "POV")
        schedule = []
        for i in range(1, min(slices, 12) + 1):
            schedule.append({
                "slice": i,
                "target_notional_usd": round(slice_notional, 2),
                "participation_pct": round(participation, 3),
                "window": f"نافذة {i}/{min(slices,12)}",
            })

        venue_notes = [
            f"التجزؤ على {s.venues} منصة لتقليل الأثر وإخفاء النية",
            "تفضيل أوامر Limit سلبية (Maker) عند التقلب المنخفض لتقليل الرسوم",
            f"حد الانزلاق المقبول: {max(5.0, spread*3):.1f} نقطة أساس لكل شريحة",
            "على C-Chain: ضبط Slippage Tolerance ومراقبة MEV/Sandwich قبل أي مبادلة DEX",
            "تجنّب التنفيذ في أول/آخر دقائق من جلسات السيولة العميقة وأثناء إعلانات البيانات الكلية",
            "⚠️ خطة نظرية فقط — لا إرسال أوامر (المادة 0.2)",
        ]

        plan = ExecutionPlan(
            method=method,
            slices=slices,
            participation_pct=round(participation, 3),
            expected_slippage_bps=round(slippage_bps, 2),
            expected_cost_usd=round(total_cost_usd, 2),
            schedule=schedule,
            venue_notes=venue_notes,
        )
        ctx.shared["execution_plan"] = plan

        evidence = [
            self.ev(ctx, f"حجم التنفيذ ${notional:,.0f} = {notional/adv*100:.3f}% من متوسط الحجم اليومي "
                         f"(${adv/1e6:,.1f}M)", "execution/adv-analysis", "derived", Strength.HIGH.value, notional),
            self.ev(ctx, f"مدة التنفيذ المقدّرة {days_needed:.2f} يوم بمشاركة {participation:.2f}% "
                         f"في {slices} شريحة", "execution/schedule", "derived", Strength.HIGH.value, days_needed),
            self.ev(ctx, f"الانزلاق المتوقع {slippage_bps:.2f} نقطة أساس "
                         f"(نصف السبريد {spread/2:.2f} + أثر السوق {impact_total_bps:.2f})",
                    "execution/slippage-model", "derived", Strength.MEDIUM.value, slippage_bps),
            self.ev(ctx, f"التكلفة الإجمالية المتوقعة ${total_cost_usd:,.2f} "
                         f"({(slippage_bps+fee_bps):.2f} نقطة أساس)",
                    "execution/tca-forecast", "derived", Strength.MEDIUM.value, total_cost_usd),
            self.ev(ctx, f"الخوارزمية المختارة {method} — مناسبة لأفق {days_needed:.2f} يوم",
                    "execution/algorithm-selection", "derived", Strength.MEDIUM.value, None),
        ]

        cost_pct_of_notional = ind.safe_div(total_cost_usd, notional) * 100.0
        thesis = (
            f"خطة تنفيذ {method} على {days_needed:.2f} يوم، {slices} شريحة، بمشاركة {participation:.2f}% "
            f"من حجم السوق، وانزلاق متوقع {slippage_bps:.2f} نقطة أساس "
            f"(تكلفة إجمالية {cost_pct_of_notional:.3f}% من قيمة المركز)."
        )
        invalidation = (
            f"يُبطل هذه الخطة إذا اتسع السبريد فوق {max(15.0, spread*3):.1f} نقطة أساس، أو إذا "
            f"انخفض الحجم اليومي تحت {adv*0.5/1e6:.1f}M$، أو إذا تجاوز الانزلاق الفعلي "
            f"{slippage_bps*2:.1f} نقطة أساس في أول شريحتين."
        )
        dissent = (
            "أقوى ما يخالف هذه الخطة: نماذج الأثر كلها تقديرية وتفشل بالضبط في اللحظات التي "
            "يهم فيها التنفيذ (تقلب حاد، انقطاع سيولة). كما أن التجزؤ الزمني يعرّض المركز "
            "لمخاطرة السعر أثناء التنفيذ (Timing Risk) — وهي مقايضة لا حل."
        )
        notes = [f"ℹ️ التكلفة المتوقعة تمثل {cost_pct_of_notional:.3f}% من قيمة المركز"]
        if cost_pct_of_notional > 0.5:
            notes.append("⚠️ تكلفة تنفيذ مرتفعة — قد تلتهم جزءاً كبيراً من الحافة المتوقعة")
        if days_needed > 5:
            notes.append(f"⚠️ مدة تنفيذ طويلة ({days_needed:.1f} يوم) — مخاطرة توقيت مرتفعة")

        return self.make(
            ctx, 0.0, thesis, evidence, invalidation, dissent,
            metrics={"plan": plan.to_dict(), "days_needed": round(days_needed, 3),
                     "cost_pct": round(cost_pct_of_notional, 4)},
            dead_zone=1.0,
            notes=notes + ["⚠️ خطة نظرية — لا تنفيذ حقيقي (المادة 0.2)"],
        )


# ==========================================================================
# 13 — وكيل الالتزام والتدقيق
# ==========================================================================

class ComplianceAgent(BaseAgent):
    """
    المدقّق. يفحص **كل** الآراء مرة واحدة ولا يفحص نفسه أبداً بهدف التجميل.

    سلطته: تستطيع إسقاط أي رأي وإيقاف أي قرار (المادة 8).
    """

    id, name_ar, name_en = "13", "وكيل الالتزام والتدقيق", "Compliance & Audit Agent"
    layer, authority, domain = Layer.CONTROL, Authority.VETO, "compliance"
    horizon = "—"
    file = "agents/13-compliance-audit.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        violations: list[Violation] = []
        missing_agents: list[str] = []

        # -- 1) هل كل وكيل إلزامي قد أصدر رأياً؟ -------------------------
        required_layers = {Layer.KNOWLEDGE, Layer.VALIDATION, Layer.CONTROL}
        for spec in ROSTER_BY_ID.values():
            if spec.layer in required_layers and spec.id not in ctx.opinions and spec.id != self.id:
                if spec.id in {"09", "10", "11", "12"}:
                    missing_agents.append(f"{spec.id} ({spec.name_ar})")

        # -- 2) فحص كل رأي مقابل عقد الرأي وفصل السلطات ------------------
        scanned = 0
        for aid, op in list(ctx.opinions.items()):
            if aid == self.id:
                continue
            scanned += 1
            violations.extend(ctx.law.validate_opinion(op))

        # -- 3) فحص فصل السلطات على مستوى المحتوى ------------------------
        for aid, op in ctx.opinions.items():
            spec = ROSTER_BY_ID.get(aid)
            if not spec:
                violations.append(Violation("1.1", "UNKNOWN_AGENT",
                                            f"وكيل غير مسجّل في الكشف: {aid}", "error", aid))
                continue
            if spec.authority == Authority.VETO and op.direction != Direction.NEUTRAL.value:
                if op.metrics.get("raw_score", 0.0) not in (0.0, None):
                    violations.append(Violation(
                        "1.3", "VETO_AGENT_DIRECTIONAL",
                        f"[{aid}] وكيل ذو حق نقض أعلن اتجاهاً سوقياً — خرق الاستقلالية",
                        "error", aid))

        # -- 4) منع التنفيذ (المادة 0.2) --------------------------------
        for aid, op in ctx.opinions.items():
            blob = " ".join([op.thesis, *[e.claim for e in op.evidence]])
            violations.extend(ctx.law.enforce_no_execution(blob, aid))

        # -- 5) الجرائم الصامتة: الاختلاق والتحيّز الاسترجاعي (المادة 8.1/8.2) --
        # كانت الأنماط معرّفة في `law.PROHIBITED_PATTERNS` وبلا أي مسار يفحصها،
        # أي أن أخطر جريمتين دستوريتين لهما كاشف مكتوب وغير مُشغَّل.
        for aid, op in ctx.opinions.items():
            blob = " ".join([op.thesis, op.invalidation, op.dissent,
                             *[e.claim for e in op.evidence]])
            violations.extend(ctx.law.scan_prohibited(
                blob, aid, codes={"FABRICATION_MARKER", "HINDSIGHT_MARKER",
                                  "CERTAINTY_OF_EDGE"}))

        # -- 6) قانون التحقق (المادة 4.1) — التأكد من إجراء الفحوص الأربعة --
        validation_op = ctx.opinions.get("09")
        if validation_op is None:
            violations.append(Violation("4.1", "VALIDATION_AGENT_MISSING",
                                        "لا رأي من وكيل التحقق — لا تخصيص رأس مال", "error", "13"))
        else:
            violations.extend(ctx.law.require_validation(
                validation_op.metrics, agent_id="09"))
            # إغلاق الثغرة الدائرية: لا نكتفي بشهادة الوكيل 09 عن نفسه —
            # نعيد حساب فحوصه من نفس اللقطة ونقارن.
            violations.extend(ComplianceAgent._verify_validation_independently(ctx))
            if not validation_op.metrics.get("overfitting_checked"):
                violations.append(Violation("4.1", "OVERFITTING_NOT_CHECKED",
                                            "فحص الإفراط في التوفيق لم يُجرَ", "error", "09"))

        # -- 7) هرمية الأدلة (المادة 3.1/3.2) — هل يوجد دليل من الطبقة 1 أو 2؟ --
        all_evidence = [e for op in ctx.knowledge_opinions() if not op.abstain
                        for e in op.evidence]
        if all_evidence:
            strongest, weakest = ctx.law.arbitrate_evidence(all_evidence)
            ctx.shared["evidence_arbitration"] = (
                ctx.law.arbitrate_conflict(strongest, weakest) if weakest else None
            )
            if strongest is not None and strongest.tier >= 4:
                violations.append(Violation(
                    "3.1", "NO_PRIMARY_EVIDENCE",
                    "لا يوجد دليل من الطبقة 1 (أونشين) أو 2 (سوق متعدد المنصات) — "
                    "القرار يسند على أدلة فنية/معنويات فقط", "warning", "13"))

        # -- 8) هل بيانات المصدر موثّقة؟ --------------------------------
        snap = ctx.snapshot
        if not snap.source:
            violations.append(Violation("2.5", "UNSOURCED_SNAPSHOT",
                                        "لقطة سوقية بلا مصدر معلن", "error", "13"))
        if snap.source == "synthetic" and not snap.meta.get("warning"):
            violations.append(Violation("3.1", "SYNTHETIC_NOT_LABELED",
                                        "بيانات اصطناعية بلا وسم تحذيري", "warning", "13"))

        # -- 9) بناء التقرير --------------------------------------------
        errors = [v for v in violations if v.severity == "error"]
        report = ComplianceReport(
            compliant=not errors and not missing_agents,
            violations=[v.to_dict() for v in violations],
            checked_agents=scanned,
            blocked=bool(errors),
            notes=(
                [f"وكلاء مفقودون من الدورة: {', '.join(missing_agents)}"] if missing_agents else []
            ) + [f"عدد المخالفات: {len(violations)} ({len(errors)} حرجة)"],
        )
        ctx.shared["compliance"] = report

        evidence = [
            self.ev(ctx, f"تم فحص {scanned} رأياً مقابل عقد الرأي (المادة 2) وفصل السلطات (المادة 1)",
                    "compliance/opinion-audit", "derived", Strength.HIGH.value, float(scanned)),
            self.ev(ctx, f"المخالفات الحرجة: {len(errors)} — العناوين: "
                         f"{', '.join(sorted({v.article for v in errors})) or 'لا شيء'}",
                    "compliance/violation-scan", "derived", Strength.HIGH.value, float(len(errors))),
            self.ev(ctx, f"فحص منع التنفيذ (المادة 0.2): "
                         f"{'لا محاولات تنفيذ' if not any(v.code == 'EXECUTION_INSTRUCTION' for v in violations) else 'رُصدت محاولة تنفيذ'}",
                    "compliance/no-execution-check", "derived", Strength.HIGH.value, None),
            self.ev(ctx, f"فحص الجرائم الصامتة (المادتان 8.1 و8.2 — اختلاق وتحيّز استرجاعي): "
                         f"{sum(1 for v in violations if v.code in {'FABRICATION_MARKER','HINDSIGHT_MARKER'})} إصابة",
                    "compliance/silent-crimes-scan", "derived", Strength.HIGH.value, None),
            self.ev(ctx, f"تحقق قانون المادة 4.1: فحوص OOS والتكاليف والقدرة والإفراط "
                         f"{'مكتملة' if not any(v.code.startswith('MISSING_') or v.code == 'OVERFITTING_NOT_CHECKED' for v in violations) else 'ناقصة'}",
                    "compliance/validation-audit", "derived", Strength.HIGH.value, None),
            self.ev(ctx, f"تحكيم هرمية الأدلة (المادة 3.2): أقوى دليل بالطبقة "
                         f"{(ctx.shared.get('evidence_arbitration') or {}).get('winner_tier', '—')}",
                    "compliance/evidence-arbitration", "derived", Strength.MEDIUM.value, None),
            self.ev(ctx, f"اكتمال الدورة: {len(ctx.opinions)} وكيل من أصل 15 "
                         f"({len(missing_agents)} مفقود في هذه المرحلة)",
                    "compliance/roster-completeness", "derived", Strength.MEDIUM.value, float(len(ctx.opinions))),
        ]

        if report.compliant:
            thesis = (f"✅ الدورة متوافقة دستورياً: {scanned} رأياً مفصول الصلاحيات، "
                      f"{len(violations)} مخالفة غير حرجة، ولا محاولة تنفيذ.")
        else:
            thesis = (f"⛔ **حجب**: {len(errors)} مخالفة حرجة من أصل {len(violations)} — "
                      f"أبرزها: {errors[0].message if errors else 'وكلاء مفقودون'}")

        invalidation = (
            "يُبطل هذا التقرير إذا أُضيف رأي جديد بعد الفحص، أو عُدّل سجل، أو استُخدم دليل "
            "بمصدر غير موثّق — الفحص لحظي ويسقط بأي تغيير لاحق."
        )
        dissent = (
            "أقوى ما يخالف هذا التقرير: الفحص آلي يتحقق من **وجود** الحقول لا من **صدقها**. "
            "وكيل قد يملأ شرط الإبطال بعبارة عامة فيمرّ الفحص، والاختلاق الذكي لا تكشفه "
            "الأنماط النصية. الالتزام الشكلي ليس التزاماً حقيقياً."
        )

        op = self.make(
            ctx, 0.0, thesis, evidence, invalidation, dissent,
            metrics={"compliant": report.compliant, "blocked": report.blocked,
                     "violations_count": len(violations), "critical": len(errors),
                     "missing_agents": missing_agents},
            dead_zone=1.0,
            notes=[f"⛔ {v}" for v in errors[:6]] or ["✅ لا مخالفات حرجة"],
        )
        op.confidence = 90.0 if report.compliant else 98.0
        return op


    # ------------------------------------------------------------------ #
    @staticmethod
    def _verify_validation_independently(ctx: AgentContext) -> list[Violation]:
        """
        **تحقق مستقل من وكيل التحقق (09)** — إغلاق الثغرة الدائرية.

        المشكلة الأصلية: `require_validation` كان يستهلك أربعة booleans **يكتبها
        الوكيل 09 عن نفسه**. وكيل كاذب يصرّح `validated=True` والأربعة `True`
        يمرّ بلا اعتراض ويُضاعف حجم المركز. أي أن المستوى الثاني من النظام
        (التحقق) كان **يشهد لنفسه**.

        الحل: وكيل الالتزام **يعيد حساب** نفس الفحوص من نفس اللقطة (كلها دوال
        حتمية) ويقارن النتيجة بتصريح الوكيل 09. أي اختلاف = مخالفة.
        """
        from .validation import capacity_analysis, lookahead_audit

        v: list[Violation] = []
        op09 = ctx.opinions.get("09")
        if op09 is None:
            return [Violation("4.1", "VALIDATION_AGENT_MISSING",
                              "لا رأي من وكيل التحقق — لا تخصيص رأس مال", "error", "13")]
        m = op09.metrics
        snap, feats = ctx.snapshot, ctx.features

        # 1) إعادة حساب تدقيق التسرّب
        la = lookahead_audit(snap.closes)
        if bool(la.get("clean")) != bool(m.get("lookahead_clean")):
            v.append(Violation(
                "4.1", "VALIDATION_SELF_REPORT_MISMATCH",
                f"تصريح وكيل 09 عن التسرّب ({m.get('lookahead_clean')}) لا يطابق "
                f"الحساب المستقل ({la.get('clean')})", "error", "09"))
        if not la.get("self_test_passed"):
            v.append(Violation("4.1", "LOOKAHEAD_TOOL_UNVERIFIED",
                               "كاشف التسرّب لم يجتز اختباره الذاتي — لا قيمة لاجتيازه",
                               "error", "09"))

        # 2) إعادة حساب تحليل القدرة
        daily_vol_fraction = max(1e-6, float(feats.get("vol_30d_ann_pct", 0.0)) / 100.0 / (365 ** 0.5))
        cap = capacity_analysis(
            adv_usd=float(snap.avg_volume_30d_usd or snap.volume_24h_usd or 0.0),
            daily_vol_fraction=daily_vol_fraction,
            spread_bps=float(feats.get("spread_bps", 0.0)),
            fee_bps=float(snap.taker_fee_bps),
            max_participation_pct=ctx.config.limits.max_market_participation_pct,
        )
        declared_cap = (m.get("capacity") or {}).get("capacity_usd")
        if declared_cap is None:
            v.append(Violation("4.1", "CAPACITY_NOT_DECLARED",
                               "وكيل التحقق لم يُعلن نتيجة تحليل القدرة", "error", "09"))
        elif abs(float(declared_cap) - float(cap["capacity_usd"])) > max(
                1.0, 0.02 * float(cap["capacity_usd"])):
            v.append(Violation(
                "4.1", "CAPACITY_SELF_REPORT_MISMATCH",
                f"قدرة معلنة ${float(declared_cap):,.0f} مقابل حساب مستقل "
                f"${cap['capacity_usd']:,.0f}", "error", "09"))

        # 3) بنية نتيجة الاختبار — لا يُقبل تصريح بلا أثر قابل للفحص
        bt = m.get("backtest") or {}
        for key in ("n_obs", "n_trials", "is_sharpe", "oos_sharpe", "costs_modeled",
                    "excess_vs_benchmark", "deflated_sharpe", "sharpe_decay"):
            if key not in bt:
                v.append(Violation("4.1", "BACKTEST_STRUCTURE_INCOMPLETE",
                                   f"نتيجة الاختبار بلا حقل «{key}» — تصريح بلا أثر",
                                   "error", "09"))
        if m.get("oos_tested") and not bt.get("ok"):
            v.append(Violation("4.1", "OOS_CLAIM_WITHOUT_RUN",
                               "تصريح باختبار خارج العينة بلا اختبار ناجح", "error", "09"))
        if int(bt.get("n_obs", 0)) < 200:
            v.append(Violation("4.1", "SAMPLE_TOO_SMALL",
                               f"عينة {bt.get('n_obs')} نقطة دون الحد الأدنى 200",
                               "warning", "09"))

        # 4) وكيل التحقق نفسه يخضع لعقد الرأي
        v.extend(ctx.law.validate_opinion(op09))
        return v

    # ------------------------------------------------------------------ #
    @staticmethod
    def audit_decision(ctx: AgentContext, decision: Any) -> dict[str, Any]:
        """
        **تدقيق بعدي للقرار** — ثغرة حوكمة مُصلَحة.

        المشكلة الأصلية: الوكيل 13 يُشغَّل في المرحلة 【4】 قبل المنسّق (14) في
        المرحلة 【5】، فكان **أهم مخرج في الديسك — القرار النهائي — لا يُدقَّق
        إطلاقاً**، رغم أن ملف الوكيل 13 ينص على أنه يدقّق مخرجات 01–12 **و14**.

        الحل: مسار تدقيق ثانٍ بعد إصدار القرار، نتيجته تُسجَّل في السجل
        (`post_decision_audit`) وتُعرض في التقرير. لا يُعدّل القرار (المادة 7.2)
        بل يوثّق صلاحيته.
        """
        violations: list[Violation] = []
        limits = ctx.config.limits
        checks_run = 0

        # المادة 6.3 — قرار بلا رأي مخالف مسجّل يُعاد للمنسّق
        violations.extend(ctx.law.validate_decision_completeness(
            decision.supporting_agents, decision.opposing_agents, decision.strongest_dissent,
            dissent_source=getattr(decision, "dissent_source", "none"),
            directional=decision.action in (Action.LONG.value, Action.SHORT.value)))
        checks_run += 2

        # المادة 1.4 — المنسّق لا يُنتج دليلاً أصلياً: كل دليله يجب أن يكون
        # إحالة إلى مخرجات وكيل معرفي، لا حساباً خاصاً به.
        checks_run += 1
        op14_for_evidence = ctx.opinions.get("14")
        if op14_for_evidence is not None:
            knowledge_ids = {o.agent_id for o in ctx.knowledge_opinions()}
            own_evidence = [
                e for e in op14_for_evidence.evidence
                if not any(aid in e.source for aid in knowledge_ids)
                and not e.source.startswith("aggregation/")
            ]
            if own_evidence:
                violations.append(Violation(
                    "1.4", "ORCHESTRATOR_PRODUCED_EVIDENCE",
                    f"{len(own_evidence)} دليلاً في رأي المنسّق لا يشير إلى مخرج وكيل "
                    f"معرفي — المنسّق لا يُنتج دليلاً أصلياً", "error", "14"))

        # المادة 8.4 — إخفاء الخسائر: القرار يجب أن يفصح عن حالة الأداء الراهنة
        checks_run += 1
        pnl = ctx.config.daily_pnl_pct
        dd = abs(ctx.config.current_drawdown_pct)
        in_loss = pnl < 0 or dd > 0
        if in_loss:
            blob = f"{decision.rationale} {decision.invalidation}"
            if "خسارة" not in blob and "تراجع" not in blob:
                violations.append(Violation(
                    "8.4", "LOSS_NOT_DISCLOSED",
                    f"الديسك في خسارة يومية {pnl:.2f}% / تراجع {dd:.2f}% "
                    f"ولا يذكرها القرار — إخفاء خسائر", "error", "14"))

        # المادة 8.7 — الالتفاف على الحدود بتقسيم المراكز
        checks_run += 1
        for ev in (ctx.shared.get("exposure_violations") or []):
            violations.append(Violation(
                ev["article"], ev["code"], ev["message"], ev["severity"], "11"))

        # المادة 2.2 — شرط الإبطال
        checks_run += 1
        if not decision.invalidation or decision.invalidation.strip() in {"", "—"}:
            violations.append(Violation("2.2", "DECISION_WITHOUT_INVALIDATION",
                                        "قرار بلا شرط إبطال — يُرفض آلياً", "error", "14"))

        # المادة 1.4 — المنسّق لا يُنتج دليلاً أصلياً
        checks_run += 1
        if not decision.evidence_summary:
            violations.append(Violation("1.4", "DECISION_WITHOUT_EVIDENCE",
                                        "قرار بلا أي دليل من طبقة المعرفة", "error", "14"))

        # المادة 5.1/5.2 — اتساق القرار مع حكم المخاطر
        checks_run += 3
        verdict = ctx.shared.get("risk_verdict")
        directional = decision.action in (Action.LONG.value, Action.SHORT.value)
        if verdict is not None:
            if directional and not verdict.approved:
                violations.append(Violation(
                    "5.1", "DECISION_OVER_RISK_DENIAL",
                    f"قرار اتجاهي ({decision.action}) رغم أن المخاطر لم تعتمد أي حجم "
                    f"(veto={verdict.veto}, approved={verdict.approved})", "error", "14"))
            if verdict.veto and decision.size_usd > 0:
                violations.append(Violation(
                    "5.1", "SIZE_WITH_VETO",
                    f"حجم موجب ({decision.size_usd:,.0f}$) مع نقض نافذ للمخاطر", "error", "14"))
            if not verdict.approved and decision.size_usd > 0:
                violations.append(Violation(
                    "5.2", "SIZE_WITHOUT_APPROVAL",
                    "حجم موجب دون اعتماد من محرك المخاطر", "error", "14"))
            if directional and abs(decision.size_usd - verdict.position_size_usd) > 0.01:
                violations.append(Violation(
                    "5.1", "SIZE_MISMATCH",
                    f"حجم القرار {decision.size_usd:,.0f}$ ≠ الحجم المعتمد "
                    f"{verdict.position_size_usd:,.0f}$ — تجاوز أو التفاف على المخاطر",
                    "error", "14"))

        # المادة 5.3 — الثقة
        checks_run += 1
        if directional and decision.confidence < limits.min_confidence:
            violations.append(Violation(
                "5.3", "DECISION_BELOW_MIN_CONFIDENCE",
                f"قرار اتجاهي بثقة {decision.confidence:.1f} < {limits.min_confidence}",
                "error", "14"))

        # المادة 5.3 — أقصى حجم مركز
        checks_run += 1
        if decision.size_usd > 0:
            pct = decision.size_usd / max(1e-9, ctx.config.capital_usd) * 100.0
            if pct > limits.max_position_pct + 1e-6:
                violations.append(Violation(
                    "5.3", "SIZE_EXCEEDS_MAX_POSITION",
                    f"حجم القرار {pct:.3f}% يتجاوز حد المركز {limits.max_position_pct}%",
                    "error", "14"))

        # المادة 6.1 — الرأي المخالف يجب أن يكون محفوظاً
        checks_run += 1
        if not decision.strongest_dissent.strip():
            violations.append(Violation("6.1", "DISSENT_NOT_PRESERVED",
                                        "لم يُحفظ أي رأي مخالف في القرار", "error", "14"))

        # المادة 0.2 — لا تنفيذ حقيقي في نص القرار
        checks_run += 1
        violations.extend(ctx.law.enforce_no_execution(decision.rationale, "14"))

        # المادة 8 — فحص **كل** الأنماط المحرّمة على نص القرار ورأي المنسّق.
        # ثغرة مُصلَحة: وكيل 14 (و13 و15) لم تكن آراؤهم تُفحَص إطلاقاً، فنص
        # «تم إرسال الأمر إلى المنصة — صفقة مضمونة» في رأي المنسّق كان يمرّ
        # بصفر مخالفات — حتى في التدقيق البعدي.
        checks_run += 1
        decision_text = " ".join([decision.rationale, decision.invalidation,
                                  decision.strongest_dissent])
        violations.extend(ctx.law.scan_prohibited(decision_text, "14"))

        op14 = ctx.opinions.get("14")
        if op14 is not None:
            checks_run += 1
            violations.extend(ctx.law.validate_opinion(op14))

        # المادة 8.3 — تسرّب البيانات المستقبلية: الفحص كان يكشف ولا يمنع
        checks_run += 1
        val_metrics = ctx.shared.get("validation") or {}
        if val_metrics.get("lookahead_clean") is False:
            violations.append(Violation(
                "8.3", "LOOKAHEAD_LEAK_DETECTED",
                "رُصد تسرّب بيانات مستقبلية في الإشارة — خرق المادة 8.3", "error", "09"))

        # المادة 4.1 — هل القرار مبني على تحقق مكتمل؟
        checks_run += 1
        val = ctx.shared.get("validation") or {}
        if directional and not val.get("oos_tested"):
            violations.append(Violation("4.1", "DECISION_WITHOUT_VALIDATION",
                                        "قرار اتجاهي بلا اختبار خارج العينة", "warning", "14"))

        errors = [v for v in violations if v.severity == "error"]
        report = {
            "audited": True,
            "decision_id": decision.decision_id,
            "valid": not errors,
            "checked": checks_run,
            "violations_found": len(violations),
            "critical": len(errors),
            "violations": [v.to_dict() for v in violations],
            "note": ("تدقيق بعدي للقرار — لا يُعدّل القرار بل يوثّق صلاحيته (المادة 7.2)"
                     if not errors else
                     "⛔ القرار يحمل مخالفة حرجة — يجب اعتباره غير صالح ومراجعته"),
        }
        ctx.shared["post_decision_audit"] = report
        return report


CONTROL_AGENTS: tuple[type[BaseAgent], ...] = (
    RiskManagerAgent,
    ExecutionAgent,
    ComplianceAgent,
)
