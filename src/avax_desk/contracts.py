"""
عقود البيانات — البيانات المشتركة بين كل الوكلاء.

كل عقد هنا يترجم مادة من الدستور إلى بنية بيانات قابلة للفحص آلياً.

**حدود ما يُفرَض عند البناء:** `Evidence` و`AgentOpinion` و`RiskVerdict` تفرض قيودها
في `__post_init__` فور الإنشاء. أما `DeskDecision` و`ComplianceReport` و`ExecutionPlan`
فلا تفرض قيوداً بنيوية — تُفحَص في `ComplianceAgent.audit_decision` بعد الإصدار
(لأن بعض قيودها تعتمد على سياق الدورة لا على الكائن وحده). لا تدّعِ أكثر من ذلك.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------
# أدوات زمنية
# --------------------------------------------------------------------------

def now_iso() -> str:
    """الطابع الزمني الحالي بصيغة ISO-8601 بمنطقة UTC — المادة 2.5."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def age_hours(value: str) -> float:
    """عمر الطابع الزمني بالساعات — يُستخدم لكشف البيانات القديمة (المادة 3.4)."""
    try:
        delta = datetime.now(timezone.utc) - parse_iso(value)
        return max(0.0, delta.total_seconds() / 3600.0)
    except Exception:
        return 1e9  # طابع زمني غير صالح ⇒ يُعامل كبيانات ميتة


# --------------------------------------------------------------------------
# التصنيفات
# --------------------------------------------------------------------------

class Layer(str, Enum):
    """طبقات الديسك — المادة 1.1."""

    KNOWLEDGE = "knowledge"
    VALIDATION = "validation"
    CONTROL = "control"
    DECISION = "decision"
    MEMORY = "memory"


