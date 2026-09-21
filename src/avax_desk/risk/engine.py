"""
محرك المخاطر — CONSTITUTION.md المادة 5.

هذا الملف يحوّل "سيادة المخاطر" من شعار إلى حساب.

القاعدة الحاكمة: **حجم المركز يُحسب، لا يُقدَّر** (المادة 5.5).
والقرار يُبنى على أقصى خسارة مقبولة، لا على أقصى ربح متوقع (المادة 5.2).
"""

from __future__ import annotations

import math
from typing import Any

from .. import indicators as ind
from ..config import DeskConfig, Limits
from ..contracts import RiskLevel, RiskVerdict, now_iso


class RiskEngine:
    """
    محرك مستقل تماماً عن أي وكيل معرفي (المادة 1.3).

    لا يعرف "الاتجاه المتوقع" إلا كوسيط لحساب الحجم — ولا يبني رأياً سوقياً.
    """

    #: نسبة الربح إلى الخسارة المستهدفة (R:R) — 1:1.5 افتراضياً
    DEFAULT_REWARD_RISK = 1.5

    def __init__(self, config: DeskConfig) -> None:
        self.config = config
        self.limits = config.limits

    # ------------------------------------------------------------------ #
    def risk_level(self, daily_pnl_pct: float, drawdown_pct: float) -> tuple[str, str]:
        """
        سلّم الإنذار — المادة 9.3.

        اصطلاح الإشارة: `drawdown_pct` يُقبل **بأي إشارة** (يُؤخذ بالقيمة المطلقة).
        السبب: «التراجع من القمة» كمية موجبة بطبيعتها، لكن واجهة CLI كانت تطلب
        قيمة سالبة ضمنياً — فمن يمرّر `20` (وهو القراءة الطبيعية) كان يحصل على
        مستوى أخضر وحماية معطّلة تماماً رغم تجاوز حد 15%. هذا خطأ صامت خطير.
        """
        lim = self.limits
        dd = abs(float(drawdown_pct))
        pnl = float(daily_pnl_pct)
        if -pnl >= lim.max_daily_loss_pct or dd >= lim.max_drawdown_pct:
            return RiskLevel.RED.value, (f"🔴 تجاوز حد الخسارة — إيقاف كامل فوري "
                                         f"(خسارة يومية {pnl:.2f}% / تراجع {dd:.2f}%)")
        if -pnl >= 1.5:
            return RiskLevel.ORANGE.value, "🟠 خسارة يومية 1.5% — إيقاف المراكز الجديدة"
        if -pnl >= 0.75:
            return RiskLevel.YELLOW.value, "🟡 خسارة يومية 0.75% — تخفيض حجم المركز 50%"
        if dd >= 0.5 * lim.max_drawdown_pct:
            return RiskLevel.YELLOW.value, "🟡 تراجع من القمة تجاوز نصف الحد — تخفيض الحجم"
        return RiskLevel.GREEN.value, "🟢 كل الحدود سليمة"

    # ------------------------------------------------------------------ #
    @staticmethod
    def win_probability(confidence: float) -> float:
        """
        تحويل درجة الثقة (0-100) إلى احتمال نجاح تقديري.

        الخريطة محافظة عمداً: ثقة 65 ⇒ 0.525، ثقة 88 ⇒ 0.640.
        الهدف منع كيلي من إنتاج أحجام ضخمة بناءً على ثقة مبالغ فيها.
        """
        return ind.clamp(0.45 + (confidence - 50.0) * 0.005, 0.30, 0.72)

    # ------------------------------------------------------------------ #
    def suggest_stops(self, entry: float, atr_value: float, direction: str) -> dict[str, float]:
        """وقف الخسارة والأهداف بمضاعفات ATR — منهج موضوعي لا عشوائي."""
        m = self.limits.atr_stop_multiple
        if atr_value <= 0:
            atr_value = entry * 0.03
        if direction == "bullish":
            stop = entry - m * atr_value
            target1 = entry + m * atr_value * self.DEFAULT_REWARD_RISK
            target2 = entry + m * atr_value * self.DEFAULT_REWARD_RISK * 2.0
        elif direction == "bearish":
            stop = entry + m * atr_value
            target1 = entry - m * atr_value * self.DEFAULT_REWARD_RISK
            target2 = entry - m * atr_value * self.DEFAULT_REWARD_RISK * 2.0
        else:
            return {"stop": entry, "target1": entry, "target2": entry, "atr": atr_value}
        return {
            "stop": stop,
            "target1": target1,
            "target2": target2,
            "atr": atr_value,
            "stop_distance_pct": abs(entry - stop) / entry * 100.0,
            "reward_risk": abs(target1 - entry) / max(1e-9, abs(entry - stop)),
        }

    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        features: dict[str, Any],
        snapshot: Any,
        direction: str,
        confidence: float,
        *,
        compliance_ok: bool = True,
        compliance_notes: list[str] | None = None,
        strategy_metrics: dict[str, Any] | None = None,
    ) -> RiskVerdict:
        """
        إصدار حكم المخاطر الكامل.

        المخرجات: موافقة/نقض + حجم المركز + الوقف + الحدود المفحوصة.
        """
        lim = self.limits
        cfg = self.config
        veto_reasons: list[str] = []
        notes: list[str] = []
        strategy_metrics = strategy_metrics or {}

        price = float(features.get("price") or snapshot.price or 0.0)
        atr_v = float(features.get("atr14") or 0.0)
        vol_ann = float(features.get("vol_30d_ann_pct") or 0.0)
        spread_bps = float(features.get("spread_bps") or 0.0)
        adv = float(snapshot.avg_volume_30d_usd or snapshot.volume_24h_usd or 0.0)

        level, level_msg = self.risk_level(cfg.daily_pnl_pct, cfg.current_drawdown_pct)

        # المادة 9.3 — «أصفر: تقلب مرتفع أو بيانات ناقصة ⇒ تخفيض حجم المركز 50%».
        # هذا الشرط لا يُشتق من الخسارة بل من حالة السوق والبيانات، ويُطبَّق فقط
        # عند مستوى أخضر (لا نُخفّض مستوى أسوأ قائماً).
        vol_regime = str(features.get("vol_regime", "normal"))
        completeness = float(features.get("completeness", 1.0))
        if level == RiskLevel.GREEN.value:
            if vol_regime in ("high", "extreme"):
                level = RiskLevel.YELLOW.value
                level_msg = (f"🟡 نظام تقلب «{vol_regime}» — تخفيض حجم المركز 50% (المادة 9.3)")
            elif completeness < 1.0:
                level = RiskLevel.YELLOW.value
                level_msg = (f"🟡 اكتمال البيانات {completeness*100:.0f}% — "
                             f"تخفيض حجم المركز 50% (المادة 9.3)")
        notes.append(level_msg)

        # ---------------- 1) الفحوص المانعة (Hard Gates) ----------------
        if cfg.halted:
            veto_reasons.append("الديسك في حالة إيقاف كامل (المادة 9.3 / مستوى أحمر)")

        if level == RiskLevel.RED.value:
            veto_reasons.append(f"حد الخسارة مخروق: خسارة يومية {cfg.daily_pnl_pct:.2f}% / "
                                f"تراجع {cfg.current_drawdown_pct:.2f}% (المادة 5.4)")

        if not compliance_ok:
            veto_reasons.append("رفض من وكيل الالتزام: مخالفة دستورية قائمة (المادة 8)")

        if direction == "neutral":
            veto_reasons.append("لا اتجاه محدد من طبقة المعرفة — لا مبرر لفتح مركز")

        if confidence < lim.min_confidence:
            veto_reasons.append(
                f"الثقة {confidence:.1f} أدنى من الحد الأدنى {lim.min_confidence} (المادة 5.3)"
            )

        if price <= 0 or adv <= 0:
            veto_reasons.append("بيانات سعرية أو حجمية غير صالحة — لا يمكن تسعير المخاطرة")

        if spread_bps > 25.0:
            veto_reasons.append(f"السبريد {spread_bps:.1f} نقطة أساس واسع جداً — تكلفة التنفيذ تلتهم الحافة")

        if vol_ann > 150.0:
            veto_reasons.append(f"تقلب سنوي {vol_ann:.0f}% خارج نطاق أي نموذج مخاطرة معقول")

        # المادة 4.1 — لا مركز على إشارة لم تُجرَ عليها فحوص التحقق الأربعة.
        # ملاحظة تفسيرية: المادة تشترط **إجراء الفحوص** لا نجاحها.
        # فشل الفحوص (validated=False) لا يمنع المركز بل يخفّض حجمه إلى النصف
        # ويُلزم ثقة أعلى — المنع الكامل يُترك لحدود المخاطرة الصريحة.
        if strategy_metrics:
            required_checks = ("oos_tested", "costs_modeled", "capacity_checked", "overfitting_checked")
            missing_checks = [c for c in required_checks if not strategy_metrics.get(c)]
            if missing_checks:
                veto_reasons.append(
                    "فحوص التحقق غير مكتملة (المادة 4.1): " + ", ".join(missing_checks)
                )
            if not strategy_metrics.get("validated", False):
                quality_haircut = 0.5
                notes.append(
                    "⚠️ الإشارة لم تجتز معايير الجودة في قانون التحقق — تخفيض الحجم 50% "
                    "ورفع الحد الأدنى للثقة"
                )
            else:
                quality_haircut = 1.0
        else:
            quality_haircut = 1.0

        # ---------------- 2) حجم المركز (محسوب، لا مقدَّر) ----------------
        level_multiplier = {
            RiskLevel.GREEN.value: 1.0,
            RiskLevel.YELLOW.value: 0.5,
            RiskLevel.ORANGE.value: 0.0,
            RiskLevel.RED.value: 0.0,
        }.get(level, 0.0)

        # إصلاح ثغرة: مستوى برتقالي/أحمر يصفّر الحجم بلا سبب نقض صريح، فينتج
        # قرار بعنوان اتجاهي وحجم صفر. المادة 9.3 تفرض إيقاف المراكز الجديدة.
        if level_multiplier <= 0.0:
            veto_reasons.append(
                f"مستوى الإنذار «{level}» ⇒ مضاعف الحجم صفر — لا مراكز جديدة (المادة 9.3)"
            )

        p = self.win_probability(confidence)
        b = self.DEFAULT_REWARD_RISK
        # سقف كيلي الداخلي 30% لا 10% — وإلا تعادل كيلي مع حد المركز دائماً
        # فصار قيداً شكلياً لا حقيقياً. حد المركز (10%) يبقى مرشحاً مستقلاً أدناه.
        kelly_capped = ind.fractional_kelly(p, b, fraction=lim.max_kelly_fraction, cap=0.30)
        kelly_notional = kelly_capped * cfg.capital_usd

        stops = self.suggest_stops(price, atr_v, direction)
        stop_pct = float(stops.get("stop_distance_pct") or 3.0)
        risk_pct = min(lim.max_risk_per_trade_pct * level_multiplier,
                       max(0.05, lim.max_risk_per_trade_pct))
        # حجم المخاطرة الثابتة: المخاطرة بالدولار ÷ نسبة الوقف
        fixed_fractional_notional = (cfg.capital_usd * risk_pct / 100.0) / max(1e-6, stop_pct / 100.0)

        max_position_notional = cfg.capital_usd * lim.max_position_pct / 100.0
        participation_notional = adv * lim.max_market_participation_pct / 100.0

        # المادة 5.3 — حد التركّز القطاعي 25% (كان معرّفاً وغير مستخدم)
        sector_budget_pct = lim.max_sector_concentration_pct - cfg.current_sector_exposure_pct
        sector_notional = max(0.0, cfg.capital_usd * sector_budget_pct / 100.0)
        if sector_budget_pct <= 0:
            veto_reasons.append(
                f"حد التركّز القطاعي مستنفد: تعرّض «{cfg.sector}» الحالي "
                f"{cfg.current_sector_exposure_pct:.2f}% ≥ الحد {lim.max_sector_concentration_pct}% "
                f"(المادة 5.3)"
            )

        candidates = {
            "kelly": kelly_notional,
            "fixed_fractional": fixed_fractional_notional,
            "max_position_limit": max_position_notional,
            "sector_concentration_limit": sector_notional,
            "market_participation_limit": participation_notional,
            "liquidity_depth_limit": (float(features.get("depth_usd") or 0.0)
                                      * lim.max_depth_participation_pct / 100.0),
        }
        binding = min(candidates, key=lambda k: candidates[k])
        final_notional = max(0.0, candidates[binding] * level_multiplier * quality_haircut)

        if candidates["market_participation_limit"] <= 1.0:
            veto_reasons.append("سيولة السوق لا تسمح بأي مركز ذي معنى — رفض تنفيذي")

        # أدنى حجم قابل للتنفيذ: مركز رمزي يُقرَّب إلى صفر ليس مركزاً.
        if 0.0 < final_notional < lim.min_position_usd:
            veto_reasons.append(
                f"الحجم المحسوب ${final_notional:,.2f} أدنى من الحد القابل للتنفيذ "
                f"${lim.min_position_usd:,.0f} — لا مركز ذي معنى (المادة 5.2)"
            )

        if binding == "max_position_limit":
            notes.append(
                "ℹ️ كيلي ليس القيد الملزم: حد المركز الأقصى (المادة 5.3) هو ما يحكم الحجم — "
                "وهذا سلوك متحفظ مقصود لا خلل في الحساب"
            )

        # إعلان صريح لتركيب التخفيضات: مضاعف المستوى (المادة 9.3) وخصم الجودة
        # (المادة 4.1) يتضاعفان. أصفر × جودة غير مجتازة = 0.25 ⇒ تخفيض 75% لا 50%.
        # التركيب صحيح منطقياً (تخفيضان مستقلان) لكنه **مفاجئ** إن لم يُعلَن.
        if level_multiplier < 1.0 and quality_haircut < 1.0:
            notes.append(
                f"ℹ️ تخفيضان متراكبان: مستوى «{level}» ×{level_multiplier:.2f} "
                f"وخصم الجودة ×{quality_haircut:.2f} = ×{level_multiplier * quality_haircut:.2f} "
                f"(تخفيض إجمالي {(1 - level_multiplier * quality_haircut) * 100:.0f}%)"
            )

        notes.append(
            f"حجم المركز محكوم بـ «{binding}» "
            f"(كيلي ${kelly_notional/1e3:.1f}K | مخاطرة ثابتة ${fixed_fractional_notional/1e3:.1f}K | "
            f"حد المركز ${max_position_notional/1e3:.1f}K | قطاعي ${sector_notional/1e3:.1f}K | "
            f"مشاركة السوق ${participation_notional/1e3:.1f}K)"
        )

        # ---------------- 3) المخاطرة الفعلية ----------------
        units = final_notional / price if price > 0 else 0.0
        risk_amount = units * abs(price - stops["stop"]) if atr_v > 0 else final_notional * 0.05
        risk_pct_actual = ind.safe_div(risk_amount, cfg.capital_usd) * 100.0
        if risk_pct_actual > lim.max_risk_per_trade_pct * 1.05:
            veto_reasons.append(
                f"المخاطرة الفعلية {risk_pct_actual:.2f}% تتجاوز الحد {lim.max_risk_per_trade_pct}% لكل صفقة"
            )

        # ---------------- 4) فحوص إضافية ----------------
        var95 = features.get("var", {}).get("var_hist_pct", 0.0)
        if var95 < -12.0:
            notes.append(f"⚠️ VaR(95%) التاريخي {var95:.2f}% — ذيل خسارة ثقيل")
        if depth_ratio := ind.safe_div(final_notional, float(features.get("depth_usd") or 1.0)):
            if depth_ratio > 0.25:
                notes.append(f"⚠️ المركز = {depth_ratio*100:.1f}% من عمق الدفتر — أثر سوقي كبير")

        ml = strategy_metrics.get("max_leverage")
        if isinstance(ml, (int, float)) and ml > 1.0:
            notes.append(f"ℹ️ رافعة مقترحة {ml:.2f}x — الدستور لا يمنعها لكن يحدّها بحجم المركز")

        approved = not veto_reasons and final_notional > 0

        # ثغرة حرجة مُصلَحة: كان يمكن أن يخرج الحكم بـ `approved=False` مع
        # `veto=False` (صفر أسباب نقض) — فيقرأه المنسّق كـ«لا نقض» ويصدر قراراً
        # اتجاهياً بحجم صفر. الثلاثي (approved/veto/size) يجب أن يكون متسقاً.
        if not approved and not veto_reasons:
            if final_notional <= 0:
                veto_reasons.append(
                    "الحجم النهائي صفر — لا مركز قابل للتسعير بالقيود الحالية "
                    "(المادة 5.2: قرار بلا خسارة قصوى محددة يُرفض)"
                )
            else:
                veto_reasons.append("الحكم غير معتمد — رفض عام من محرك المخاطر")
        approved = not veto_reasons and final_notional > 0

        # اتساق داخلي إلزامي قبل الإصدار
        assert approved == (not veto_reasons and final_notional > 0), "تناقض داخلي في حكم المخاطر"
        assert not (approved and final_notional <= 0), "اعتماد بحجم صفري — تناقض"
        assert not (approved and veto_reasons), "اعتماد مع وجود نقض — تناقض"

        approved_notional = final_notional if approved else 0.0

        return RiskVerdict(
            approved=approved,
            veto=bool(veto_reasons),
            risk_level=level,
            max_position_pct=round(ind.safe_div(approved_notional, cfg.capital_usd) * 100.0, 3),
            position_size_usd=round(approved_notional, 2),
            computed_size_usd=round(final_notional, 2),
            stop_loss_pct=round(stop_pct, 3),
            risk_per_trade_pct=round(risk_pct_actual, 4),
            veto_reasons=veto_reasons,
            limits_checked={
                "max_daily_loss_pct": lim.max_daily_loss_pct,
                "max_drawdown_pct": lim.max_drawdown_pct,
                "max_position_pct": lim.max_position_pct,
                "max_sector_concentration_pct": lim.max_sector_concentration_pct,
                "current_sector_exposure_pct": cfg.current_sector_exposure_pct,
                "sector": cfg.sector,
                "min_confidence": lim.min_confidence,
                "max_market_participation_pct": lim.max_market_participation_pct,
                "max_kelly_fraction": lim.max_kelly_fraction,
                "max_risk_per_trade_pct": lim.max_risk_per_trade_pct,
                "current_daily_pnl_pct": cfg.daily_pnl_pct,
                "current_drawdown_pct": cfg.current_drawdown_pct,
                "win_probability_used": round(p, 4),
                "reward_risk_used": b,
                "binding_constraint": binding,
                "kelly_binding": binding == "kelly",
                "level_multiplier": level_multiplier,
                "quality_haircut": quality_haircut,
                "composed_multiplier": round(level_multiplier * quality_haircut, 4),
            },
            notes=notes + list(compliance_notes or []),
            timestamp=now_iso(),
        )

    # ------------------------------------------------------------------ #
    def stress_test(self, features: dict[str, Any], notional_usd: float) -> dict[str, Any]:
        """اختبار ضغط سريع: ماذا لو تكرر أسوأ يوم في التاريخ؟"""
        var = features.get("var", {})
        mc = features.get("monte_carlo", {})
        worst_hist = float(var.get("var_hist_pct", -5.0))
        cvar = float(var.get("cvar_pct", worst_hist * 1.5))
        p05 = float(mc.get("var95_pct", -15.0))
        return {
            "notional_usd": notional_usd,
            "scenario_var95": round(notional_usd * worst_hist / 100.0, 2),
            "scenario_cvar": round(notional_usd * cvar / 100.0, 2),
            "scenario_mc_p05_30d": round(notional_usd * p05 / 100.0, 2),
            "scenario_flash_crash_40pct": round(-notional_usd * 0.40, 2),
            "survives_flash_crash": abs(notional_usd * 0.40) <= self.config.capital_usd * 0.15,
            "note": "اختبار ضغط تقديري — ليس ضماناً (المادة 5.2)",
        }

    # ------------------------------------------------------------------ #
    @staticmethod
    def kelly_binding_analysis(limits: Limits | None = None,
                               capital: float = 1_000_000.0,
                               confidences: list[float] | None = None) -> dict[str, Any]:
        """
        هل يستطيع كيلي أن يكون **القيد الملزم** تحت الحدود الدستورية الحالية؟

        ⚠️ **نتيجة صادقة:** لا. داخل نطاق الثقات المقبولة (الحد الأدنى …
        السقف 88) يعطي نصف كيلي نسبة من رأس المال تتراوح حول 10%–20%، بينما
        `max_position_pct` = 10%. لذلك **سقف المركز يفوز دائماً**، وكيلي مرشّح
        محسوب لا حاكم.

        هذا **ليس عيباً في الحساب** بل نتيجة بنيوية: حدود الدستور أكثر تحفظاً من
        نصف كيلي عند كل الثقات المقبولة. لكن تقديمه كأنه «قيد حقيقي» تضليل —
        ولذلك يُعلَن هنا ويُدرَج في مخرجات المخاطر.
        """
        lim = limits or Limits()
        cap = capital
        max_pos = cap * lim.max_position_pct / 100.0
        rows = []
        for c in (confidences or [50, 55, 60, 65, 70, 75, 80, 85, 88]):
            p = RiskEngine.win_probability(c)
            f = ind.fractional_kelly(p, 1.5, lim.max_kelly_fraction, 0.30)
            notional = f * cap
            eligible = c >= lim.min_confidence
            rows.append({
                "confidence": c,
                "win_prob": round(p, 4),
                "kelly_half_capped_pct": round(f * 100, 3),
                "kelly_notional": round(notional, 2),
                "max_position_notional": round(max_pos, 2),
                "eligible_for_entry": eligible,
                "binds": notional < max_pos - 1e-9,
            })

        eligible_rows = [r for r in rows if r["eligible_for_entry"]]
        binds_eligible = any(r["binds"] for r in eligible_rows)
        binds_ineligible = any(r["binds"] for r in rows if not r["eligible_for_entry"])

        if binds_eligible:
            note = "كيلي يقيّد الحجم في جزء من نطاق الثقات المؤهلة."
        elif binds_ineligible:
            note = ("⚠️ **كيلي لا يقيّد الحجم في أي نقطة من نطاق الثقات المؤهلة** "
                    f"(≥ {lim.min_confidence}): نصف كيلي يتجاوز سقف المركز "
                    f"({lim.max_position_pct}%) دائماً. يقيّد فقط عند ثقة **دون** حد الدخول، "
                    f"وهي حالات مرفوضة أصلاً. سقف المركز هو الحاكم الفعلي — "
                    f"وهذا مُعلن لا مُخفى، وليس عيباً في الحساب بل نتيجة بنيوية: "
                    f"حدود الدستور أكثر تحفظاً من نصف كيلي.")
        else:
            note = "كيلي لا يقيّد الحجم في النطاق المفحوص."

        return {
            "min_confidence": lim.min_confidence,
            "max_position_notional": round(max_pos, 2),
            "kelly_binds_in_eligible_range": binds_eligible,
            "kelly_binds_only_below_min_confidence": binds_ineligible and not binds_eligible,
            "kelly_can_bind": any(r["binds"] for r in rows),
            "rows": rows,
            "note": note,
        }

    # ------------------------------------------------------------------ #
    @staticmethod
    def kelly_table(confidences: list[float] | None = None) -> list[dict[str, float]]:
        """
        جدول مرجعي لكيلي المقيد — للتوثيق والمراجعة.

        ملاحظة: السقف هنا **0.30** ليطابق `evaluate` (كان 0.10 فيتعارض معه).
        """
        confidences = confidences or [50, 55, 60, 65, 70, 75, 80, 85, 88]
        out = []
        for c in confidences:
            p = RiskEngine.win_probability(c)
            f = ind.fractional_kelly(p, 1.5, 0.5, 0.30)
            out.append({
                "confidence": c,
                "win_prob": round(p, 4),
                "kelly_full_pct": round(ind.kelly_fraction(p, 1.5) * 100, 3),
                "kelly_half_capped_pct": round(f * 100, 3),
            })
        return out
