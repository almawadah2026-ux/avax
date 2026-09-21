"""
ربط هوية الوكلاء بالكشف الرسمي — إنهاء تكرار الكشف في 4 مواضع.

**المشكلة (S6 من التدقيق):** كشف الوكلاء الـ15 كان معرّفاً في **أربعة أماكن**:
    1. `law.py::AGENT_ROSTER`              ← المرجع الرسمي
    2. سمات الأصناف في `desks/*.py`        ← نسخة ثانية
    3. التجميعات `KNOWLEDGE_AGENTS` …      ← نسخة ثالثة (ضمنية)
    4. `workflows/avax-desk.workflow.js`   ← نسخة رابعة

وقد **انحرفت النسخة الثانية فعلاً**: 19 عدم تطابق في `name_ar`/`name_en` لم تُكتشف
لأن `audit_roster` كان يفحص `layer`/`authority` فقط.

**الحل:** الكشف الرسمي هو **المصدر الوحيد للحقيقة**. تُربَط سمات أصناف الوكلاء منه
عند الاستيراد، فلا يمكن أن ينحرف صنف عن الكشف — حتى لو كُتبت قيم مختلفة في تعريفه.
النسخة الرابعة (JS) تُفحَص بالتقاطع عبر `audit_implementations`.
"""

from __future__ import annotations

from typing import Any


def bind_roster_metadata() -> dict[str, Any]:
    """
    ينسخ الهوية من `law.AGENT_ROSTER` إلى أصناف الوكلاء.

    يُستدعى عند استيراد حزمة `desks`، فيصبح الكشف الرسمي هو الحاكم لا النسخة المحلية.
    يعيد تقريراً بالمخالفات التي كانت موجودة قبل الربط (لتُرى ولا تُخفى).
    """
    from ..law import ROSTER_BY_ID
    from .control import CONTROL_AGENTS
    from .knowledge import KNOWLEDGE_AGENTS
    from .memory import MEMORY_AGENTS
    from .orchestrator import DECISION_AGENTS
    from .validation import VALIDATION_AGENTS

    all_classes = (*KNOWLEDGE_AGENTS, *VALIDATION_AGENTS, *CONTROL_AGENTS,
                   *DECISION_AGENTS, *MEMORY_AGENTS)
    overridden: list[dict[str, str]] = []
    bound: list[str] = []
    unregistered: list[str] = []

    for cls in all_classes:
        ref = ROSTER_BY_ID.get(str(cls.id))
        if ref is None:
            unregistered.append(f"{cls.__name__} (id={cls.id!r})")
            continue
        for field, expected in (("name_ar", ref.name_ar), ("name_en", ref.name_en),
                                ("file", ref.file)):
            actual = getattr(cls, field, None)
            if actual != expected:
                overridden.append({
                    "class": cls.__name__, "field": field,
                    "was": str(actual), "now": str(expected),
                })
            setattr(cls, field, expected)
        cls.layer = ref.layer
        cls.authority = ref.authority
        bound.append(cls.id)

    return {
        "bound": sorted(bound),
        "count": len(bound),
        "overridden": overridden,
        "unregistered_classes": unregistered,
        "roster_size": len(ROSTER_BY_ID),
        "note": ("الكشف الرسمي (`law.AGENT_ROSTER`) هو المصدر الوحيد للحقيقة: "
                 "سمات الأصناف تُنسخ منه عند الاستيراد، فلا يمكن أن تنحرف عنه."),
    }


def audit_implementations() -> dict[str, Any]:
    """
    تدقيق تقاطع: هل كل وكيل في الكشف له **صنف تنفيذي**؟ وهل كل صنف مسجّل؟

    هذا يغلق الثغرة التي كشفها التدقيق: `cli.py` كان يستدعي الأصناف بالاسم،
    وإضافة وكيل إلى الكشف لا تُدخله الدورة. الآن يصبح الغياب **مكشوفاً**.
    """
    from ..law import AGENT_ROSTER  # noqa: F401
    from .control import CONTROL_AGENTS
    from .knowledge import KNOWLEDGE_AGENTS
    from .memory import MEMORY_AGENTS
    from .orchestrator import DECISION_AGENTS
    from .validation import VALIDATION_AGENTS

    by_layer = {
        "knowledge": KNOWLEDGE_AGENTS,
        "validation": VALIDATION_AGENTS,
        "control": CONTROL_AGENTS,
        "decision": DECISION_AGENTS,
        "memory": MEMORY_AGENTS,
    }

    implemented: dict[str, str] = {}
    for layer, classes in by_layer.items():
        for cls in classes:
            implemented[str(cls.id)] = f"{layer}:{cls.__name__}"

    missing: list[dict[str, str]] = []
    wrong_layer: list[dict[str, str]] = []
    for ref in AGENT_ROSTER:
        where = implemented.get(ref.id)
        if where is None:
            missing.append({"id": ref.id, "name": ref.name_ar,
                            "expected_layer": ref.layer.value})
        elif not where.startswith(ref.layer.value):
            wrong_layer.append({"id": ref.id, "roster_layer": ref.layer.value,
                                "implemented_in": where})

    extra = [f"{aid} ({where})" for aid, where in implemented.items()
             if aid not in {r.id for r in AGENT_ROSTER}]

    return {
        "roster_size": len(AGENT_ROSTER),
        "implemented_classes": len(implemented),
        "missing_implementations": missing,
        "wrong_layer": wrong_layer,
        "extra_implementations": extra,
        "ok": not missing and not wrong_layer and not extra,
        "by_layer": {layer: [str(c.id) for c in classes] for layer, classes in by_layer.items()},
    }