class Authority(str, Enum):
    """الصلاحيات — المادة 1.1."""

    ADVISORY = "advisory"
    VETO = "veto"
    DECISION = "decision"
    RECORD = "record"


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Strength(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLevel(str, Enum):
    """سلّم الإنذار — المادة 9.3."""

    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


class Action(str, Enum):
    """
    قرارات الديسك الممكنة.

    ⚠️ **حالة محجوزة:** `FLAT` («البقاء خارج السوق / إغلاق مركز قائم») **لا مُنتِج لها
    حالياً** — `OrchestratorAgent.finalize` يُصدر `LONG` أو `SHORT` أو `ABSTAIN`.
    سبب الإبقاء: الديسك لا يحمل حالة محفظة، ولا يمكن التمييز بين «لم ندخل» و«خرجنا»
    بلا `open_positions`. عند ربط حالة المحفظة فعلياً يصبح `FLAT` ذا معنى.
    (كانت حالة ميتة بلا توثيق — والآن موثّقة صراحةً بدل إيهام القارئ بوجودها.)
    """

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"
    ABSTAIN = "ABSTAIN"


#: هرمية الأدلة — CONSTITUTION.md المادة 3.1
#: الرقم الأصغر = دليل أقوى. 1 هو الأقوى، 7 هو الأضعف.
EVIDENCE_TIERS: dict[str, int] = {
    "onchain": 1,      # بيانات أونشين موقّعة ومباشرة من الشبكة
    "market": 2,       # بيانات السوق من منصات متعددة
    "derived": 3,      # إحصاءات مشتقة بمنهج معلن
    "technical": 4,    # مؤشرات فنية محسوبة من أسعار
    "sentiment": 5,    # تحليل معنويات مُصنَّف
    "expert": 6,       # رأي خبير / مصدر صحفي
    "inference": 7,    # استنتاج استنباطي بلا مصدر
}

TIER_LABELS: dict[int, str] = {
    1: "بيانات أونشين مباشرة",
    2: "بيانات سوق من منصات",
    3: "إحصاء مشتق بمنهج معلن",
    4: "مؤشر فني محسوب",
    5: "تحليل معنويات",
    6: "رأي خبير / صحافة",
    7: "استنتاج بلا مصدر",
}


# --------------------------------------------------------------------------
# الدليل — المادة 2.5 و 3.1
# --------------------------------------------------------------------------

@dataclass
class Evidence:
    """
    وحدة الدليل. أي رقم بلا مصدر أو طابع زمني يُرفض عند الإنشاء (المادة 2.5).
    """

    claim: str
    source: str
    timestamp: str
    kind: str = "derived"          # مفتاح من EVIDENCE_TIERS
    strength: str = Strength.MEDIUM.value
    value: float | None = None

    def __post_init__(self) -> None:
        if not self.claim or not self.claim.strip():
            raise ValueError("دليل بلا ادّعاء — المادة 2.5")
        src = (self.source or "").strip()
        lowered = src.lower()
        # رفض المصادر الوهمية. ملاحظة مهمة: الفحص **بالقيمة الكاملة أو بعبارة
        # كاملة**، لا بمطابقة جزئية — وإلا وقعنا في إيجابية كاذبة مثل مطابقة
        # "n/a" داخل المسار «c-chai**n/a**ctive-addresses».
        bogus_exact = {"", "unknown", "n/a", "na", "none", "null", "nil",
                       "غير معروف", "مجهول", "-", "?", "—", "tbd", "todo"}
        bogus_phrases = ("غير معروف", "مصدر مجهول", "unknown source",
                         "lorem ipsum", "placeholder", "to be determined")
        if lowered in bogus_exact or any(p in lowered for p in bogus_phrases):
            raise ValueError(
                f"دليل بلا مصدر موثّق: {self.claim!r} (المصدر: {self.source!r}) — "
                f"المادة 2.5 (رقم بلا مصدر = رقم مُختلق)"
            )
        if not self.timestamp:
            raise ValueError(f"دليل بلا طابع زمني: {self.claim!r} — المادة 2.5")
        if self.kind not in EVIDENCE_TIERS:
            raise ValueError(f"نوع دليل غير معروف: {self.kind!r}. المسموح: {sorted(EVIDENCE_TIERS)}")

    @property
    def tier(self) -> int:
        """قوة الدليل وفق هرمية المادة 3.1 — الأصغر أقوى."""
        return EVIDENCE_TIERS[self.kind]

    @property
    def tier_label(self) -> str:
        return TIER_LABELS[self.tier]

    def staleness(self, threshold_hours: float = 24.0) -> bool:
        """هل الدليل قديم؟ — المادة 3.4."""
        return age_hours(self.timestamp) > threshold_hours

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# رأي الوكيل — المادة 2 (عقد الرأي)
# --------------------------------------------------------------------------

@dataclass
class AgentOpinion:
    """
    عقد الرأي — CONSTITUTION.md المادة 2.

    الحقول الستة الإلزامية: thesis, evidence, confidence, horizon, invalidation, dissent.
    رأي بلا شرط إبطال يُرفض آلياً (المادة 2.2).
    """

    agent_id: str
    agent_name: str
    thesis: str
    evidence: list[Evidence]
    confidence: float
    horizon: str
    invalidation: str
    dissent: str
    direction: str = Direction.NEUTRAL.value
    abstain: bool = False
    abstain_reason: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # -- قيود البناء الفورية ------------------------------------------------
    def __post_init__(self) -> None:
        if not (0.0 <= float(self.confidence) <= 100.0):
            raise ValueError(f"[{self.agent_id}] الثقة خارج النطاق 0-100: {self.confidence}")
        if self.direction not in {d.value for d in Direction}:
            raise ValueError(f"[{self.agent_id}] اتجاه غير معروف: {self.direction!r}")

    # -- خصائص مساعدة ------------------------------------------------------
    @property
    def net_confidence(self) -> float:
        """الثقة بعد خصم البيانات القديمة — المادة 3.4."""
        if self.abstain:
            return 0.0
        return max(0.0, self.confidence - self.staleness_penalty())

    def staleness_penalty(self, threshold_hours: float | None = None,
                          max_penalty_pct: float | None = None) -> float:
        """
        خصم التقادم — المادة 3.4: «البيانات الأقدم من الحد تُوسم STALE وتُخفَّض
        ثقتها بنسبة 30%».

        التطبيق: الخصم نسبي بحسب حصة الأدلة القديمة من إجمالي الأدلة، بسقف
        نسبة الخصم المعرّفة في `Limits.stale_confidence_penalty`.
        القيم تُقرأ من الإعدادات لا من ثوابت مضمّنة.
        """
        from .config import Limits

        limits = Limits()
        threshold = limits.stale_hours if threshold_hours is None else threshold_hours
        cap_pct = (limits.stale_confidence_penalty * 100.0
                   if max_penalty_pct is None else max_penalty_pct)
        if not self.evidence:
            return 0.0
        stale = sum(1 for e in self.evidence if age_hours(e.timestamp) > threshold)
        if not stale:
            return 0.0
        return (stale / len(self.evidence)) * cap_pct

    @property
    def best_tier(self) -> int:
        return min((e.tier for e in self.evidence), default=7)

    @property
    def directional_sign(self) -> int:
        return {Direction.BULLISH.value: 1, Direction.BEARISH.value: -1}.get(self.direction, 0)

    @classmethod
    def abstain_opinion(
        cls, agent_id: str, agent_name: str, reason: str
    ) -> "AgentOpinion":
        """
        الامتناع — المادة 9. الامتناع أفضل من رأي ضعيف ولا يُعاقب.
        """
        return cls(
            agent_id=agent_id,
            agent_name=agent_name,
            thesis="امتناع عن إصدار رأي",
            evidence=[],
            confidence=0.0,
            horizon="—",
            invalidation="—",
            dissent="—",
            direction=Direction.NEUTRAL.value,
            abstain=True,
            abstain_reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [e.to_dict() for e in self.evidence]
        data["net_confidence"] = round(self.net_confidence, 2)
        data["best_tier"] = self.best_tier
        return data


# --------------------------------------------------------------------------
# قرار المخاطر — المادة 5
# --------------------------------------------------------------------------

@dataclass
class RiskVerdict:
    """
    حكم وكيل المخاطر. حق النقض مطلق ولا يُتجاوز (المادة 5.1).
    """

    approved: bool
    veto: bool
    risk_level: str = RiskLevel.GREEN.value
    max_position_pct: float = 0.0
    #: الحجم **المعتمد** فعلياً — صفر إذا وُجد نقض
    position_size_usd: float = 0.0
    #: الحجم **المحسوب** قبل النقض — للتوثيق والمراجعة فقط، غير قابل للاستخدام
    computed_size_usd: float = 0.0
    stop_loss_pct: float = 0.0
    risk_per_trade_pct: float = 0.0
    veto_reasons: list[str] = field(default_factory=list)
    limits_checked: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        """
        فرض الاتساق: الثلاثي (approved / veto / position_size_usd) لا يجوز أن يتناقض.
        (كان هذا العقد بلا تحقق، فصار ممكناً بناء حكم «معتمد بحجم صفر» أو «منقوض بحجم موجب».)
        """
        if self.approved and self.veto:
            raise ValueError("حكم مخاطر متناقض: approved=True مع veto=True")
        if self.approved and self.position_size_usd <= 0:
            raise ValueError("حكم مخاطر متناقض: معتمد بحجم صفري")
        if self.veto and self.position_size_usd > 0:
            raise ValueError("حكم مخاطر متناقض: منقوض بحجم موجب")
        if self.risk_level not in {r.value for r in RiskLevel}:
            raise ValueError(f"مستوى إنذار غير معروف: {self.risk_level!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# خطة التنفيذ — مخرجات الوكيل 12 (تنفيذ ورقي فقط، المادة 0.2)
# --------------------------------------------------------------------------

@dataclass
class ExecutionPlan:
    """
    خطة تنفيذ نظرية. هذا **ليس أمراً** — لا يُرسل لأي منصة (المادة 0.2).
    """

    method: str = "VWAP"
    slices: int = 0
    participation_pct: float = 0.0
    expected_slippage_bps: float = 0.0
    expected_cost_usd: float = 0.0
    schedule: list[dict[str, Any]] = field(default_factory=list)
    venue_notes: list[str] = field(default_factory=list)
    disclaimer: str = "خطة نظرية للتحليل فقط — لا تنفيذ حقيقي (المادة 0.2)"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# تقرير الالتزام — المادة 8
# --------------------------------------------------------------------------

@dataclass
class ComplianceReport:
    compliant: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    checked_agents: int = 0
    blocked: bool = False
    notes: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# القرار النهائي — المادة 6
# --------------------------------------------------------------------------

@dataclass
class DeskDecision:
    """القرار النهائي للديسك، مع حفظ الرأي المخالف إلزامياً (المادة 6)."""

    decision_id: str
    asset: str
    action: str
    confidence: float
    horizon: str
    invalidation: str
    rationale: str
    supporting_agents: list[str] = field(default_factory=list)
    opposing_agents: list[str] = field(default_factory=list)
    abstaining_agents: list[str] = field(default_factory=list)
    strongest_dissent: str = ""
    #: مصدر الرأي المخالف: "agent" حقيقي · "fallback" نص احتياطي · "none" غائب (المادة 6.3)
    dissent_source: str = "none"
    #: نوع الامتناع: "no_edge" لا حافة · "risk_veto" نقض · "compliance_block" حجب · "halted" إيقاف
    abstention_kind: str = ""
    #: أسباب المنع صريحة (كانت تُدمج في نص المبرر فقط)
    blocks: list[str] = field(default_factory=list)
    groupthink_flag: bool = False
    entry_zone: list[float] = field(default_factory=list)
    stop_price: float | None = None
    targets: list[float] = field(default_factory=list)
    size_usd: float = 0.0
    risk_verdict: RiskVerdict | None = None
    execution_plan: ExecutionPlan | None = None
    compliance: ComplianceReport | None = None
    evidence_summary: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=now_iso)

    @staticmethod
    def new_id() -> str:
        return f"DEC-{uuid.uuid4().hex[:10].upper()}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.risk_verdict:
            data["risk_verdict"] = self.risk_verdict.to_dict()
        if self.execution_plan:
            data["execution_plan"] = self.execution_plan.to_dict()
        if self.compliance:
            data["compliance"] = self.compliance.to_dict()
        return data


# --------------------------------------------------------------------------
# سجل غير قابل للتعديل — المادة 7
# --------------------------------------------------------------------------

@dataclass
class JournalRecord:
    """
    سجل الدورة. مربوط بسلسلة هاش (Hash Chain) — المادة 7.2:
    السجل غير قابل للتعديل بعد الكتابة؛ أي تعديل يكسر السلسلة.
    """

    record_id: str
    sequence: int
    payload: dict[str, Any]
    previous_hash: str = "GENESIS"
    timestamp: str = field(default_factory=now_iso)
    record_hash: str = ""

    def hash_body(self) -> str:
        """جسم السجل المُوقَّع — مُفصول ليُتيح توقيعاً بمفتاح (HMAC) من الخارج."""
        return json.dumps(
            {
                "record_id": self.record_id,
                "sequence": self.sequence,
                "timestamp": self.timestamp,
                "previous_hash": self.previous_hash,
                "payload": self.payload,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    def compute_hash(self) -> str:
        return hashlib.sha256(self.hash_body().encode("utf-8")).hexdigest()

    def seal(self, digest_fn: Any = None) -> "JournalRecord":
        """يختم السجل. `digest_fn` تتيح توقيعاً بمفتاح خارجي (HMAC)."""
        self.record_hash = digest_fn(self.hash_body()) if digest_fn else self.compute_hash()
        return self

    def verify(self, digest_fn: Any = None) -> bool:
        expected = digest_fn(self.hash_body()) if digest_fn else self.compute_hash()
        return bool(self.record_hash) and self.record_hash == expected

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
