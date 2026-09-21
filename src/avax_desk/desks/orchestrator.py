"""
الوكيل 14 — المنسّق / مدير المحفظة.

صاحب **القرار**، لكنه ليس صاحب سلطة مطلقة:
    • لا يستطيع تجاوز نقض المخاطر (المادة 5.1)
    • لا يستطيع إصدار قرار بلا رأي مخالف مسجّل (المادة 6.3)
    • لا يستطيع إنتاج دليل أصلي (المادة 1.4)

عمله: تجميع، ترجيح، ثم **الاعتراف بعدم اليقين** بصيغة قابلة للتدقيق.
"""

from __future__ import annotations

from typing import Any

from .. import indicators as ind
from ..contracts import (
    Action,
    AgentOpinion,
    Authority,
    Direction,
    DeskDecision,
    Layer,
    Strength,
)
from .base import AgentContext, BaseAgent

#: منطقة ميتة أعلى من الوكلاء الأفراد: القرار المجمّع يجب أن يكون واضحاً
DECISION_DEAD_ZONE = 0.10


class OrchestratorAgent(BaseAgent):
    id, name_ar, name_en = "14", "المنسّق / مدير المحفظة", "Orchestrator / PM Agent"
    layer, authority, domain = Layer.DECISION, Authority.DECISION, "decision"
    horizon = "أيام إلى أسابيع"
    file = "agents/14-orchestrator.md"

    # ------------------------------------------------------------------ #
    # المرحلة 1: المقترح
    # ------------------------------------------------------------------ #
    def propose(self, ctx: AgentContext) -> dict[str, Any]:
        """
        تجميع آراء طبقة المعرفة بترجيح مركّب:
            الوزن = الثقة الصافية × قوة طبقة الدليل × خصم التحقق × وزن الأداء التاريخي
        """
        knowledge = ctx.knowledge_opinions()

        validation_op = ctx.opinions.get("09")
        validation_metrics = validation_op.metrics if validation_op else {}
        ctx.shared["validation"] = validation_metrics
        discounts: dict[str, float] = validation_metrics.get("agent_discounts", {})
        validated = bool(validation_metrics.get("validated", False))

        history_weights: dict[str, float] = ctx.shared.get("agent_weights", {}) or {}
        merged: dict[str, float] = {}
        for aid in set(discounts) | set(history_weights):
            merged[aid] = float(discounts.get(aid, 1.0)) * float(history_weights.get(aid, 1.0))

        agg = ind.weighted_evidence_score(knowledge, weights=merged)
        score = float(agg["score"])

        direction = ("bullish" if score > DECISION_DEAD_ZONE
                     else "bearish" if score < -DECISION_DEAD_ZONE
                     else "neutral")

        active = [o for o in knowledge if not o.abstain and o.direction != Direction.NEUTRAL.value]
        supporters = [o for o in active if o.direction == direction] if direction != "neutral" else []
        opposers = [o for o in active if o.direction != direction] if direction != "neutral" else []

        agreement = ind.safe_div(len(supporters), len(active), 0.0)
        base_conf = ind.mean([o.net_confidence for o in supporters]) if supporters else 0.0

        # الثقة المجمّعة = مزيج مرجّح من ثلاثة مكوّنات مستقلة:
        #   45% متوسط ثقة المؤيدين (جودة كل رأي)
        #   30% اتساع الاتفاق (هل هذا رأي جماعة أم رأي فرد؟)
        #   25% قوة الإشارة المرجّحة (هل الحافة clear أم هامشية؟)
        signal_strength = ind.clamp(abs(score) / 0.50, 0.0, 1.0)
        confidence = (
            0.45 * base_conf
            + 0.30 * (100.0 * agreement)
            + 0.25 * (100.0 * signal_strength)
        )

        # عقوبات دستورية **جمعية** لا ضربية: الخصم بالنقاط قابل للتدقيق والتفسير،
        # أما الضرب فيُسقط الثقة تحت الحد الأدنى دائماً ويمنع أي قرار.
        penalties: list[str] = []
        red = ctx.opinions.get("10")
        if red and red.metrics.get("consensus_direction") == direction and direction != "neutral":
            confidence -= 4.0
            penalties.append("خصم 4 نقاط — حجة مضادة من محامي الشيطان على نفس الاتجاه")
        if not validated:
            confidence -= 6.0
            penalties.append("خصم 6 نقاط — الإشارة لم تجتز معايير الجودة في قانون التحقق (المادة 4.1)")
        if direction != "neutral" and len(supporters) < 3:
            confidence -= 5.0
            penalties.append("خصم 5 نقاط — أقل من 3 وكلاء مؤيدين")
        if not active:
            confidence = 0.0

        # -- المادة 3.2: أولوية الدليل الأولي -----------------------------
        # ثغرة مُصلَحة: `arbitrate_evidence` كان يُستدعى ولا يؤثر على القرار،
        # فيمكن أن يفوز اتجاه تسنده ثلاثة أدلة طبقة 4 على دليل واحد طبقة 1.
        primary = ctx.law.primary_evidence_conflict(knowledge, direction)
        if primary.get("conflict"):
            confidence -= 15.0
            penalties.append(
                f"خصم 15 نقطة — تعارض مع دليل أولي (المادة 3.2): {primary['note']}"
            )

        confidence = round(ind.clamp(confidence, 0.0, 88.0), 2)

        proposal = {
            "direction": direction,
            "score": round(score, 4),
            "confidence": confidence,
            "agreement": round(agreement, 4),
            "supporters": [o.agent_id for o in supporters],
            "opposers": [o.agent_id for o in opposers],
            "abstainers": [o.agent_id for o in knowledge if o.abstain],
            "base_confidence": round(base_conf, 2),
            "penalties": penalties,
            "aggregation": agg,
            "validation_discounts": discounts,
            "history_weights": history_weights,
            "validated": validated,
            "primary_evidence_conflict": primary,
        }
        ctx.shared["proposal"] = proposal
        return proposal

    # ------------------------------------------------------------------ #
    # المرحلة 2: القرار النهائي
    # ------------------------------------------------------------------ #
    def finalize(self, ctx: AgentContext) -> DeskDecision:
        """يبني القرار النهائي بعد حكم المخاطر وتقرير الالتزام."""
        proposal = ctx.shared.get("proposal") or self.propose(ctx)
        verdict = ctx.shared.get("risk_verdict")
        compliance = ctx.shared.get("compliance")
        plan = ctx.shared.get("execution_plan")
        engine = ctx.shared.get("risk_engine")

        direction = proposal["direction"]
        confidence = float(proposal["confidence"])
        price = ctx.features["price"]
        atr_v = ctx.features["atr14"]

        blocks: list[str] = []
        # المادة 5.2 — قرار بلا حكم مخاطرة لا يُصدر إطلاقاً.
        # (ثغرة مُصلَحة: غياب `risk_verdict` كان يُنتج LONG بحجم 0 بدل حجب.)
        if verdict is None:
            blocks.append("لا حكم مخاطرة — يُحظر إصدار أي قرار (المادة 5.2)")
        if compliance is not None and not compliance.compliant:
            blocks.append("حجب من وكيل الالتزام (المادة 8)")
        if verdict is not None and verdict.veto:
            blocks.append("نقض من وكيل المخاطر (المادة 5.1)")
        # ثغرة مُصلَحة: كان الفحص يقتصر على `veto` دون `approved`. أي مسار
        # يصفّر الحجم (رأس مال صفري، عمق مفقود) كان يُنتج قراراً اتجاهياً بحجم صفر.
        if verdict is not None and not verdict.approved:
            blocks.append("وكيل المخاطر لم يعتمد أي حجم (المادة 5.2)")
        if direction == "neutral":
            blocks.append("لا اتجاه محدد — الامتناع هو القرار الصحيح (المادة 0.4)")
        # ربط قانون كان معرّفاً بلا مستدعٍ: `law.eligible_for_entry` (المادة 5.3)
        if not ctx.law.eligible_for_entry(confidence):
            blocks.append(
                f"الثقة المجمّعة {confidence:.1f} دون الحد الأدنى "
                f"{ctx.config.limits.min_confidence} (المادة 5.3)"
            )
        if ctx.config.halted:
            blocks.append("الديسك موقوف (المادة 9.3)")
        # المادة 8.3 — تسرّب مستقبلي مُكتشَف يمنع القرار لا يُسجَّل فقط.
        validation_metrics = ctx.shared.get("validation") or {}
        if validation_metrics.get("lookahead_clean") is False:
            blocks.append("رُصد تسرّب بيانات مستقبلية — يُحظر القرار (المادة 8.3)")

        # المادة 5.3 — إعادة تحقق دفاعية من سقف المركز قبل الإصدار.
        # (كان `finalize` يأخذ حجم محرك المخاطر كما هو بلا فحص ثانٍ.)
        max_allowed = ctx.config.capital_usd * ctx.config.limits.max_position_pct / 100.0
        if verdict is not None and verdict.position_size_usd > max_allowed + 1e-6:
            blocks.append(
                f"حجم المعتمد ${verdict.position_size_usd:,.0f} يتجاوز سقف المركز "
                f"${max_allowed:,.0f} (المادة 5.3)"
            )

        # المادة 3.2 — تعارض مع دليل أولي (طبقة 1 أو 2) ⇒ الدليل الأولي يرجّح
        if (proposal.get("primary_evidence_conflict") or {}).get("conflict"):
            blocks.append(
                "تعارض مع دليل من الطبقة 1 أو 2 — الدليل الأولي يرجّح على الأضعف (المادة 3.2)"
            )

        # المادة 8.7 — منع الالتفاف على الحدود بتقسيم المراكز
        proposed_notional = float(verdict.position_size_usd) if verdict else 0.0
        exposure_violations = ctx.law.aggregate_exposure_violations(
            ctx.config.open_positions, proposed_notional, ctx.config.sector,
            ctx.config.capital_usd, ctx.config.limits,
        )
        ctx.shared["exposure_violations"] = [v.to_dict() for v in exposure_violations]
        if any(v.severity == "error" for v in exposure_violations):
            blocks.append("تجاوز التعرّض الكلي أو القطاعي بتقسيم المراكز (المادة 8.7)")

        action = {
            "bullish": Action.LONG.value,
            "bearish": Action.SHORT.value,
        }.get(direction, Action.ABSTAIN.value)
        if blocks:
            action = Action.ABSTAIN.value

        # -- المستويات ---------------------------------------------------
        stops = {"stop": price, "target1": price, "target2": price}
        if engine is not None:
            stops = engine.suggest_stops(price, atr_v, direction)
        entry_zone = [round(price * 0.9975, 6), round(price * 1.0025, 6)]

        # -- الرأي المخالف (المادة 6) ------------------------------------
        opposing_ids = list(proposal["opposers"])
        strongest_dissent, dissent_source = self._strongest_dissent(ctx, proposal)
        if not opposing_ids and strongest_dissent:
            opposing_ids = ["10"]   # محامي الشيطان دائماً مخالف مسجّل

        groupthink = ctx.law.flag_groupthink(ctx.knowledge_opinions())

        size_usd = float(verdict.position_size_usd) if (verdict and not verdict.veto) else 0.0
        # ثغرة مُصلَحة: القرار المحجوب كان يحتفظ بحجم مخاطر موجب، فيُطبع
        # «حجم المركز: $37,923» تحت عنوان «الامتناع» ويُسجَّل كذلك. قرار ممتنع
        # حجمه صفر بالتعريف.
        if action == Action.ABSTAIN.value:
            size_usd = 0.0

        # نوع الامتناع — يُميّز «لا حافة» من «نقض» من «حجب» من «إيقاف».
        # (كان التمييز يُمحى لأن الكل يُسجَّل ABSTAIN بلا تفصيل.)
        # الترتيب مقصود: غياب الاتجاه يُصنَّف `no_edge` حتى لو أضاف محرك المخاطر
        # سبب نقض تابعاً (لأن «لا اتجاه» هو السبب الجذري لا عرضه).
        abstention_kind = ""
        if action == Action.ABSTAIN.value:
            if ctx.config.halted:
                abstention_kind = "halted"
            elif direction == "neutral":
                abstention_kind = "no_edge"
            elif compliance is not None and not compliance.compliant:
                abstention_kind = "compliance_block"
            elif verdict is not None and (verdict.veto or not verdict.approved):
                abstention_kind = "risk_veto"
            else:
                abstention_kind = "no_edge"

        rationale = self._compose_rationale(ctx, proposal, verdict, compliance, blocks)

        decision = DeskDecision(
            decision_id=DeskDecision.new_id(),
            asset=ctx.snapshot.asset,
            action=action,
            confidence=confidence,
            horizon=self.horizon,
            invalidation=self._decision_invalidation(ctx, direction, stops, price),
            rationale=rationale,
            supporting_agents=list(proposal["supporters"]),
            opposing_agents=opposing_ids,
            abstaining_agents=list(proposal["abstainers"]),
            strongest_dissent=strongest_dissent,
            dissent_source=dissent_source,
            abstention_kind=abstention_kind,
            blocks=list(blocks),
            groupthink_flag=bool(leader := groupthink.get("groupthink", groupthink.get("flag", False))),
            entry_zone=entry_zone if action != Action.ABSTAIN.value else [],
            stop_price=round(stops["stop"], 6) if action != Action.ABSTAIN.value else None,
            targets=([round(stops["target1"], 6), round(stops["target2"], 6)]
                     if action != Action.ABSTAIN.value else []),
            size_usd=round(size_usd, 2),
            risk_verdict=verdict,
            execution_plan=plan,
            compliance=compliance,
            evidence_summary=self._evidence_summary(ctx),
        )
        ctx.shared["decision"] = decision
        ctx.shared["groupthink"] = groupthink
        return decision

    # ------------------------------------------------------------------ #
    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        """رأي المنسّق — يعكس القرار النهائي بدل أن يضيف رأياً سوقياً جديداً (المادة 1.4)."""
        decision: DeskDecision | None = ctx.shared.get("decision")
        if decision is None:
            decision = self.finalize(ctx)

        proposal = ctx.shared.get("proposal", {})
        groupthink = ctx.shared.get("groupthink", {})
        verdict = ctx.shared.get("risk_verdict")

        decision_txt = {
            Action.LONG.value: "فتح مركز شراء",
            Action.SHORT.value: "فتح مركز بيع",
            Action.FLAT.value: "البقاء خارج السوق",
            Action.ABSTAIN.value: "الامتناع",
        }[decision.action]

        evidence = [
            self.ev(ctx, f"الدرجة المجمّعة {proposal.get('score')} من "
                         f"{len(proposal.get('supporters', []))} وكيل مؤيد و"
                         f"{len(proposal.get('opposers', []))} معارض",
                    f"aggregation/agents-{'+'.join(sorted(ctx.opinions))}", "derived",
                    Strength.HIGH.value, proposal.get("score")),
            self.ev(ctx, f"نسبة الاتفاق {proposal.get('agreement', 0.0)*100:.1f}% — "
                         f"{groupthink.get('note', '')}",
                    f"aggregation/agents-{'+'.join(sorted(ctx.opinions))}", "derived",
                    Strength.HIGH.value, proposal.get("agreement")),
            self.ev(ctx, f"الثقة المجمّعة {decision.confidence:.1f} بعد تطبيق "
                         f"{len(proposal.get('penalties', []))} خصماً دستورياً",
                    f"aggregation/agents-{'+'.join(sorted(ctx.opinions))}", "derived",
                    Strength.HIGH.value, decision.confidence),
            self.ev(ctx, f"حكم المخاطر: {'نقض' if (verdict and verdict.veto) else 'موافقة بحجم ' + f'${decision.size_usd:,.0f}'}",
                    "aggregation/risk-verdict", "derived", Strength.HIGH.value, decision.size_usd),
            self.ev(ctx, f"أقوى رأي مخالف مسجّل: {decision.strongest_dissent[:160]}",
                    f"aggregation/dissent-from-{decision.dissent_source}", "derived",
                    Strength.HIGH.value, None),
        ]

        score = 0.0
        thesis = (
            f"القرار النهائي: **{decision_txt}** على {decision.asset} بثقة {decision.confidence:.1f}/100. "
            f"المبرر: {decision.rationale[:260]}"
        )
        invalidation = decision.invalidation
        dissent = (
            f"الرأي المخالف محفوظ: {decision.strongest_dissent} "
            "— قرار بلا رأي مخالف مسجّل يُعاد للمنسّق إلزامياً (المادة 6.3)."
        )

        op = self.make(
            ctx, score, thesis, evidence, invalidation, dissent,
            metrics={
                "action": decision.action,
                "decision_id": decision.decision_id,
                "confidence": decision.confidence,
                # سلّم الثقة (المادة 7.1 من القالب) — كان معرّفاً بلا مستدعٍ
                "confidence_band": ctx.law.confidence_band(decision.confidence)[0],
                "eligible_for_entry": ctx.law.eligible_for_entry(decision.confidence),
                "size_usd": decision.size_usd,
                "groupthink": groupthink,
                "penalties": proposal.get("penalties", []),
                "primary_evidence_conflict": proposal.get("primary_evidence_conflict", {}),
                "binding_constraint": (verdict.limits_checked.get("binding_constraint") if verdict else None),
            },
            dead_zone=1.0,
            notes=["ℹ️ هذا رأي المنسّق النهائي — لا يضيف دليلاً جديداً (المادة 1.4)"],
        )
        return op

    # ------------------------------------------------------------------ #
    # أدوات داخلية
    # ------------------------------------------------------------------ #
    def _strongest_dissent(self, ctx: AgentContext,
                           proposal: dict[str, Any]) -> tuple[str, str]:
        """
        يعيد (نص الرأي المخالف، مصدره).

        المصدر مهم: «agent» مخالفة حقيقية من وكيل، و«fallback» نص احتياطي مبرمج.
        التمييز يمنع الفحص الشكلي في المادة 6.3 (كان الحقل لا يفرغ أبداً).
        """
        red = ctx.opinions.get("10")
        parts: list[str] = []
        source = "none"

        if red and not red.abstain:
            counter = red.metrics.get("counter_thesis", "")
            if counter:
                parts.append(counter)
                source = "agent"
            weaknesses = red.metrics.get("weaknesses", [])
            if weaknesses:
                parts.append(weaknesses[0])
                source = "agent"

        for oid in proposal.get("opposers", [])[:2]:
            op = ctx.opinions.get(oid)
            if op and not op.abstain:
                parts.append(f"[{oid} {op.agent_name}] {op.thesis}")
                source = "agent"

        if not parts:
            parts.append(
                "لم يُسجَّل معارض مباشر؛ محامي الشيطان أشار إلى أن الأدلة المؤيدة "
                "كثيفة لكن غير محصّنة ضد الانقلاب المفاجئ في السيولة."
            )
            source = "fallback"
        return " | ".join(parts)[:1200], source

    @staticmethod
    def _evidence_summary(ctx: AgentContext) -> list[dict[str, Any]]:
        """أقوى 8 أدلة مرتبة حسب هرمية المادة 3.1."""
        items: list[dict[str, Any]] = []
        for op in ctx.knowledge_opinions():
            if op.abstain:
                continue
            for e in op.evidence:
                items.append({
                    "agent_id": op.agent_id,
                    "tier": e.tier,
                    "tier_label": e.tier_label,
                    "claim": e.claim,
                    "source": e.source,
                    "strength": e.strength,
                })
        items.sort(key=lambda x: (x["tier"], 0 if x["strength"] == "high" else 1))
        return items[:8]

    def _decision_invalidation(self, ctx: AgentContext, direction: str,
                               stops: dict[str, float], price: float) -> str:
        if direction == "neutral":
            return ("يبقى الامتناع صحيحاً حتى يخرج متوسط الأدلة المرجّح عن المنطقة الميتة "
                    f"(±{DECISION_DEAD_ZONE}) أو يظهر دليل من الطبقة 1 أو 2.")
        verb = "دون" if direction == "bullish" else "فوق"
        return (
            f"يُبطل هذا القرار عند إغلاق {verb} مستوى الوقف {stops['stop']:.4f}، "
            f"أو عند انقلاب التمويل/التدفقات الأونشين إلى الاتجاه المعاكس، "
            f"أو عند تجاوز الخسارة اليومية {ctx.config.limits.max_daily_loss_pct}% (إيقاف آلي)."
        )

    @staticmethod
    def _compose_rationale(ctx: AgentContext, proposal: dict[str, Any],
                           verdict: Any, compliance: Any, blocks: list[str]) -> str:
        lines: list[str] = []
        if blocks:
            lines.append("⛔ الامتناع الإلزامي: " + "؛ ".join(blocks) + ".")
        else:
            lines.append(
                f"تجميع مرجّح لـ {len(proposal['supporters']) + len(proposal['opposers'])} رأياً "
                f"باتجاه {proposal['direction']} بدرجة {proposal['score']:+.3f}، "
                f"واتفاق {proposal['agreement']*100:.0f}%."
            )
        if proposal.get("penalties"):
            lines.append("خصومات مطبقة: " + "؛ ".join(proposal["penalties"]) + ".")
        if verdict is not None:
            lines.append(
                f"المخاطر: مستوى {verdict.risk_level}، حجم ${verdict.position_size_usd:,.0f} "
                f"({verdict.max_position_pct:.2f}%)، وقف {verdict.stop_loss_pct:.2f}%، "
                f"القيد الملزم «{verdict.limits_checked.get('binding_constraint')}»."
            )
        if compliance is not None:
            lines.append(
                f"الالتزام: {'متوافق' if compliance.compliant else 'غير متوافق'} "
                f"({len(compliance.violations)} مخالفة، {compliance.checked_agents} رأياً مفحوصاً)."
            )
        lines.append(f"المصدر: {'بيانات حيّة' if ctx.snapshot.source == 'live' else 'بيانات اصطناعية (تدريب)'}.")
        return " ".join(lines)


DECISION_AGENTS: tuple[type[BaseAgent], ...] = (OrchestratorAgent,)
