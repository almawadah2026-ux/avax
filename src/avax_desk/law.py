"""
محرك القوانين — الترجمة التنفيذية لدستور ديسك أفالانش.

كل مادة في CONSTITUTION.md لها أثر هنا. القانون الذي لا يُفرَض آلياً قانون ميت
(CONSTITUTION.md المادة 10.2).

هذا الملف هو **السلطة القضائية** في الديسك: يفحص، يرفض، ينقض، ويُبطل.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .config import Limits
from .contracts import (
    AgentOpinion,
    Authority,
    EVIDENCE_TIERS,
    Evidence,
    Layer,
    TIER_LABELS,
)


# --------------------------------------------------------------------------
# هوية الوكلاء — المرجع الوحيد لصلاحيات كل وكيل (المادة 1.1)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentSpecRef:
    id: str
    name_ar: str
    name_en: str
    layer: Layer
    authority: Authority
    file: str
    domain: str = ""


AGENT_ROSTER: tuple[AgentSpecRef, ...] = (
    AgentSpecRef("01", "وكيل بنية السوق", "Market Structure", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/01-market-structure.md", "microstructure"),
    AgentSpecRef("02", "وكيل التحليل الفني", "Technical Analysis", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/02-technical-analysis.md", "technical"),
    AgentSpecRef("03", "الوكيل الكمي", "Quantitative", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/03-quantitative.md", "stats"),
    AgentSpecRef("04", "وكيل الماكرو والأساسيات", "Macro & Fundamentals", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/04-macro-fundamental.md", "macro"),
    AgentSpecRef("05", "وكيل الأونشين", "On-chain (AVAX)", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/05-onchain-avax.md", "onchain"),
    AgentSpecRef("06", "وكيل المشتقات والتقلب", "Derivatives & Volatility", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/06-derivatives-volatility.md", "derivatives"),
    AgentSpecRef("07", "وكيل المعنويات والأخبار", "Sentiment & News", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/07-sentiment-news.md", "sentiment"),
    AgentSpecRef("08", "وكيل نظرية المحافظ", "Portfolio Theory", Layer.KNOWLEDGE, Authority.ADVISORY,
                 "agents/08-portfolio-theory.md", "portfolio"),
    AgentSpecRef("09", "وكيل التحقق والاختبار", "Validation & Backtest", Layer.VALIDATION, Authority.ADVISORY,
                 "agents/09-validation-backtest.md", "validation"),
    AgentSpecRef("10", "محامي الشيطان", "Red Team", Layer.VALIDATION, Authority.ADVISORY,
                 "agents/10-red-team.md", "falsification"),
    AgentSpecRef("11", "وكيل المخاطر", "Risk Manager", Layer.CONTROL, Authority.VETO,
                 "agents/11-risk-manager.md", "risk"),
    AgentSpecRef("12", "وكيل التنفيذ", "Execution", Layer.CONTROL, Authority.ADVISORY,
                 "agents/12-execution.md", "execution"),
    AgentSpecRef("13", "وكيل الالتزام والتدقيق", "Compliance & Audit", Layer.CONTROL, Authority.VETO,
                 "agents/13-compliance-audit.md", "compliance"),
    AgentSpecRef("14", "المنسّق / مدير المحفظة", "Orchestrator / PM", Layer.DECISION, Authority.DECISION,
                 "agents/14-orchestrator.md", "decision"),
    AgentSpecRef("15", "وكيل الذاكرة والسجل", "Memory & Journal", Layer.MEMORY, Authority.RECORD,
                 "agents/15-memory-journal.md", "journal"),
)

ROSTER_BY_ID: dict[str, AgentSpecRef] = {a.id: a for a in AGENT_ROSTER}


# --------------------------------------------------------------------------
# المخالفات
# --------------------------------------------------------------------------

@dataclass
class Violation:
    """مخالفة دستورية واحدة."""

    article: str          # مثال: "2.2"
    code: str             # رمز ثابت للفحص الآلي
    message: str
    severity: str = "error"   # error | warning
    agent_id: str = ""
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "article": self.article,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "agent_id": self.agent_id,
            "evidence_ref": self.evidence_ref,
        }

    def __str__(self) -> str:
        tag = "⛔" if self.severity == "error" else "⚠️"
        return f"{tag} [م{self.article} | {self.code}] {self.message}"


# --------------------------------------------------------------------------
# أنماط السلوك المحرّم — المادة 8
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ProhibitedPattern:
    code: str
    article: str
    description: str
    regex: re.Pattern[str]
    severity: str = "error"


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


PROHIBITED_PATTERNS: tuple[ProhibitedPattern, ...] = (
    ProhibitedPattern(
        "FABRICATION_MARKER", "8.1",
        "مؤشر على بيانات مُختلقة أو مصدر وهمي",
        _rx(r"(مصدر غير معروف|source:\s*unknown|بيانات تقديرية غير موثقة|lorem ipsum)"),
    ),
    ProhibitedPattern(
        "CERTAINTY_LANGUAGE", "8.8",
        "لغة يقين مطلق — الدستور يمنع الادّعاء بمعرفة المستقبل",
        _rx(r"(مضمون(ة)?\s*(100|تماماً|بالكامل)|بلا أي مخاطر|ربح مؤكد|guaranteed\s+return|risk[- ]free\s+profit|سيرتفع حتماً|سينهار حتماً)"),
    ),
    ProhibitedPattern(
        "HINDSIGHT_MARKER", "8.2",
        "مؤشر على تحيّز استرجاعي — الاستشهاد بمعلومة لاحقة للقرار",
        # ملاحظة: كان النمط يطابق كلمة «hindsight» المجرّدة، فيصيب أي نص يذكر
        # المصطلح تعريفاً (بما فيه ملف الوكيل 15 نفسه) — إيجابية كاذبة.
        # الآن يشترط عبارة الاستدلال الفعلي: in/with hindsight.
        _rx(r"(كما توقّعنا سابقاً بعد الحدث|لو كنّا اشترينا بالأمس|"
            r"\bin hindsight\b|\bwith hindsight\b|hindsight\s+made\s+it\s+(obvious|clear))"),
    ),
    ProhibitedPattern(
        "EXECUTION_INSTRUCTION", "0.2",
        "أمر تنفيذ فعلي — محرّم منعاً مطلقاً",
        _rx(r"(تم إرسال الأمر|أرسلت الأمر إلى المنصة|order\s+(placed|submitted|sent)|تم التنفيذ على المنصة|اربط محفظتك|أدخل مفتاح API)"),
    ),
    ProhibitedPattern(
        "IMPERATIVE_BUY", "1.2",
        "أمر شراء/بيع مباشر من وكيل معرفي",
        _rx(r"(اشترِ الآن|بِع الآن|ضع أمر شراء|ضع أمر بيع|buy now|sell now|place order)"),
    ),
    ProhibitedPattern(
        "CERTAINTY_OF_EDGE", "8.8",
        "ادّعاء حافة مطلقة بلا احتمال خطأ",
        _rx(r"(لا يمكن أن يخسر|صفقة مضمونة|نسبة نجاح 100\s*%)"),
    ),
)


# --------------------------------------------------------------------------
# سلّم الثقة — المادة 7.1 من القالب
# --------------------------------------------------------------------------

CONFIDENCE_BANDS: tuple[tuple[float, float, str, bool], ...] = (
    (0.0, 20.0, "تخمين", False),
    (21.0, 40.0, "ضعيف", False),
    (41.0, 64.0, "متوسط — للمراقبة فقط", False),
    (65.0, 80.0, "قوي — مؤهل للدخول", True),
    (81.0, 100.0, "قوي جداً — يتطلب دليلين مستقلين", True),
)


def confidence_band(score: float) -> tuple[str, bool]:
    """يعيد (التسمية، هل هو مؤهل للدخول) وفق سلّم الثقة الإلزامي."""
    for low, high, label, eligible in CONFIDENCE_BANDS:
        if low <= score <= high:
            return label, eligible
    return "خارج النطاق", False


# --------------------------------------------------------------------------
# محرك القوانين
# --------------------------------------------------------------------------

class LawEngine:
    """
    السلطة القضائية للديسك.

    الاستخدام:
        law = LawEngine()
        violations = law.validate_opinion(opinion)
        if violations: ...
    """

    def __init__(self, limits: Limits | None = None) -> None:
        self.limits = limits or Limits()
        self.audit_log: list[Violation] = []

    # -- المادة 2: عقد الرأي ------------------------------------------------
    def validate_opinion(self, op: AgentOpinion) -> list[Violation]:
        """
        فحص رأي وكيل مقابل عقد الرأي (المادة 2) وفصل السلطات (المادة 1).
        يعيد قائمة المخالفات؛ قائمة فارغة = رأي صالح.
        """
        v: list[Violation] = []
        spec = ROSTER_BY_ID.get(op.agent_id)

        # الامتناع مشروع — لكنه **لا يعفي** من فحص السلوك المحرّم (المادة 8).
        # ثغرة مُصلَحة: كان `validate_opinion` يعود قبل كل الفحوص، فرأي ممتنع بنص
        # «اشترِ الآن — صفقة مضمونة» يمرّ بصفر مخالفات ويُكتب نصّه في السجل.
        if op.abstain:
            if not op.abstain_reason:
                v.append(Violation("9.1", "ABSTAIN_WITHOUT_REASON",
                                   "امتناع بلا سبب معلن", "warning", op.agent_id))
            blob = " ".join([op.thesis, op.invalidation, op.dissent,
                             *[e.claim for e in op.evidence]])
            v.extend(self.scan_prohibited(blob, op.agent_id))
            self.audit_log.extend(v)
            return v

        # المادة 2.2 — شرط الإبطال إلزامي
        if not op.invalidation or op.invalidation.strip() in {"", "—", "-", "none", "لا يوجد"}:
            v.append(Violation("2.2", "MISSING_INVALIDATION",
                               f"[{op.agent_id}] رأي بلا شرط إبطال — يُرفض آلياً", "error", op.agent_id))

        # المادة 2.1 — الحقول الإلزامية
        if not op.thesis or len(op.thesis.strip()) < 5:
            v.append(Violation("2.1", "MISSING_THESIS",
                               f"[{op.agent_id}] فرضية غائبة أو تافهة", "error", op.agent_id))

        if not op.horizon or op.horizon.strip() in {"", "—"}:
            # تفسير المادة 2.1: الأفق الزمني إلزامي للوكلاء الذين يُنتجون فرضيات سوقية.
            # وكلاء التحقق والضبط لا يُنتجون فرضية اتجاهية، فالأفق عندهم «لا ينطبق».
            produces_thesis = spec is None or spec.layer == Layer.KNOWLEDGE
            if produces_thesis or not op.horizon:
                v.append(Violation("2.1", "MISSING_HORIZON",
                                   f"[{op.agent_id}] أفق زمني غائب", "error", op.agent_id))

        if not op.dissent or op.dissent.strip() in {"", "—"}:
            v.append(Violation("2.1", "MISSING_DISSENT",
                               f"[{op.agent_id}] حقل المخالف غائب", "warning", op.agent_id))

        # المادة 2.3 — الثقة بلا أدلة
        if not op.evidence:
            v.append(Violation("2.3", "CONFIDENCE_WITHOUT_EVIDENCE",
                               f"[{op.agent_id}] ثقة {op.confidence} بلا دليل مفصّل", "error", op.agent_id))

        # المادة 2.5 — كل دليل له مصدر وطابع زمني (مفروض في Evidence.__post_init__)
        for ev in op.evidence:
            if ev.staleness(self.limits.stale_hours):
                v.append(Violation("3.4", "STALE_EVIDENCE",
                                   f"[{op.agent_id}] دليل قديم (> {self.limits.stale_hours}h): {ev.claim[:60]}",
                                   "warning", op.agent_id, ev.claim))

        # المادة 8.8 — لغة اليقين
        text_blob = " ".join([op.thesis, op.invalidation, op.dissent] + [e.claim for e in op.evidence])
        v.extend(self.scan_prohibited(text_blob, op.agent_id, codes={"CERTAINTY_LANGUAGE", "CERTAINTY_OF_EDGE"}))

        # المادة 1.2 — وكيل معرفي لا يصدر أوامر تنفيذ
        if spec and spec.layer == Layer.KNOWLEDGE:
            v.extend(self.scan_prohibited(text_blob, op.agent_id, codes={"IMPERATIVE_BUY"}))
            if op.metrics.get("recommendation"):
                v.append(Violation("1.2", "KNOWLEDGE_AGENT_RECOMMENDS",
                                   f"[{op.agent_id}] وكيل معرفي أصدر توصية تنفيذية — خرق فصل السلطات",
                                   "error", op.agent_id))

        # المادة 1.3 — المخاطر لا يقدّم فرضيات سوقية
        if op.agent_id == "11" and op.direction != "neutral" and op.metrics.get("market_thesis"):
            v.append(Violation("1.3", "RISK_AGENT_MARKET_THESIS",
                               "وكيل المخاطر قدّم فرضية سوقية — فقد استقلاليته", "error", op.agent_id))

        # المادة 2.4 — الغموض بدل الرقم (موسّع: كان يفحص `thesis` فقط)
        text_all = " ".join([op.thesis, op.invalidation, op.dissent,
                             *[e.claim for e in op.evidence]])
        vague = self.ambiguity_score(text_all)
        if vague >= 2:
            v.append(Violation("2.4", "VAGUE_LANGUAGE",
                               f"[{op.agent_id}] {vague} عبارات غموض بدل رقم ودليل "
                               f"(المادة 2.4: «يُمنع استخدام عبارات الغموض كبديل عن رقم ونطاق»)",
                               "warning", op.agent_id))
        if vague >= 4:
            v.append(Violation("2.4", "EXCESSIVE_VAGUENESS",
                               f"[{op.agent_id}] {vague} عبارات غموض — النص وصفي لا كمّي",
                               "error", op.agent_id))

        # المادة 0.2 — لا تنفيذ
        v.extend(self.enforce_no_execution(text_blob, op.agent_id))

        self.audit_log.extend(v)
        return v

    # -- المادة 0.2: منع التنفيذ -------------------------------------------
    def enforce_no_execution(self, text: str, agent_id: str = "") -> list[Violation]:
        return self.scan_prohibited(text, agent_id, codes={"EXECUTION_INSTRUCTION"})

    # -- المادة 8: فحص الأنماط المحرّمة ------------------------------------
    def scan_prohibited(
        self, text: str, agent_id: str = "", codes: set[str] | None = None
    ) -> list[Violation]:
        out: list[Violation] = []
        for p in PROHIBITED_PATTERNS:
            if codes is not None and p.code not in codes:
                continue
            m = p.regex.search(text or "")
            if m:
                out.append(Violation(
                    p.article, p.code,
                    f"{p.description} — العبارة: «{m.group(0)[:40]}»",
                    p.severity, agent_id,
                ))
        return out

    # -- المادة 3: تحكيم الأدلة --------------------------------------------
    def arbitrate_evidence(
        self, evidences: Sequence[Evidence]
    ) -> tuple[Evidence | None, Evidence | None]:
        """
        عند تعارض دليلين، الأقوى في الهرمية يرجّح (المادة 3.2).

        يعيد (الرابح، الخاسر). الرابح هو الأدنى في رقم الطبقة.
        """
        if not evidences:
            return None, None
        ordered = sorted(evidences, key=lambda e: (e.tier, 0 if e.strength == "high" else 1))
        return ordered[0], (ordered[-1] if len(ordered) > 1 else None)

    def arbitrate_conflict(self, strong: Evidence, weak: Evidence) -> dict[str, Any]:
        """يشرح نتيجة التحكيم بين دليلين متعارضين."""
        winner, loser = (strong, weak) if strong.tier <= weak.tier else (weak, strong)
        return {
            "winner": winner.claim,
            "winner_tier": winner.tier,
            "winner_tier_label": TIER_LABELS[winner.tier],
            "loser": loser.claim,
            "loser_tier": loser.tier,
            "rule": "CONSTITUTION.md المادة 3.2 — الأدنى طبقةً يرجّح",
            "margin": abs(strong.tier - weak.tier),
        }

    # -- المادة 4.4: كشف الإجماع المريب ------------------------------------
    def flag_groupthink(self, opinions: Iterable[AgentOpinion], threshold: float | None = None) -> dict[str, Any]:
        """
        الإجماع الكامل إشارة إنذار لا ثقة (المادة 4.4).
        """
        thr = threshold if threshold is not None else self.limits.groupthink_threshold
        active = [o for o in opinions if not o.abstain and o.direction != "neutral"]
        if not active:
            return {"flag": False, "agreement": 0.0, "n": 0, "note": "لا آراء اتجاهية"}
        bulls = sum(1 for o in active if o.direction == "bullish")
        bears = len(active) - bulls
        agreement = max(bulls, bears) / len(active)
        flag = agreement >= thr and len(active) >= 5
        return {
            "flag": flag,
            "agreement": round(agreement, 4),
            "n": len(active),
            "bullish": bulls,
            "bearish": bears,
            "threshold": thr,
            "note": ("إجماع شبه تام — يُفعّل مراجعة إلزامية ضد Groupthink (المادة 4.4)"
                     if flag else "توزيع آراء مقبول"),
        }

    # -- المادة 4.1: قانون التحقق ------------------------------------------
    def require_validation(self, claim_metrics: dict[str, Any], agent_id: str = "") -> list[Violation]:
        """
        لا تُقبل استراتيجية/إشارة بلا: خارج العينة، نموذج تكاليف، فحص قدرة، فحص Overfitting.
        """
        v: list[Violation] = []
        required = {
            "oos_tested": "اختبار خارج العينة (Out-of-Sample)",
            "costs_modeled": "نموذج تكاليف واقعي",
            "capacity_checked": "تحليل القدرة (Capacity)",
            "overfitting_checked": "فحص Overfitting / Deflated Sharpe",
        }
        for key, label in required.items():
            if not claim_metrics.get(key):
                v.append(Violation("4.1", f"MISSING_{key.upper()}",
                                   f"[{agent_id}] إشارة بلا {label}", "error", agent_id))

        # المادة 4.2 — نتيجة استثنائية = شبهة
        excess = claim_metrics.get("excess_vs_benchmark")
        if isinstance(excess, (int, float)) and excess > 3.0:
            v.append(Violation("4.2", "SUSPICIOUS_PERFORMANCE",
                               f"[{agent_id}] أداء يتجاوز 3 أضعاف المعيار ({excess:.2f}x) — يُصنَّف مشتبهاً به",
                               "warning", agent_id))
        return v

    # -- المادة 5.3: الحد الأدنى للثقة -------------------------------------
    def eligible_for_entry(self, confidence: float) -> bool:
        return confidence >= self.limits.min_confidence

    # -- سلّم الثقة (المادة 7.1 من القالب) — كان معرّفاً كدالة حرة بلا مستدعٍ
    @staticmethod
    def confidence_band(score: float) -> tuple[str, bool]:
        """يعيد (التسمية، هل هو مؤهل للدخول) وفق سلّم الثقة الإلزامي."""
        return confidence_band(score)

    # -- المادة 2.4: الغموض بدل الرقم --------------------------------------
    _VAGUE = re.compile(r"\b(قد يكون|قد يحدث|ربما|من المحتمل جداً|يُحتمل|"
                        r"maybe|possibly|might|could be)\b")

    def ambiguity_score(self, text: str) -> int:
        """عدد عبارات الغموض في نص — المادة 2.4."""
        return len(self._VAGUE.findall(text or ""))

    # -- المادة 3.2: أولوية الدليل الأولي -----------------------------------
    def primary_evidence_conflict(self, opinions: Iterable[AgentOpinion],
                                  decided_direction: str,
                                  min_confidence: float = 55.0) -> dict[str, Any]:
        """
        المادة 3.2: «عند تعارض دليل من المستوى 1 مع دليل من المستوى 5،
        **المستوى 1 يرجّح دائماً** ما لم يُثبت خطأ القياس».

        ثغرة مُصلَحة: `arbitrate_evidence` كان يُستدعى لكن مخرجه لا يصل إلى القرار،
        فيمكن أن يفوز اتجاه تسنده ثلاثة أدلة من الطبقة 4 على دليل واحد من الطبقة 1.
        الآن: أي رأي اتجاهي **مخالف** يسنده دليل من الطبقة 1 أو 2 بثقة صافية ≥ الحد
        يُسقط الاتجاه المجمّع (يُحوّله إلى امتناع) — لا يُخصم منه فقط.
        """
        if decided_direction == "neutral":
            return {"conflict": False, "reason": "لا اتجاه مجمّع للمقارنة"}
        offenders = [
            o for o in opinions
            if not o.abstain
            and o.direction not in (decided_direction, "neutral")
            and o.best_tier <= 2
            and o.net_confidence >= min_confidence
        ]
        if not offenders:
            return {"conflict": False,
                    "reason": "لا دليل أولي (طبقة 1 أو 2) يعارض الاتجاه المجمّع"}
        strongest = max(offenders, key=lambda o: (o.net_confidence, -o.best_tier))
        return {
            "conflict": True,
            "agent_id": strongest.agent_id,
            "agent_name": strongest.agent_name,
            "tier": strongest.best_tier,
            "tier_label": TIER_LABELS[strongest.best_tier],
            "direction": strongest.direction,
            "confidence": round(strongest.net_confidence, 2),
            "rule": "CONSTITUTION.md المادة 3.2 — الدليل الأولي يرجّح على الأضعف",
            "note": (f"الوكيل {strongest.agent_id} ({strongest.agent_name}) يسنده دليل "
                     f"من الطبقة {strongest.best_tier} ({TIER_LABELS[strongest.best_tier]}) "
                     f"باتجاه {strongest.direction} بثقة {strongest.net_confidence:.1f} — "
                     f"يعارض الاتجاه المجمّع {decided_direction}"),
        }

    # -- المادة 5.3: التركّز الكلي (منع الالتفاف بتقسيم المراكز) -------------
    @staticmethod
    def aggregate_exposure_violations(
        open_positions: list[dict[str, Any]],
        new_notional: float,
        sector: str,
        capital_usd: float,
        limits: Limits,
    ) -> list[Violation]:
        """
        المادة 8.7 — «تجاوز حدود المخاطر أو الالتفاف عليها **بتقسيم المراكز**».

        لا يكفي فحص المركز الجديد وحده: يجب جمع التعرّض القائم. بدون ذلك يستطيع
        الديسك فتح عشرة مراكز بـ9% لكل منها (= 90% من رأس المال) وكل واحد «تحت الحد».
        """
        v: list[Violation] = []
        total = sum(float(p.get("notional_usd", 0.0)) for p in open_positions) + new_notional
        total_pct = ind_safe_div(total, capital_usd) * 100.0
        if total_pct > limits.max_position_pct + 1e-6:
            v.append(Violation(
                "8.7", "AGGREGATE_EXPOSURE_EXCEEDED",
                f"التعرّض الكلي بعد المركز الجديد {total_pct:.3f}% يتجاوز حد المركز "
                f"{limits.max_position_pct}% — التفاف بتقسيم المراكز", "error", "11"))

        sector_total = (sum(float(p.get("notional_usd", 0.0)) for p in open_positions
                            if str(p.get("sector", "")) == sector) + new_notional)
        sector_pct = ind_safe_div(sector_total, capital_usd) * 100.0
        if sector_pct > limits.max_sector_concentration_pct + 1e-6:
            v.append(Violation(
                "8.7", "SECTOR_EXPOSURE_EXCEEDED",
                f"التعرّض القطاعي «{sector}» بعد المركز الجديد {sector_pct:.3f}% "
                f"يتجاوز الحد {limits.max_sector_concentration_pct}%", "error", "11"))

        if len(open_positions) >= 10 and new_notional > 0:
            v.append(Violation(
                "8.7", "EXCESSIVE_POSITION_COUNT",
                f"{len(open_positions)} مركزاً مفتوحاً — تفتيت يخفي تعرّضاً كلّياً",
                "warning", "11"))
        return v

    # -- المادة 6.3: قرار بلا رأي مخالف ------------------------------------
    def validate_decision_completeness(
        self, supporting: Sequence[str], opposing: Sequence[str], strongest_dissent: str,
        dissent_source: str = "unknown", directional: bool = True
    ) -> list[Violation]:
        """
        المادة 6.3.

        ثغرة مُصلَحة: كان `_strongest_dissent` يُرجع دائماً نصاً احتياطياً مبرمجاً،
        فالحقل **لا يفرغ أبداً** والفحص كان تحصيل حاصل. الآن يُمرَّر `dissent_source`
        للتمييز بين مخالفة حقيقية من وكيل ونص احتياطي.
        """
        v: list[Violation] = []
        if not strongest_dissent or not strongest_dissent.strip():
            v.append(Violation("6.3", "NO_DISSENT_RECORDED",
                               "قرار بلا رأي مخالف مسجّل — يُعاد للمنسّق إلزامياً", "error", "14"))
        elif dissent_source == "fallback":
            v.append(Violation(
                "6.3", "DISSENT_IS_FALLBACK",
                "الرأي المخالف نصّ احتياطي مبرمج لا حجة من وكيل معارض — "
                "المادة 6.3 تطلب رأياً مخالفاً مسجّلاً من مصدره", "warning", "14"))
        elif dissent_source == "none":
            v.append(Violation("6.3", "DISSENT_SOURCE_MISSING",
                               "لم يُحدَّد مصدر الرأي المخالف", "error", "14"))
        if directional and not supporting:
            v.append(Violation("6.3", "NO_SUPPORTING_EVIDENCE",
                               "قرار اتجاهي بلا أي وكيل مؤيد — دليل مفقود", "error", "14"))
        return v

    # -- المادة 9: مستوى الإنذار -------------------------------------------
    def risk_level(self, daily_pnl_pct: float, drawdown_pct: float) -> tuple[str, str]:
        """
        سلّم الإنذار — المادة 9.3.

        ملاحظة: هذا تنفيذ مكرّر لسلّم `RiskEngine.risk_level`. أُبقي للتوافق
        والفحص المستقل، لكن **المصدر الملزم هو `RiskEngine`** لأنه المستدعى في
        مسار التشغيل. أي تعديل على العتبات يجب أن يقع في `Limits` فيقرأه الاثنان.
        """
        if -daily_pnl_pct >= self.limits.max_daily_loss_pct or \
                abs(drawdown_pct) >= self.limits.max_drawdown_pct:
            return "red", "🔴 إيقاف كامل فوري"
        if -daily_pnl_pct >= 1.5:
            return "orange", "🟠 إيقاف المراكز الجديدة"
        if -daily_pnl_pct >= 0.75 or abs(drawdown_pct) >= 0.5 * self.limits.max_drawdown_pct:
            return "yellow", "🟡 تخفيض حجم المركز 50%"
        return "green", "🟢 عمل طبيعي"

    # -- أدوات مساعدة -------------------------------------------------------
    @staticmethod
    def evidence_tier_of(kind: str) -> int:
        return EVIDENCE_TIERS.get(kind, 7)

    def summary(self) -> dict[str, Any]:
        errors = [v for v in self.audit_log if v.severity == "error"]
        warnings = [v for v in self.audit_log if v.severity == "warning"]
        return {
            "total": len(self.audit_log),
            "errors": len(errors),
            "warnings": len(warnings),
            "by_article": _count_by(self.audit_log, "article"),
            "by_code": _count_by(self.audit_log, "code"),
        }


def _count_by(items: Iterable[Violation], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        key = str(getattr(it, attr))
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def ind_safe_div(a: float, b: float, default: float = 0.0) -> float:
    """قسمة آمنة (بلا اعتماد على مكتبة المؤشرات لتفادي دورة استيراد)."""
    return a / b if b else default
