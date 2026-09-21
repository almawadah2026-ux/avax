"""
واجهة التشغيل — تشغيل دورة كاملة لديسك أفالانش.

الاستخدام:
    python -m avax_desk.cli --scenario bull
    python -m avax_desk.cli --live --capital 5000000
    python -m avax_desk.cli --audit-roster
    python -m avax_desk.cli --verify-journal
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DeskConfig, Limits
from .contracts import Action, DeskDecision, RiskLevel
from .desks.base import AgentContext, compute_features
from .desks.control import CONTROL_AGENTS, ComplianceAgent
from .desks.knowledge import KNOWLEDGE_AGENTS
from .desks.memory import MemoryAgent
from .desks.orchestrator import OrchestratorAgent
from .desks.validation import VALIDATION_AGENTS
from .journal.store import JournalStore
from .law import LawEngine
from .registry import audit_roster, consistency_report

SEP = "─" * 74
SEP2 = "═" * 74


# ==========================================================================
# المشغّل
# ==========================================================================

class DeskRunner:
    """يشغّل دورة قرار كاملة وفق تسلسل الدستور."""

    def __init__(self, config: DeskConfig | None = None,
                 journal_path: str | Path = "journal/desk_journal.jsonl",
                 write_journal: bool = True) -> None:
        self.config = config or DeskConfig()
        self.write_journal = write_journal
        self.store = JournalStore(journal_path)
        self.law = LawEngine(self.config.limits)
        self.trace: list[str] = []

    # ------------------------------------------------------------------ #
    def _log(self, msg: str) -> None:
        self.trace.append(msg)
        if self.config.verbose:
            print(msg)

    def _load_snapshot(self) -> Any:
        if self.config.live_data:
            # المصدر الحيّ: CoinMarketCap أولاً (اقتباس + ماكرو + هيمنة BTC)،
            # ثم CoinGecko للسلسلة الزمنية، ثم Binance/alternative.me.
            # عند فشل كل ذلك نتراجع للاصطناعي **معلنين السبب** (المادة 3.3).
            try:
                from .backend.supabase_client import load_dotenv
                from .data.coinmarketcap import CoinMarketCapFeed
                dotenv = load_dotenv()
                key = dotenv.get("CMC_API_KEY") or os.environ.get("CMC_API_KEY", "")
                if key:
                    cmc = CoinMarketCapFeed(api_key=key, days=self.config.lookback_days,
                                            timeout=self.config.network_timeout,
                                            fallback_seed=self.config.seed)
                    snap = cmc.fetch()
                    for d in cmc.degraded[:3]:
                        self._log(f"  ⚠️ {str(d)[:110]}")
                    if snap.source == "live":
                        return snap
                    self._log("  ⚠️ CMC لم يُنتج بيانات حيّة — أنتقل إلى الجالب الاحتياطي")
            except Exception as exc:  # noqa: BLE001
                self._log(f"  ⚠️ تعذّر CMC: {type(exc).__name__}: {str(exc)[:110]}")

            from .data.live import LiveFeed
            feed = LiveFeed(days=self.config.lookback_days, timeout=self.config.network_timeout,
                            fallback_seed=self.config.seed)
            snap = feed.fetch()
            if feed.degraded:
                self._log(f"  ⚠️ مصادر متعثرة: {'; '.join(str(d)[:90] for d in feed.degraded[:3])}")
            return snap
        from .data.synthetic import SyntheticFeed
        return SyntheticFeed(
            seed=self.config.seed,
            days=self.config.lookback_days,
            scenario=self.config.scenario,
        ).generate()

    # ------------------------------------------------------------------ #
    def _halt_state_path(self) -> Path:
        return Path(self.store.path).parent / "halt_state.json"

    def _load_halt_state(self) -> None:
        """
        استعادة الإيقاف عبر العمليات — المادة 5.4 («يتوقف الديسك آلياً **لبقية اليوم**»).

        ثغرة مُصلَحة: كان `halted` في الذاكرة فقط، فتشغيل جديد في نفس اليوم يعاود
        التداول كأن شيئاً لم يكن. الآن يُحفظ الإيقاف بوقت انتهاء (نهاية يوم UTC).

        ملاحظة عزل: تُتجاهل حالة الإيقاف كلياً في وضع `--no-journal`، لأن غياب
        السجل يعني غياب الحالة المستدامة — وإلا تسرّب إيقاف اختبار إلى تشغيل آخر
        (وهو ما حدث فعلاً أثناء التدقيق).
        """
        if not self.write_journal:
            return
        p = self._halt_state_path()
        # رُفع الإيقاف صراحةً (`--resume`) ⇒ لا يُعاد تطبيقه من الملف
        if self.config.resume_note:
            p.unlink(missing_ok=True)
            return
        if not p.exists() or self.config.halted:
            return
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        until = state.get("halted_until")
        if not until:
            return
        try:
            if datetime.now(timezone.utc) < datetime.fromisoformat(until):
                self.config.halted = True
                self.config.halt_reason = state.get("reason", "إيقاف مستعاد من ملف الحالة")
                self.config.halted_at = state.get("halted_at", "")
                self._log(f"  🔴 إيقاف مستعاد من حالة محفوظة حتى {until[:19]}Z "
                          f"(المادة 5.4) — استخدم --resume للرفع")
            else:
                p.unlink(missing_ok=True)     # انتهى اليوم ⇒ يُرفع تلقائياً
        except ValueError:
            return

    def _save_halt_state(self) -> None:
        if not self.write_journal:
            return
        p = self._halt_state_path()
        try:
            if self.config.halted:
                end_of_day = datetime.now(timezone.utc).replace(
                    hour=23, minute=59, second=59, microsecond=0)
                p.write_text(json.dumps({
                    "halted_until": end_of_day.isoformat(timespec="seconds"),
                    "reason": self.config.halt_reason,
                    "halted_at": self.config.halted_at,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                p.unlink(missing_ok=True)     # رُفع الإيقاف ⇒ لا حالة معلّقة
        except OSError:
            pass

    def run(self) -> dict[str, Any]:
        cfg = self.config
        # تصفير سجل المخالفات قبل كل دورة — وإلا حملت تقاريرُ الدورة الحالية
        # مخالفاتِ دورة سابقة عند إعادة استخدام نفس المُشغّل (ثغرة مُصلَحة).
        self.law.audit_log.clear()
        self._load_halt_state()
        self._log(SEP2)
        self._log("  🏔️  ديسك أفالانش — دورة قرار كاملة")
        self._log(f"  الدستور v1.0 | الأصل: {cfg.asset} | رأس المال: ${cfg.capital_usd:,.0f}")
        self._log(SEP2)

        # ---- 0) البيانات -------------------------------------------------
        self._log("\n【0】تحميل البيانات")
        snap = self._load_snapshot()
        features = compute_features(snap)
        self._log(f"  {snap.summary()}")
        self._log(f"  المصدر: {snap.source} | اكتمال البيانات: {features['completeness']*100:.0f}%")
        if snap.source == "synthetic":
            self._log("  ℹ️ بيانات اصطناعية حتمية — للتدريب والاختبار (ليست سوقاً حقيقياً)")

        # ---- تهيئة السياق ------------------------------------------------
        ctx = AgentContext(
            snapshot=snap,
            config=cfg,
            law=self.law,
            features=features,
            shared={
                "journal_store": self.store,
                "agent_weights": self.store.agent_weights(),
            },
        )

        # ---- 1) طبقة المعرفة --------------------------------------------
        self._log("\n【1】طبقة المعرفة (الوكلاء 01–08) — تجميع الأدلة")
        for cls in KNOWLEDGE_AGENTS:
            op = cls().run(ctx)
            icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[op.direction]
            self._log(f"  {icon} [{op.agent_id}] {op.agent_name:<28} "
                      f"{op.direction:<8} ثقة={op.confidence:5.1f} (صافي {op.net_confidence:5.1f})")

        # ---- 2) طبقة التحقق ---------------------------------------------
        self._log("\n【2】طبقة التحقق (09–10) — الشك المنظم")
        for cls in VALIDATION_AGENTS:
            op = cls().run(ctx)
            extra = ""
            if op.agent_id == "09":
                bt = op.metrics.get("backtest", {})
                extra = (f" | DSR={bt.get('deflated_sharpe')} "
                         f"انحلال={bt.get('sharpe_decay')} "
                         f"OOS-Sharpe={bt.get('oos_sharpe')} "
                         f"{'✅ اجتاز' if op.metrics.get('validated') else '⛔ لم يجتز'}")
            if op.agent_id == "10":
                extra = f" | إجماع={op.metrics.get('consensus_direction')} " \
                        f"نقاط ضعف={len(op.metrics.get('weaknesses', []))}"
            self._log(f"  🔍 [{op.agent_id}] {op.agent_name:<28}{extra}")

        # ---- 3) المقترح --------------------------------------------------
        self._log("\n【3】تجميع مرجّح (الوكيل 14) — المقترح")
        orch = OrchestratorAgent()
        proposal = orch.propose(ctx)
        self._log(f"  الاتجاه: {proposal['direction']} | الدرجة: {proposal['score']:+.4f} "
                  f"| الاتفاق: {proposal['agreement']*100:.0f}%")
        self._log(f"  مؤيدون: {', '.join(proposal['supporters']) or '—'} | "
                  f"معارضون: {', '.join(proposal['opposers']) or '—'}")
        self._log(f"  الثقة المجمّعة: {proposal['confidence']:.2f}")
        for p in proposal["penalties"]:
            self._log(f"    ⚠️ {p}")

        # ---- 4) طبقة الضبط ----------------------------------------------
        # تُشتق القائمة من الكشف الرسمي `CONTROL_AGENTS` لا من استدعاءات بالاسم،
        # فإضافة وكيل ضبط إلى الكشف تُدخله الدورة تلقائياً.
        self._log("\n【4】طبقة الضبط (11–13) — سلطة المنع")
        for cls in CONTROL_AGENTS:
            agent = cls()
            agent.run(ctx)
            if agent.id == "11":
                verdict = ctx.shared["risk_verdict"]
                self._log(f"  {'🚫 نقض' if verdict.veto else '✅ موافقة'} | مستوى: {verdict.risk_level} "
                          f"| حجم: ${verdict.position_size_usd:,.0f} ({verdict.max_position_pct:.2f}%)")
                self._log(f"     وقف: {verdict.stop_loss_pct:.2f}% | "
                          f"مخاطرة/صفقة: {verdict.risk_per_trade_pct:.3f}% "
                          f"| القيد الملزم: {verdict.limits_checked.get('binding_constraint')}")
                for r in verdict.veto_reasons:
                    self._log(f"     ⛔ {r}")
            elif agent.id == "12":
                plan = ctx.shared.get("execution_plan")
                if plan:
                    self._log(f"  📐 خطة التنفيذ: {plan.method} | {plan.slices} شريحة "
                              f"| مشاركة {plan.participation_pct:.2f}% "
                              f"| انزلاق {plan.expected_slippage_bps:.2f} نقطة أساس "
                              f"| تكلفة ${plan.expected_cost_usd:,.0f}")
            elif agent.id == "13":
                compliance = ctx.shared["compliance"]
                self._log(f"  {'✅ متوافق' if compliance.compliant else '⛔ حجب'} | "
                          f"{compliance.checked_agents} رأياً مفحوصاً | "
                          f"{len(compliance.violations)} مخالفة "
                          f"({sum(1 for v in compliance.violations if v['severity']=='error')} حرجة)")
                for v in compliance.violations:
                    if v["severity"] == "error":
                        self._log(f"     ⛔ [م{v['article']}] {v['message'][:96]}")

        # ---- 5) القرار النهائي ------------------------------------------
        self._log("\n【5】القرار النهائي (الوكيل 14)")
        decision = orch.finalize(ctx)
        self._log(f"  🎯 {decision.action} | ثقة {decision.confidence:.2f}/100 | "
                  f"حجم ${decision.size_usd:,.0f}")
        self._log(f"  {decision.rationale}")

        orch.run(ctx)

        # ---- 5ب) التدقيق البعدي للقرار (المادة 8 + 6.3) -------------------
        # ثغرة حوكمة مُصلَحة: الوكيل 13 كان يعمل قبل 14 فلا يدقّق القرار إطلاقاً.
        post = ComplianceAgent.audit_decision(ctx, decision)
        self._log(f"\n【5ب】التدقيق البعدي للقرار — "
                  f"{'✅ صالح' if post['valid'] else '⛔ غير صالح'} "
                  f"({post['checked']} فحصاً، {post['violations_found']} مخالفة، "
                  f"{post['critical']} حرجة)")
        for v in post["violations"]:
            if v["severity"] == "error":
                self._log(f"     ⛔ [م{v['article']}] {v['message'][:96]}")

        # ---- 6) السجل ----------------------------------------------------
        self._log("\n【6】السجل (الوكيل 15)")
        if self.write_journal:
            MemoryAgent().run(ctx)
            rec = ctx.shared.get("journal_record")
            if rec:
                self._log(f"  📒 سُجّل برقم {rec.sequence} | hash {rec.record_hash[:20]}…")
        else:
            self._log("  ℹ️ الكتابة في السجل معطّلة (--no-journal)")

        result = self._build_result(ctx, decision, proposal, verdict, compliance, plan)
        self._save_halt_state()
        # المادة 9.2 — قياس نسبة الامتناع (لم يكن له أي قياس في النظام)
        try:
            result["journal_summary"] = self.store.summary()
        except Exception:  # noqa: BLE001
            result["journal_summary"] = None
        result["constitution"] = self.store.constitution_fingerprint(
            self.config.constitution_path)
        if result["constitution"].get("changed"):
            self._log("  ⚠️ بصمة الدستور تغيّرت بلا توثيق (المادة 10.1)")
        self._log("\n" + SEP2)
        return result

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_result(ctx: AgentContext, decision: DeskDecision, proposal: dict[str, Any],
                      verdict: Any, compliance: Any, plan: Any) -> dict[str, Any]:
        return {
            "timestamp": decision.timestamp,
            "asset": decision.asset,
            "data_source": ctx.snapshot.source,
            "decision": {
                "id": decision.decision_id,
                "action": decision.action,
                "confidence": decision.confidence,
                "horizon": decision.horizon,
                "entry_zone": decision.entry_zone,
                "stop": decision.stop_price,
                "targets": decision.targets,
                "size_usd": decision.size_usd,
                "rationale": decision.rationale,
                "invalidation": decision.invalidation,
                "supporting_agents": decision.supporting_agents,
                "opposing_agents": decision.opposing_agents,
                "strongest_dissent": decision.strongest_dissent,
                "dissent_source": decision.dissent_source,
                "abstention_kind": decision.abstention_kind,
                "blocks": decision.blocks,
                "groupthink_flag": decision.groupthink_flag,
            },
            "proposal": proposal,
            "risk": verdict.to_dict() if verdict else None,
            "execution_plan": plan.to_dict() if plan else None,
            "compliance": compliance.to_dict() if compliance else None,
            "post_decision_audit": ctx.shared.get("post_decision_audit"),
            "opinions": {aid: op.to_dict() for aid, op in ctx.opinions.items()},
            "law_audit": ctx.law.summary(),
            "evidence_summary": decision.evidence_summary,
            "market": ctx.snapshot.to_dict(),
        }


# ==========================================================================
# التقرير النصي
# ==========================================================================

def render_report(result: dict[str, Any]) -> str:
    d = result["decision"]
    risk = result.get("risk") or {}
    comp = result.get("compliance") or {}
    prop = result.get("proposal") or {}
    plan = result.get("execution_plan") or {}
    audit = result.get("law_audit") or {}

    action_ar = {
        Action.LONG.value: "🟢 فتح مركز شراء (LONG)",
        Action.SHORT.value: "🔴 فتح مركز بيع (SHORT)",
        Action.FLAT.value: "⚪ البقاء خارج السوق",
        Action.ABSTAIN.value: "⏸️ الامتناع (ABSTAIN)",
    }.get(d["action"], d["action"])

    L: list[str] = []
    L.append(SEP2)
    L.append("  📋 تقرير ديسك أفالانش — AVAX")
    L.append(f"  {result['timestamp']}  |  مصدر البيانات: {result['data_source']}")
    L.append(SEP2)

    L.append("\n▌القرار")
    L.append(f"  {action_ar}")
    if d.get("abstention_kind"):
        kind_ar = {"no_edge": "لا حافة مرجّحة", "risk_veto": "نقض من المخاطر",
                   "compliance_block": "حجب من الالتزام", "halted": "الديسك موقوف"}
        L.append(f"  نوع الامتناع: {kind_ar.get(d['abstention_kind'], d['abstention_kind'])}")
        for b in (d.get("blocks") or []):
            L.append(f"    ⛔ {b}")
    L.append(f"  الثقة: {d['confidence']:.2f}/100   |   الأفق: {d['horizon']}")
    L.append(f"  حجم المركز: ${d['size_usd']:,.0f}")
    if d["entry_zone"]:
        L.append(f"  نطاق الدخول: {d['entry_zone'][0]:,.4f} – {d['entry_zone'][1]:,.4f}")
        L.append(f"  وقف الخسارة: {d['stop']:,.4f}   |   الأهداف: "
                 + " / ".join(f"{t:,.4f}" for t in d["targets"]))
    L.append(f"\n  المبرر: {d['rationale']}")
    L.append(f"\n  شرط الإبطال: {d['invalidation']}")

    L.append("\n▌التجميع المرجّح")
    L.append(f"  الدرجة: {prop.get('score')}   |   الاتجاه: {prop.get('direction')}   "
             f"|   الاتفاق: {(prop.get('agreement') or 0)*100:.0f}%")
    L.append(f"  مؤيدون ({len(d['supporting_agents'])}): {', '.join(d['supporting_agents']) or '—'}")
    L.append(f"  معارضون ({len(d['opposing_agents'])}): {', '.join(d['opposing_agents']) or '—'}")
    if d["groupthink_flag"]:
        L.append("  🚨 إجماع شبه تام — مراجعة إلزامية ضد Groupthink (المادة 4.4)")

    L.append("\n▌الرأي المخالف (محفوظ — المادة 6)")
    L.append(f"  {d['strongest_dissent'][:700]}")

    L.append("\n▌المخاطر (المادة 5)")
    L.append(f"  المستوى: {risk.get('risk_level')}   |   "
             f"{'🚫 نقض' if risk.get('veto') else '✅ موافقة'}")
    L.append(f"  الحجم: ${risk.get('position_size_usd', 0):,.0f} "
             f"({risk.get('max_position_pct', 0):.2f}% من رأس المال)")
    L.append(f"  الوقف: {risk.get('stop_loss_pct', 0):.2f}%   |   "
             f"مخاطرة/صفقة: {risk.get('risk_per_trade_pct', 0):.3f}%")
    lc = risk.get("limits_checked", {})
    L.append(f"  احتمال النجاح المستخدم: {lc.get('win_probability_used')}   |   "
             f"R:R: {lc.get('reward_risk_used')}   |   القيد الملزم: {lc.get('binding_constraint')}")
    for r in (risk.get("veto_reasons") or [])[:5]:
        L.append(f"    ⛔ {r}")

    if plan:
        L.append("\n▌التنفيذ (نظري — المادة 0.2)")
        L.append(f"  الخوارزمية: {plan.get('method')}   |   الشرائح: {plan.get('slices')}   "
                 f"|   المشاركة: {plan.get('participation_pct')}%")
        L.append(f"  الانزلاق المتوقع: {plan.get('expected_slippage_bps')} نقطة أساس   |   "
                 f"التكلفة: ${plan.get('expected_cost_usd', 0):,.2f}")

    L.append("\n▌الالتزام والتدقيق (المادة 8)")
    L.append(f"  {'✅ متوافق' if comp.get('compliant') else '⛔ حجب'}   |   "
             f"{comp.get('checked_agents')} رأياً مفحوصاً   |   "
             f"{len(comp.get('violations') or [])} مخالفة")
    for v in (comp.get("violations") or [])[:6]:
        tag = "⛔" if v["severity"] == "error" else "⚠️"
        L.append(f"    {tag} [م{v['article']}] {v['message'][:110]}")

    post = result.get("post_decision_audit") or {}
    if post:
        L.append("\n▌التدقيق البعدي للقرار (المادتان 6.3 و 5.1)")
        L.append(f"  {'✅ القرار صالح دستورياً' if post.get('valid') else '⛔ القرار يحمل مخالفة حرجة'}   "
                 f"|   {post.get('checked', 0)} فحصاً، {post.get('violations_found', 0)} مخالفة، "
                 f"{post.get('critical', 0)} حرجة")
        for v in (post.get("violations") or [])[:5]:
            tag = "⛔" if v["severity"] == "error" else "⚠️"
            L.append(f"    {tag} [م{v['article']}] {v['message'][:110]}")

    L.append("\n▌تدقيق القوانين")
    L.append(f"  إجمالي المخالفات: {audit.get('total', 0)} "
             f"({audit.get('errors', 0)} حرجة، {audit.get('warnings', 0)} تحذير)")
    for art, cnt in list((audit.get("by_article") or {}).items())[:6]:
        L.append(f"    المادة {art}: {cnt}")

    L.append("\n▌أقوى الأدلة (هرمية المادة 3.1)")
    for e in (result.get("evidence_summary") or [])[:6]:
        L.append(f"  [طبقة {e['tier']} · وكيل {e['agent_id']}] {e['claim'][:120]}")

    L.append("\n▌آراء الوكلاء")
    for aid in sorted((result.get("opinions") or {}).keys()):
        op = result["opinions"][aid]
        icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[op["direction"]]
        state = "امتناع" if op["abstain"] else op["direction"]
        L.append(f"  {icon} [{aid}] {op['agent_name']:<28} {state:<8} "
                 f"ثقة={op['confidence']:5.1f} صافي={op.get('net_confidence', 0):5.1f} "
                 f"طبقة={op.get('best_tier')}")

    L.append("\n" + SEP2)
    L.append("  ⚠️ هذا تحليل آلي لأغراض البحث والتطوير — ليس نصيحة مالية.")
    L.append("  ⚠️ الديسك لا ينفّذ صفقات حقيقية (CONSTITUTION.md المادة 0.2).")
    L.append(SEP2)
    return "\n".join(L)


# ==========================================================================
# نقطة الدخول
# ==========================================================================

def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(
        prog="avax-desk",
        description="ديسك أفالانش — فريق وكلاء تحليل لمنظومة Avalanche/AVAX",
    )
    parser.add_argument("--scenario", default="auto",
                        choices=["auto", "bull", "bear", "chop", "crisis", "recovery"],
                        help="سيناريو السوق للبيانات الاصطناعية")
    parser.add_argument("--seed", type=int, default=42, help="بذرة العشوائية (للتكرار)")
    parser.add_argument("--days", type=int, default=365, help="عدد أيام التاريخ")
    parser.add_argument("--capital", type=float, default=1_000_000.0, help="رأس المال بالدولار")
    parser.add_argument("--live", action="store_true", help="استخدام بيانات حيّة من الشبكة")
    parser.add_argument("--daily-pnl", type=float, default=0.0,
                        help="الربح/الخسارة اليومية %% (سالب = خسارة)")
    parser.add_argument("--drawdown", type=float, default=0.0,
                        help="التراجع من القمة %% — يُقبل بأي إشارة (20 = تراجع 20%%)")
    parser.add_argument("--json", action="store_true", help="طباعة النتيجة JSON")
    parser.add_argument("--save-report", default="", help="مسار حفظ التقرير النصي")
    parser.add_argument("--no-journal", action="store_true", help="عدم الكتابة في السجل")
    parser.add_argument("--sector-exposure", type=float, default=0.0,
                        help="التعرّض الحالي للقطاع %% — لفرض حد التركّز (المادة 5.3)")
    parser.add_argument("--sector", default="layer-1", help="اسم القطاع (افتراضياً layer-1)")
    parser.add_argument("--resume", action="store_true",
                        help="رفع الإيقاف يدوياً (المادة 5.4 — لا رفع تلقائي)")
    parser.add_argument("--push", action="store_true",
                        help="دفع الدورة إلى الواجهة الخلفية (Supabase)")
    parser.add_argument("--db-health", action="store_true",
                        help="فحص اتصال الواجهة الخلفية وعدّاد الجداول")
    parser.add_argument("--audit-roster", action="store_true", help="تدقيق اتساق ملفات الوكلاء")
    parser.add_argument("--verify-journal", action="store_true", help="التحقق من سلامة السجل")
    parser.add_argument("--journal-summary", action="store_true",
                        help="توليد ملخّص Markdown للسجل (المادة 7.1)")
    parser.add_argument("--post-mortem", default="",
                        help="تسجيل مراجعة بعدية: معرّف القرار (المادة 7.3)")
    parser.add_argument("--outcome", default="",
                        help="نتيجة القرار للمراجعة البعدية: correct | incorrect | flat")
    parser.add_argument("--lesson", default="", help="الدرس المستفاد من المراجعة البعدية")
    parser.add_argument("--quiet", action="store_true", help="تقليل مخرجات التشغيل")
    args = parser.parse_args(argv)

    if args.audit_roster:
        print(consistency_report())
        audit = audit_roster()
        return 0 if audit["ok"] else 1

    if args.verify_journal:
        store = JournalStore("journal/desk_journal.jsonl")
        chain = store.verify_chain()
        print(SEP2)
        print("  التحقق من سلامة سجل الديسك (المادة 7.2)")
        print(SEP2)
        print(f"  عدد السجلات: {chain['records']}")
        print(f"  سلامة السلسلة: {'✅ سليمة' if chain['valid'] else '⛔ مكسورة'}")
        print(f"  رأس السلسلة: {chain['head_hash'][:32]}…")
        for b in chain["broken"]:
            print(f"    ⛔ تسلسل {b['sequence']}: {b['issue']}")
        print(SEP2)
        return 0 if chain["valid"] else 1

    if args.db_health:
        try:
            from .backend.supabase_client import SupabaseBackend
            h = SupabaseBackend().health()
            print(SEP2)
            print("  فحص الواجهة الخلفية (Supabase)")
            print(SEP2)
            print(f"  المشروع: {h['url']}")
            print(f"  الحالة: {'✅ سليم' if h['ok'] else '⚠️ بعض الجداول غير مقروءة'}")
            for t, n in h["tables"].items():
                print(f"    ▸ {t:<22} {n}")
            print(SEP2)
            return 0 if h["ok"] else 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ⛔ تعذّر فحص الواجهة الخلفية: {type(exc).__name__}: {exc}")
            return 1

    if args.journal_summary:
        store = JournalStore("journal/desk_journal.jsonl")
        path = store.write_markdown_summary()
        print(f"  ✅ كُتب ملخّص السجل في: {path}")
        print(json.dumps(store.summary(), ensure_ascii=False, indent=2))
        return 0

    if args.post_mortem:
        store = JournalStore("journal/desk_journal.jsonl")
        decision = next((d for d in store.decisions()
                         if d.get("decision_id") == args.post_mortem), None)
        if decision is None:
            print(f"  ⛔ لا يوجد قرار بالمعرّف: {args.post_mortem}")
            return 1
        outcome = args.outcome or "unknown"
        correct = (outcome == "correct")

        # نتيجة كل وكيل: هل كان اتجاهه متوافقاً مع ما تحقق فعلاً؟ (المادة 7.3)
        record_payload = next((r.payload for r in store.records()
                               if r.payload.get("decision", {}).get("decision_id") == args.post_mortem),
                              {})
        digest = record_payload.get("opinions_digest", []) or []
        expected = "bullish" if decision.get("action") == "LONG" else (
            "bearish" if decision.get("action") == "SHORT" else "neutral")
        agent_scores = [
            {"agent_id": d.get("agent_id", ""),
             "direction": d.get("direction", "neutral"),
             "correct": ((d.get("direction") == expected) == correct)
             if expected != "neutral" else correct}
            for d in digest
        ]
        result = MemoryAgent.record_post_mortem(
            store, args.post_mortem, outcome, agent_scores, args.lesson)
        print(SEP2)
        print("  المراجعة البعدية (المادة 7.3)")
        print(SEP2)
        print(f"  القرار: {args.post_mortem} | النتيجة: {outcome}")
        print(f"  سُجّل برقم: {result['sequence']}  ({result['record_id']})")
        print(f"  أوزان الوكلاء المحدَّثة: {result['updated_weights']}")
        if args.lesson:
            print(f"  الدرس: {args.lesson}")
        print(SEP2)
        store.write_markdown_summary()
        return 0

    # تحقق من صحة الوسائط — `--days 0` كان يُسقط الديسك بانهيار غير معالج
    if args.days < 60:
        print(f"  ⛔ --days يجب أن يكون 60 يوماً على الأقل (المُمرَّر: {args.days}). "
              f"السلاسل الأقصر لا تكفي لحساب مؤشرات 200 فترة أو اختبار خارج العينة.")
        return 1
    if args.capital < 0:
        print("  ⛔ --capital لا يمكن أن يكون سالباً.")
        return 1

    config = DeskConfig(
        asset="AVAX",
        capital_usd=args.capital,
        seed=args.seed,
        scenario=args.scenario,
        lookback_days=args.days,
        live_data=args.live,
        daily_pnl_pct=args.daily_pnl,
        current_drawdown_pct=args.drawdown,
        current_sector_exposure_pct=args.sector_exposure,
        sector=args.sector,
        limits=Limits(),
        verbose=not args.quiet,
    )

    runner = DeskRunner(config, write_journal=not args.no_journal)
    if args.resume:
        config.resume("رفع يدوي بأمر --resume")
    result = runner.run()

    report = render_report(result)
    print(report)

    if args.save_report:
        out = Path(args.save_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\n  💾 حُفظ التقرير في: {out}")

    if args.json:
        print("\n" + json.dumps(result, ensure_ascii=False, indent=2, default=str))

    if args.push:
        try:
            from .backend.supabase_client import SupabaseBackend
            backend = SupabaseBackend()
            ids = backend.push_run(result)
            result["backend"] = {k: v for k, v in ids.items() if k != "errors"}
            if ids.get("errors"):
                print(f"  ⚠️ أخطاء دفع: {ids['errors'][:2]}")
        except Exception as exc:  # noqa: BLE001
            # الدفع عملية لاحقة — فشلها لا يُسقط التحليل (المادة 0.2)
            print(f"  ⚠️ تعذّر الدفع إلى الواجهة الخلفية: {type(exc).__name__}: {str(exc)[:160]}")

    # رمز الخروج: 0 = قرار، 2 = امتناع، 3 = حجب/نقض
    if result["decision"]["action"] == Action.ABSTAIN.value:
        return 3 if (result.get("compliance") or {}).get("blocked") else 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
