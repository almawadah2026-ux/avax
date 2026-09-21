"""
الوكيل 15 — الذاكرة والسجل.

وظيفته ثلاثية:
    1. كتابة الدورة في سجل غير قابل للتعديل (المادة 7.1, 7.2)
    2. توفير أوزان الأداء التاريخي للوكلاء (المادة 7.4)
    3. إتاحة المراجعة البعدية (Post-Mortem) بعد انتهاء أفق القرار (المادة 7.3)

هو الوكيل الوحيد الذي **لا يُقيَّم ولا يُنقَض** — لأنه لا يصدر أحكاماً سوقية.
"""

from __future__ import annotations

from typing import Any

from ..contracts import AgentOpinion, Authority, Layer, Strength, now_iso
from ..journal.store import JournalStore
from .base import AgentContext, BaseAgent


class MemoryAgent(BaseAgent):
    id, name_ar, name_en = "15", "وكيل الذاكرة والسجل", "Memory & Journal Agent"
    layer, authority, domain = Layer.MEMORY, Authority.RECORD, "journal"
    horizon = "دائم"
    file = "agents/15-memory-journal.md"

    # ------------------------------------------------------------------ #
    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        store: JournalStore | None = ctx.shared.get("journal_store")
        decision = ctx.shared.get("decision")

        if store is None:
            return AgentOpinion.abstain_opinion(
                self.id, self.name_ar, "لا سجل مُهيَّأ — لا يمكن التسجيل"
            )
        if decision is None:
            return AgentOpinion.abstain_opinion(
                self.id, self.name_ar, "لا قرار مُصدر — لا شيء يستحق التسجيل"
            )

        proposal = ctx.shared.get("proposal", {})
        verdict = ctx.shared.get("risk_verdict")
        compliance = ctx.shared.get("compliance")

        record = store.append_decision(decision, extras={
            "constitution_fingerprint": store.constitution_fingerprint(
                ctx.config.constitution_path),
            "snapshot_meta": {
                "asset": ctx.snapshot.asset,
                "source": ctx.snapshot.source,
                "timestamp": ctx.snapshot.timestamp,
                **{k: v for k, v in (ctx.snapshot.meta or {}).items()},
            },
            "opinions_digest": [
                {
                    "agent_id": op.agent_id,
                    "agent_name": op.agent_name,
                    "direction": op.direction,
                    "confidence": op.confidence,
                    "net_confidence": round(op.net_confidence, 2),
                    "best_tier": op.best_tier,
                    "abstain": op.abstain,
                    "thesis": op.thesis,
                }
                for op in ctx.opinions.values()
            ],
            "proposal": proposal,
            "risk_verdict": verdict.to_dict() if verdict else None,
            "compliance": compliance.to_dict() if compliance else None,
            "post_decision_audit": ctx.shared.get("post_decision_audit"),
            "law_audit": ctx.law.summary(),
            "constitution_version": "1.0",
            "post_mortem": {"status": "pending", "due_horizon": decision.horizon,
                            "agent_scores": []},
            "recorded_at": now_iso(),
        })

        chain = store.verify_chain()
        weights = store.agent_weights()
        calibration = store.calibration()
        # المادة 7.1 — «JSON + ملخص Markdown»
        markdown_path = store.write_markdown_summary()
        ctx.shared["journal_record"] = record
        ctx.shared["agent_weights"] = weights
        ctx.shared["calibration"] = calibration

        evidence = [
            self.ev(ctx, f"سُجّل القرار {decision.decision_id} في السجل برقم تسلسلي "
                         f"{record.sequence}", "journal/desk_journal.jsonl", "derived",
                    Strength.HIGH.value, float(record.sequence)),
            self.ev(ctx, f"بصمة السجل (hash) {record.record_hash[:24]}… مربوط بالسجل السابق "
                         f"{record.previous_hash[:16]}…", "journal/hash-chain", "derived",
                    Strength.HIGH.value, None),
            self.ev(ctx, f"سلامة السلسلة: {chain['records']} سجلاً، "
                         f"{'سليمة' if chain['valid'] else 'مكسورة'}"
                         + (f"، {chain['corrupt_lines']} سطر تالف" if chain["corrupt_lines"] else ""),
                    "journal/chain-verification", "derived", Strength.HIGH.value, float(chain["records"])),
            self.ev(ctx, f"أوزان الأداء التاريخي المحمّلة: "
                         f"{', '.join(f'{k}→{v}' for k, v in weights.items()) or 'لا سجل سابق كافٍ (الكل 1.0)'}",
                    "journal/agent-weights", "derived", Strength.MEDIUM.value, None),
            self.ev(ctx, f"عدد الآراء المسجّلة في هذه الدورة: {len(ctx.opinions)}",
                    "journal/cycle-digest", "derived", Strength.MEDIUM.value, float(len(ctx.opinions))),
            self.ev(ctx, f"معايرة الثقة (Brier) على {calibration['samples']} مراجعة بعدية: "
                         f"{calibration['brier_score'] if calibration['brier_score'] is not None else '—'} "
                         f"(0.25 = تخمين عشوائي) — {calibration['verdict']}",
                    "journal/calibration-brier", "derived", Strength.HIGH.value,
                    calibration["brier_score"]),
        ]

        thesis = (
            f"سُجّلت الدورة رقم {record.sequence} بنجاح؛ السلسلة "
            f"{'سليمة' if chain['valid'] else 'مكسورة'} عند {chain['records']} سجلاً، "
            f"والمراجعة البعدية مستحقة عند أفق «{decision.horizon}»."
        )
        invalidation = (
            "يُبطل هذا التسجيل إذا فشل التحقق من السلسلة (تعديل خارجي على الملف)، "
            "أو إذا لم تُنفَّذ المراجعة البعدية عند انتهاء الأفق (المادة 7.3)."
        )
        dissent = (
            "أقوى ما يخالف هذا التسجيل: السجل يحفظ ما **قيل** لا ما **صحّ**. "
            "ودون مراجعة بعدية فعلية يتحول السجل إلى أرشيف لا ذاكرة، "
            "والدستور يشترط المراجعة لا الكتابة فقط."
        )

        return self.make(
            ctx, 0.0, thesis, evidence, invalidation, dissent,
            metrics={
                "record_id": record.record_id,
                "sequence": record.sequence,
                "record_hash": record.record_hash,
                "previous_hash": record.previous_hash,
                "chain_valid": chain["valid"],
                "total_records": chain["records"],
                "agent_weights": weights,
                "post_mortem_due": decision.horizon,
                "markdown_summary": str(markdown_path),
                "calibration": calibration,
            },
            dead_zone=1.0,
            notes=[
                "ℹ️ السجل غير قابل للتعديل — التصحيح يكون بإدخال جديد يشير للقديم (المادة 7.2)",
                f"ℹ️ المراجعة البعدية مستحقة عند أفق: {decision.horizon} (المادة 7.3)",
                f"ℹ️ ملخّص Markdown مُحدَّث: {markdown_path.name} (المادة 7.1)",
            ],
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def record_post_mortem(
        store: JournalStore,
        decision_id: str,
        outcome: str,
        agent_scores: list[dict[str, Any]],
        lesson: str = "",
    ) -> dict[str, Any]:
        """
        مراجعة بعدية — المادة 7.3.

        تُسجَّل كإدخال جديد (لا تعديل على القديم)، وتحمل نتيجة كل وكيل.
        """
        record = store.append({
            "post_mortem": {
                "decision_id": decision_id,
                "outcome": outcome,
                "agent_scores": agent_scores,
                "lesson": lesson,
                "reviewed_at": now_iso(),
            }
        }, kind="post_mortem")
        return {
            "record_id": record.record_id,
            "sequence": record.sequence,
            "updated_weights": store.agent_weights(),
        }


MEMORY_AGENTS: tuple[type[BaseAgent], ...] = (MemoryAgent,)
