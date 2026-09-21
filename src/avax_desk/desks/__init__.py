"""
الوكلاء — طبقات المعرفة والتحقق والضبط والقرار والذاكرة.

عند استيراد هذه الحزمة تُربَط سمات أصناف الوكلاء من **الكشف الرسمي**
(`law.AGENT_ROSTER`) عبر `_binding.bind_roster_metadata()`. النتيجة:
مصدر واحد للحقيقة، ويستحيل أن ينحرف صنف عن الكشف.
"""

from .base import AgentContext, BaseAgent, compute_features, make_opinion

__all__ = ["AgentContext", "BaseAgent", "compute_features", "make_opinion"]

#: تقرير الربط بالكشف الرسمي — يُتاح للتشخيص والتدقيق
ROSTER_BINDING: dict = {}


def _bind() -> None:
    """
    يُنفَّذ مرة واحدة عند الاستيراد.

    الترتيب مقصود: تُستورد الأصناف داخل الدالة لا في المستوى الأعلى، لتفادي
    أي دورة استيراد (الأصناف تستورد `base` الذي يستورد `law`).
    """
    global ROSTER_BINDING
    try:
        from ._binding import bind_roster_metadata
        ROSTER_BINDING = bind_roster_metadata()
    except Exception as exc:  # noqa: BLE001 — الربط لا يجوز أن يُسقط الاستيراد
        ROSTER_BINDING = {"error": f"{type(exc).__name__}: {exc}"}


_bind()
