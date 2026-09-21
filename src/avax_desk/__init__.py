"""
ديسك أفالانش — AVAX Trading Desk
================================

فريق وكلاء ذكاء اصطناعي متخصصين في تحليل منظومة Avalanche / AVAX.

القاعدة الدستورية الحاكمة (المادة 0.2):
    هذا النظام **لا ينفّذ صفقات حقيقية**. لا مفاتيح API، لا محافظ، لا أوامر مالية.
    كل مخرج هو رأي مُعلَّل قابل للتدقيق، لا نصيحة مالية ولا أمر تنفيذ.
"""

from .config import DeskConfig, Limits
from .contracts import (
    AgentOpinion,
    ComplianceReport,
    DeskDecision,
    Evidence,
    ExecutionPlan,
    JournalRecord,
    RiskVerdict,
)
from .law import LawEngine, Violation

__version__ = "1.0.0"

__all__ = [
    "DeskConfig",
    "Limits",
    "Evidence",
    "AgentOpinion",
    "RiskVerdict",
    "ExecutionPlan",
    "ComplianceReport",
    "DeskDecision",
    "JournalRecord",
    "LawEngine",
    "Violation",
    "__version__",
]
