"""
تسجيل دورة القرار ABSTAIN (CYC-2026-0921-0009Z) في السجل غير القابل للتعديل.

الوكيل 15 — وكيل الذاكرة والسجل (المادة 1.1 «التسجيل»، والمواد 6، 7.1–7.4، 8.2، 8.4، 8.9).

المبادئ المُنفَّذة هنا:
  * لا يُعدّل أي إدخال سابق — الإدخال الجديد يشير للقديم (المادة 7.2).
    الإدخال السابق: JRN-50D66DF37D97 (الدورة CYC-2026-0920-2322Z).
  * لا يُحمَّل «ما عرفناه لاحقاً» على القرار: لقطة المدخلات مثبَّتة ببصمة sha256 (المادة 8.2).
  * لا تخفيض أوزان بلا نمط مُثبت مكرر 3 مرات (المادة 7.4) — السكربت يرفض التخفيض ويشرحه.
  * لا يُزايد على الأدلة: كل ادعاء إمّا «قرأتُه» (ببصمة) أو «لم يُسلَّم» (مُعلن).

الاستعمال:
    python tools/record_cycle_15_20260921.py --probe     # بناء الحمولة بلا كتابة
    python tools/record_cycle_15_20260921.py --record    # تسجيل الدورة (كتابة مرة واحدة)
    python tools/record_cycle_15_20260921.py --verify     # التحقق من سلامة السلسلة
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from avax_desk.journal.store import JournalStore  # noqa: E402

CANONICAL = ROOT / "journal" / "desk_journal.jsonl"
ARCHIVE = ROOT / "journal" / "archive" / "desk_journal_demo.jsonl"
INPUT = ROOT / "journal" / "records" / "CYC-2026-0921-0009Z.input.json"
CYCLE_MD = ROOT / "journal" / "CYC-2026-0921-0009Z.md"

CYCLE_ID = "CYC-2026-0921-0009Z"
DATA_AS_OF = "2026-09-21T00:09:44+00:00"          # _meta.generated_at للقطة (366 شمعة، seed=11، bull)
HORIZON_END = "2026-09-22T00:09:44+00:00"          # = اللقطة + 24 ساعة (المادة 3.4) — وهو الأفق المُعلن في القرار
REVIEW_DATE = "2026-09-22T00:09:44+00:00"          # المراجعة البعدية الإلزامية (المادة 7.3)
RECORDED_AT_APPROX = "2026-09-21T00:54:54Z"        # ساعة النظام لحظة بدء التسجيل (الطابع النهائي يُنتجه now_iso)
PREDECESSOR_RECORD = "JRN-50D66DF37D97"
PREDECESSOR_CYCLE = "CYC-2026-0920-2322Z"

# ملفات لقطة الأدلة لحظة القرار — تُثبَّت ببصمة sha256 (المادة 8.2)
EVIDENCE_FILES: list[tuple[str, str]] = [
    ("CONSTITUTION.md", "الدستور الملزم — بصمته داخل السجل (المادة 10.1)"),
    ("journal/records/CYC-2026-0921-0009Z.input.json",
     "لقطة مدخلات القرار: نصّ قرار 14 حرفياً + نصّ النقض كما ورد في blocks + إقرار بالملفات الغائبة"),
    ("data/snapshot_full.json", "لقطة البيانات as_of 2026-09-21T00:09:44Z — synthetic-deterministic seed=11 scenario=bull، 366 شمعة"),
    ("reports/agent-01-market-structure-2026-09-21.json", "رأي 01 لهذه الدورة — الحقول الستة + abstain_reason حاضرة"),
    ("reports/agent-02-technical-analysis.json", "رأي 02 لهذه الدورة — الحقول الستة + abstain_reason حاضرة"),
    ("reports/agent-08-portfolio-theory.json", "رأي 08 لهذه الدورة — الحقول الستة + abstain_reason حاضرة"),
    ("reports/agent-09-validation-verdict-2026-09-21.md", "حكم التحقق 09: إبطال جزئي + سقف الدورة 64، ثقة 78"),
    ("reports/agent-09-validation-verdict-2026-09-21.json", "حكم التحقق 09 (نسخة JSON)"),
    ("reports/redteam-10-challenge-2026-09-21.md", "محامي الشيطان 10 — الحجة المضادة المحفوظة بنصّها"),
    ("reports/agent-13-compliance-report-2026-09-21.md", "تقرير الالتزام 13 = FAIL (36/54 = 0.667) + النقض CVETO-2026-0921-13-01"),
    ("journal/desk_journal.jsonl", "السلسلة المعيارية قبل الإضافة (إدخال واحد: JRN-50D66DF37D97)"),
    ("journal/archive/desk_journal_demo.jsonl", "السلسلة التاريخية المؤرشفة (خوانية منفصلة) — لا تُعدَّل"),
]

# آراء الدورة: ما هو مُثبَّت كملف، وما ذُكر في تدقيق 13، وما هو غائب.
# الأمانة في العدّ: لا يُنسب ملف لوكيل بلا بصمة ملف (المادتان 2.5 و3.3).
OPINION_ARTIFACT_STATUS = {
    "01": {"file": "reports/agent-01-market-structure-2026-09-21.json", "form": "file"},
    "02": {"file": "reports/agent-02-technical-analysis.json", "form": "file"},
    "03": {"file": None, "form": "audit_only", "note": "13 عدّ 31 دليلاً وثقة 45 — لا ملف خام في الشجرة"},
    "04": {"file": None, "form": "audit_only", "note": "13 عدّ 20 دليلاً وثقة 53، و09 أبطلها اتجاهياً — لا ملف خام"},
    "05": {"file": None, "form": "audit_only", "note": "13 عدّ 14 دليلاً وثقة 64 (أعلى ثقة في الدورة) — لا ملف خام"},
    "06": {"file": None, "form": "audit_only", "note": "13 عدّ 21 دليلاً وثقة 48 — لا ملف خام لهذه الدورة (ملفات 06 في الشجرة لدورات سابقة)"},
    "07": {"file": None, "form": "audit_only", "note": "13 عدّ 11 دليلاً وثقة 22 + ملاحظة وسم الطبقة F2 — لا ملف خام"},
    "08": {"file": "reports/agent-08-portfolio-theory.json", "form": "file"},
    "09": {"file": "reports/agent-09-validation-verdict-2026-09-21.md", "form": "file"},
    "10": {"file": "reports/redteam-10-challenge-2026-09-21.md", "form": "file"},
    "11": {"file": None, "form": "quoted_in_decision", "note": "RiskVerdict خام لم يُسلَّم؛ المضمون منقول في blocks/rationale"},
    "12": {"file": None, "form": "absent", "note": "لا خطة تنفيذ مُقدَّمة (اختياري: لا مركز)"},
    "13": {"file": "reports/agent-13-compliance-report-2026-09-21.md", "form": "file"},
    "14": {"file": "journal/records/CYC-2026-0921-0009Z.input.json", "form": "file", "note": "نصّ القرار نفسه مُثبَّت في لقطة المدخلات"},
}

SIX_FIELDS = ["thesis", "evidence", "confidence", "horizon", "invalidation", "dissent"]


def sha256_file(rel: str) -> str | None:
    p = ROOT / rel
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def raw_opinion_audit() -> dict:
    """
    فحص قابل لإعادة الإنتاج على الملفات الخام المتاحة فعلاً في الشجرة.

    الغرض: فصل «الادعاء» عن «الأثر» — هل نقص الحقول الستة (ملاحظة 13: F1) موجود في الأصول
    أم في حزمة التسليم فقط؟ الجواب يُقاس هنا لا يُدَّعى (المادتان 3.3 و8.2).
    """
    out: dict = {"checked": {}, "unavailable": [], "evidence_count_mismatch": []}
    for aid in ("01", "02", "08"):
        rel = OPINION_ARTIFACT_STATUS[aid]["file"]
        p = ROOT / rel
        data = json.loads(p.read_text(encoding="utf-8"))
        present = {f: data.get(f) not in (None, "", [], {}) for f in SIX_FIELDS}
        ev = data.get("evidence") or []
        out["checked"][aid] = {
            "file": rel,
            "snapshot_as_of": data.get("snapshot_as_of"),
            "direction": data.get("direction"),
            "confidence": data.get("confidence"),
            "six_fields_present": present,
            "six_fields_count": sum(present.values()),
            "abstain": data.get("abstain"),
            "abstain_reason_present": data.get("abstain_reason") not in (None, "", [], {}),
            "evidence_items_in_file": len(ev),
        }
    for aid in ("03", "04", "05", "06", "07"):
        out["unavailable"].append(aid)
    out["evidence_count_mismatch"] = [
        {"agent": "02", "audit_13_count": 12, "raw_file_count": out["checked"]["02"]["evidence_items_in_file"],
         "delta": out["checked"]["02"]["evidence_items_in_file"] - 12,
         "source": "reports/agent-13-compliance-report-2026-09-21.md §2 مقابل reports/agent-02-technical-analysis.json"},
        {"agent": "01", "audit_13_count": 16, "raw_file_count": out["checked"]["01"]["evidence_items_in_file"],
         "delta": out["checked"]["01"]["evidence_items_in_file"] - 16},
        {"agent": "08", "audit_13_count": 14, "raw_file_count": out["checked"]["08"]["evidence_items_in_file"],
         "delta": out["checked"]["08"]["evidence_items_in_file"] - 14},
    ]
    return out


def _assert_partitions(payload: dict) -> None:
    """
    حارس عدّ: يمنع تكرار الخطأ المُصحَّح في الإدخال JRN-EE42E4AB5CA0.

    الدرس المُسجَّل (النمط F-14): حقلٌ عددي في سجل دائم كُتب بلا تحقق من تطابق الأقسام.
    هنا يُفرض: مجموع أقسام الآراء = عدد الوكلاء المتوقع، ومجموع أجزاء الثقة = الثقة المُعلنة.
    """
    total = (payload["opinions_present_verifiable"] + payload["opinions_quoted_only"]
             + payload["opinions_audit_only"] + payload["opinions_absent"])
    if total != payload["opinions_expected"]:
        raise ValueError(f"⛔ أقسام الآراء لا تطابق الإجمالي: {total} ≠ {payload['opinions_expected']}")
    files = sum(1 for o in payload["opinions_digest"] if o.get("artifact") == "file")
    if files != payload["opinions_present_verifiable"]:
        raise ValueError(f"⛔ عدد الآراء ذات الملفات ({files}) ≠ الحقل المُعلن "
                         f"({payload['opinions_present_verifiable']})")
    proj = payload["proposal"]
    parts = proj["base_confidence"] + sum(float(p.split()[0].replace("−", "-")) for p in proj["penalties"])
    if abs(parts - proj["resulting_confidence"]) > 0.05:
        raise ValueError(f"⛔ أجزاء الثقة لا تطابق الناتج: {parts} ≠ {proj['resulting_confidence']}")


def archive_report() -> dict:
    """قراءة السلسلة التاريخية المؤرشفة — قراءة فقط، بلا كتابة (المادة 7.2)."""
    if not ARCHIVE.exists():
        return {"available": False}
    store = JournalStore(ARCHIVE)
    chain = store.verify_chain()
    return {
        "available": True,
        "path": str(ARCHIVE.relative_to(ROOT)),
        "sha256": sha256_file("journal/archive/desk_journal_demo.jsonl"),
        "records": chain["records"],
        "chain_valid": chain["valid"],
        "head_hash": chain["head_hash"],
        "anchor_check": chain["anchor_check"],
        "history_weights": store.agent_weights(),
        "calibration": store.calibration(),
    }


def canonical_state() -> dict:
    store = JournalStore(CANONICAL)
    chain = store.verify_chain()
    recs = store.records()
    return {
        "records": chain["records"],
        "valid": chain["valid"],
        "head_hash": chain["head_hash"],
        "anchor_check": chain["anchor_check"],
        "sequences": [(r.sequence, r.record_id, r.timestamp) for r in recs],
        "weights": store.agent_weights(),
        "calibration": store.calibration(),
    }


def assigned_decision_id() -> str:
    digest = sha256_file("journal/records/CYC-2026-0921-0009Z.input.json") or ""
    return f"DEC-{digest[:10].upper()}"


def build_payload() -> dict:
    delivered = json.loads(INPUT.read_text(encoding="utf-8"))
    dec_in = delivered["delivered_decision"]
    rv_in = delivered["risk_veto_as_delivered_in_decision"]
    archive = archive_report()
    canon = canonical_state()
    raw = raw_opinion_audit()

    evidence = []
    for rel, note in EVIDENCE_FILES:
        digest = sha256_file(rel)
        evidence.append({
            "claim": f"بصمة sha256 للملف {rel}: {digest or 'غير موجود'}",
            "source": rel,
            "timestamp": DATA_AS_OF,
            "kind": "derived",
            "strength": "high" if digest else "low",
            "note": note,
        })

    decision = {
        "decision_id": assigned_decision_id(),
        "decision_id_note": ("معرّف مُنشأ من الوكيل 15 اشتقاقاً من بصمة لقطة المدخلات — القرار المُسلَّم لم يحمل "
                             "معرّفاً؛ لم يُختلق معرّف ولا طابع زمني (المادتان 2.5 و8.1)"),
        "asset": "AVAX",
        "action": dec_in["action"],
        "confidence": dec_in["confidence"],
        "horizon": dec_in["horizon"],
        "invalidation": dec_in["invalidation"],
        "rationale": dec_in["rationale"],
        "supporting_agents": dec_in["supporting_agents"],
        "opposing_agents": dec_in["opposing_agents"],
        "abstaining_agents": ["01", "02", "05", "07", "08"],
        "directional_agents": [{"agent": "04", "direction": "bearish", "confidence": 53.0,
                                "status": "INVALIDATED اتجاهياً بحكم 09"}],
        "strongest_dissent": dec_in["strongest_dissent"],
        "dissent_source": "agent",
        "dissent_source_agent": "10",
        "abstention_kind": "risk_veto",
        "blocks": dec_in["blocks"],
        "groupthink_flag": False,
        "entry_zone": [],
        "stop_price": None,
        "targets": [],
        "size_usd": 0.0,
        "risk_verdict": rv_in,
        "execution_plan": None,
        "compliance": {
            "compliant": False,
            "checked_agents": 9,
            "blocked": True,
            "verdict": "FAIL",
            "rate": 0.667,
            "rate_expression": "36/54",
            "veto_id": "CVETO-2026-0921-13-01",
            "serious_findings": 8,
            "audited_at": "2026-09-21T00:48:52+00:00",
            "scope_note": ("تدقيق 13 غطّى 8 آراء + حكم المخاطر؛ مخرجات 09/10/12/14/15 لم تُسلَّم في حزمة الدورة "
                           "لديه (ملاحظته F16)"),
            "contested_basis": ("قاعدة العدّ 36/54 تحتوي F1 (2.1 = 0/8) وF7 (9.1 = 0/5). أثر الأصل المتاح "
                                "يُكذّب ذلك لـ3 من 8: الملفات الخام لـ01 و02 و08 تحمل الحقول الستة كاملة "
                                "وabstain_reason (انظر six_field_reproduction). لا يُعدَّل تقرير 13؛ يُسجَّل "
                                "التعارض في هذا الإدخال الجديد (المادة 7.2)، وأثره: هامش FAIL موضع نزاع لا صفر، "
                                "مع بقاء النقض المخاطري (5.1) قائماً ومستقلاً عن هذه الملاحظة"),
            "timestamp": "2026-09-21T00:48:52+00:00",
        },
        "evidence_summary": evidence,
        "timestamp": "",
        "timestamp_note": ("القرار المُسلَّم لم يحمل طابعاً زمنياً؛ وقت التسجيل يُنتجه now_iso() ووقت البيانات هو "
                           "data_as_of. لم أُسند للقرار وقتاً لم يُقدَّم (المادتان 2.5 و8.1)"),
    }

    opinions_digest = [
        {"agent_id": "01", "direction": "abstain", "confidence": 35.0, "artifact": "file",
         "stake": "امتناع + خريطة بنية سوق؛ الحقول الستة حاضرة في الأصل الخام"},
        {"agent_id": "02", "direction": "abstain", "confidence": 30.0, "artifact": "file",
         "stake": "امتناع عن الاتجاه + خريطة مخاطر؛ الحقول الستة وabstain_reason حاضرة في الأصل الخام"},
        {"agent_id": "03", "direction": "neutral", "confidence": 45.0, "artifact": "audit_only",
         "stake": "محايد اتجاهياً (الثقة 45 بحسب تدقيق 13؛ الأصل الخام غير موجود في الشجرة)"},
        {"agent_id": "04", "direction": "bearish", "confidence": 53.0, "artifact": "audit_only",
         "stake": "الإشارة الاتجاهية الوحيدة — أبطلها 09 اتجاهياً (−25) لبناء أساسها على حقول مولَّدة"},
        {"agent_id": "05", "direction": "abstain", "confidence": 64.0, "artifact": "audit_only",
         "stake": "امتناع؛ ثقته 64 سقفُ الدورة الفعلي (دون عتبة الدخول 65 بدرجة واحدة)"},
        {"agent_id": "06", "direction": "neutral", "confidence": 48.0, "artifact": "audit_only",
         "stake": "محايد؛ ملف 06 لهذه الدورة غير موجود في الشجرة (الموجود لدورات سابقة)"},
        {"agent_id": "07", "direction": "abstain", "confidence": 22.0, "artifact": "audit_only",
         "stake": "امتناع + ملاحظة وسم طبقة F2 بحكم 13"},
        {"agent_id": "08", "direction": "neutral", "confidence": 40.0, "artifact": "file",
         "stake": "مخرج قيد لا أمر؛ الحقول الستة وabstain_reason حاضرة في الأصل الخام"},
        {"agent_id": "09", "direction": "neutral", "confidence": 78.0, "artifact": "file",
         "stake": "إبطال جزئي + تخفيض ثقة + سقف دورة مُثبَّت 64؛ الحقول الستة كاملة في حكمه"},
        {"agent_id": "10", "direction": "bearish", "confidence": None, "artifact": "file",
         "stake": "حجة مضادة (السجل: قطبية الحجة لا اتجاه القرار) — محفوظة بنصّها"},
        {"agent_id": "11", "direction": "neutral", "confidence": None, "artifact": "quoted_in_decision",
         "stake": "VETOED — لا مركز؛ الحجم 0؛ measured=53.0 مقابل limit=65 (المادة 5.3)"},
        {"agent_id": "12", "direction": None, "confidence": None, "artifact": "absent",
         "stake": "لم يُسلَّم؛ ولا خطة تنفيذ مُقدَّمة (اختياري لعدم وجود مركز)"},
        {"agent_id": "13", "direction": "neutral", "confidence": 78.0, "artifact": "file",
         "stake": "FAIL (36/54 = 0.667) + نقض CVETO-2026-0921-13-01؛ ثقته 78"},
        {"agent_id": "14", "direction": "neutral", "confidence": 42.6, "artifact": "file",
         "stake": "ABSTAIN (abstention_kind = risk_veto) — الحجم 0، بلا entry/stop/target"},
    ]

    payload = {
        "cycle_id": CYCLE_ID,
        "record_type": "decision",
        "immutable": True,
        "recorded_by": "15",
        "asset": "AVAX",
        "data_as_of": DATA_AS_OF,
        "recorded_at_approx": RECORDED_AT_APPROX,
        "opinions_expected": 14,
        "opinions_present_verifiable": 7,   # 01, 02, 08, 09, 10, 13, 14 — ملفات خام مُبصَّمة
        "opinions_quoted_only": 1,          # 11 — منقول داخل نصّ القرار
        "opinions_audit_only": 5,           # 03, 04, 05, 06, 07 — بلا ملف خام
        "opinions_absent": 1,               # 12
        "opinions_digest": opinions_digest,
        "opinions_artifact_status": OPINION_ARTIFACT_STATUS,
        "opinions_digest_source": (
            "7 آراء مُثبَّتة كملفات خام مُبصَّمة (01, 02, 08, 09, 10, 13, 14)؛ ورأي واحد (11) منقول داخل نصّ "
            "القرار بلا ملف حكم مُسلَّم؛ و5 آراء (03,04,05,06,07) لا ملف خام لها ويُقتصر فيها على ما عدّه تدقيق 13؛ "
            "والوكيل 12 غائب. 7+1+5+1 = 14. لا يُنسب لوكيل رقمٌ لم يُقرأ له أثر (المادتان 2.5 و3.3)"
        ),
        "six_field_reproduction": raw,
        "decision": decision,
        "risk_verdict": rv_in,
        "proposal": {
            "direction": "neutral",
            "score": 0.0,
            "confidence": 42.6,
            "agreement": 1.0,
            "directional_views": 1,
            "groupthink_threshold_met": False,
            "groupthink_substance_note": (
                "المادة 4.4 غير مُفعَّلة شكلاً (1 < 5 آراء اتجاهية)، لكن استقلالية الأدلة منعدمة: "
                "139 دليلاً بمستوى 3 مشتقة من مولّد واحد ⇒ صوت واحد لا أصوات (بروتوكول §5 بند 11)"
            ),
            "supporters": dec_in["supporting_agents"],
            "opposers": dec_in["opposing_agents"],
            "abstainers": ["01", "02", "05", "07", "08"],
            "base_confidence": 57.6,
            "penalties": [
                "−4 حجة مضادة لمحامي الشيطان",
                "−6 بوابة الجودة (المادة 4.1 غير مستوفاة لأي إشارة)",
                "−5 لقلة المؤيدين عن 3",
            ],
            "resulting_confidence": 42.6,
            "validation_discounts": {"02": 0.90, "04": 0.75, "06": 0.95, "07": 0.95, "08": 0.95},
            "validation_discounts_note": (
                "هذه خصومات المادة 4.1 (حكم 09: −10/−25/−5/−5/−5) وليست أوزاناً تاريخية بالمادة 7.4 — "
                "التمييز نفسه المُثبَّت في الإدخال السابق (JRN-50D66DF37D97)"
            ),
            "history_weights": archive.get("history_weights", {}),
            "validated": False,
            "note": "لا ترجيح في هذه الدورة: البروتوكول انتهى عند البوابة 3 (نقض نافذ، المادة 5.1)",
        },
        "compliance": decision["compliance"],
        "snapshot_meta": {
            "asset": "AVAX",
            "source": "synthetic-deterministic",
            "timestamp": DATA_AS_OF,
            "seed": 11,
            "scenario": "bull",
            "bars_provided": 366,
            "last_close": 51.6221,
            "snapshot_sha256": sha256_file("data/snapshot_full.json"),
            "warning": ("بيانات اصطناعية حتمية — ليست شبكة حقيقية ولا سوقاً حقيقياً (المادتان 3.1 و3.3). "
                        "طبقات الأدلة 1–2 غير مستحقة."),
            "version_instability": ("الوسم (seed=11, scenario=bull) أنتج mid=115.5413 وسلسلة 120 شمعة في دورة "
                                    "2026-09-20T23:22:37Z، وmid=51.6221 وسلسلة 366 شمعة في هذه الدورة ⇒ الوسم ليس "
                                    "معرّفاً نسخياً مستقراً؛ الحسم المقترح: content-hash للقطة (حكم 09 §6.1)"),
        },
        "evidence_at_decision_time": evidence,
        "dissent_record": {
            "supporters": len(dec_in["supporting_agents"]),
            "opponents": len(dec_in["opposing_agents"]),
            "abstainers": 5,
            "neutral_non_abstaining": 2,
            "directional": 1,
            "strongest_counter_argument": dec_in["strongest_dissent"],
            "source_agent": "10",
            "verbatim_preserved": True,
            "counting_caveat": (
                "حقل supporting_agents كما سُلِّم يضمّ الممتنعين الخمسة (01,02,05,07,08) بين المؤيدين، "
                "ولا يضمّ الرأي الاتجاهي الوحيد (04) في أي من القائمتين. سُجِّل كما ورد بلا تصحيح صامت "
                "(المادتان 6.1 و7.2)، ويُرفع للمنسّق لحسم دلالة العدّ"
            ),
            "second_dissent": (
                "dissent الوكيل 13 (وثيقة الالتزام): «معظم النقض يقع على حقول غائبة عن حزمة التسليم لا على "
                "غيابها في السجلات الأصلية… تدقيق مبني على الجوهر وحده كان سيُخرج PASS_WITH_FINDINGS لا FAIL» "
                "— وقد صدّقه أثر الأصل المتاح (six_field_reproduction) في 3/3 من الملفات المفحوصة"
            ),
        },
        "post_mortem": {
            "status": "PENDING",
            "due_horizon": dec_in["horizon"],
            "horizon_end": HORIZON_END,
            "evaluation_class": "SYNTHETIC_TRAINING",
            "excluded_from_weight_updates": True,
            "review_date": REVIEW_DATE,
            "hard_stale_bound": HORIZON_END,
            "review_mode": "ABSTAINED",
            "review_criteria": [
                "هل كان الامتناع صحيحاً؟ يُقاس بثلاثة أسئلة منفصلة عن الربح: (أ) هل بقيت أسباب الحجب الثمانية "
                "عشرة قائمة؟ (ب) لو رُفع النقض، ما المسار المضاد الواقعي من آخر إغلاق 51.6221$ على أفق 24 ساعة؟ "
                "(ج) هل أُغلقت ملاحظات 13 الجسيمة (F1/F2/F3/F4/F10/F16) ونُفِّذ علاج F6/F11؟",
                "لا يُقيَّم قرار 2026-09-21T00:09:44Z بأي معلومة لم تكن متاحة لحظته؛ ما يُعرف لاحقاً يُسجَّل "
                "ملاحظة لا حكماً (المادة 8.2)",
                "إن رُفع النقض قبل REVIEW_DATE وفق شروط الإبطال، تُقدَّم المراجعة إلى لحظة رفع النقض + دورة واحدة",
                "المراجعة لا تُؤجَّل بعد 2026-09-22T00:09:44Z: بعده تصير اللقطة STALE بخصم 30% (المادة 3.4) "
                "ويصير التقييم غير قابل للمعايرة",
            ],
            "agent_scores": [],
            "scores_excluded_reason": (
                "لا اتجاه مُجاز في هذه الدورة (1 رأي اتجاهي مُبطَل، 5 امتناعات، 2 حياد)؛ وتقييم عملية اصطناعية "
                "حتمية بـ«صواب/خطأ» يُغذّي الأوزان بنمط مرفوض (F-11، المادة 7.4)"
            ),
        },
        "outcome": {
            "status": "PENDING",
            "review_date": REVIEW_DATE,
            "hard_stale_bound": HORIZON_END,
            "realized_pnl_pct": 0.0,
            "max_adverse_excursion_pct": 0.0,
            "invalidation_triggered": False,
            "hindsight_notes": "لا شيء بعد — تُملأ عند REVIEW_DATE بمقارنة اللقطة بسعر السوق المرجعي المتاح",
        },
        "agent_scores": [],
        "calibration": {
            "samples_canonical_chain": canon["calibration"]["samples"],
            "samples_archive_chain": archive.get("calibration", {}).get("samples"),
            "brier_archive": archive.get("calibration", {}).get("brier_score"),
            "curve": [],
            "note": ("المعايرة غير قابلة للحساب: صفر عيّنة في السلسلة المعيارية (لا مراجعة بعدية مُنجزة بعد)، "
                     "وعيّنة اصطناعية واحدة في السلسلة المؤرشفة. Brier على عيّنة واحدة رقم بلا معنى؛ والمقاييس "
                     "تُقرأ معاً لا Hit Rate وحده (ملف 15 §3.3أ و§7)"),
        },
        "error_patterns": [
            {
                "pattern_id": "F-01",
                "agent": "خط الأنابيب (التسليم/الأرشفة)",
                "description": ("اختفاء ملفات آراء خام من الشجرة لخمسة وكلاء (03,04,05,06,07) ⇒ تدقيق لا يستطيع "
                                "التحقق من الأصول، ونقض يتقوّل على حزمة تسليم"),
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-21T00:48:52+00:00",
                "evidence_refs": ["reports/agent-13-compliance-report-2026-09-21.md §8 F16",
                                  "six_field_reproduction (3 ملفات فقط من 8 متاحة)"],
                "remedy": "أرشفة ملف لكل رأي بمعرّف دورة صريح + content-hash؛ ومنع أي نقض على «حزمة» بدل الأصول",
            },
            {
                "pattern_id": "F-03",
                "agent": "09 (حكم التحقق)",
                "description": ("تغطية فحص التسريب ناقصة: الفحص #4 فشل، والفحصان #8 و#9 لم يُجرَيا ⇒ لا يجوز عدّ "
                                "مسح التسريب مكتملاً (المادة 8.3)"),
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-21T00:40:00+00:00",
                "evidence_refs": ["reports/agent-09-validation-verdict-2026-09-21.md",
                                  "reports/agent-13-compliance-report-2026-09-21.md §4 F9"],
                "remedy": "تشغيل الفحوص التسعة كاملة قبل أي ترجيح، وإدراج النتيجة في الحكم",
            },
            {
                "pattern_id": "F-04",
                "agent": "01 / خط الأنابيب (المولّد)",
                "description": ("قدرة تنفيذ دائرية: العمق المنشور = 0.500% من ADV بالبناء "
                                "(depth = 2×0.0025×DV) ⇒ تحليل القدرة والكلفة لا يقيسان شيئاً مستقلاً"),
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-21T00:40:00+00:00",
                "evidence_refs": ["reports/agent-09-validation-verdict-2026-09-21.md §2 و§4",
                                  "tools/export_snapshot.py:56-65", "src/avax_desk/data/synthetic.py:64"],
                "remedy": "عمق من مصدر مستقل عن حجم الشمعة، أو إسقاط أي استنتاج قدرة/كلفة مبني عليه",
            },
            {
                "pattern_id": "F-06",
                "agent": "الدورة (01–08) + الترجيح",
                "description": ("تقارب ظاهري لا استقلال: 139 دليلاً بمستوى 3 تعود كلها إلى مولّد واحد "
                                "(SyntheticFeed, seed=11) ⇒ صوت واحد لا أصوات، وإنذار المادة 4.4 غير مُفعَّل شكلاً"),
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-21T00:40:00+00:00",
                "evidence_refs": ["reports/agent-13-compliance-report-2026-09-21.md §2",
                                  "reports/agent-09-validation-verdict-2026-09-21.md §6.3"],
                "remedy": "مقياس استقلالية فعلي قبل تفعيل/تعطيل إنذار 4.4؛ وإلا فالإجماع رقم لا معنى له",
            },
            {
                "pattern_id": "F-10",
                "agent": "01 / 11",
                "description": ("تجاهل الطرف المقابل: venues_count = 10 رقم مولَّد بلا هوية منصات ولا دفتر لكل منصة "
                                "ولا توزيع حفظ ⇒ لا تقييم طرف مقابل ولا حد مشاركة لكل منصة"),
                "occurrence_count": 2,
                "status": "OBSERVED",
                "first_seen": "2026-09-20T23:22:37+00:00",
                "evidence_refs": ["reports/agent-01-market-structure-2026-09-21.json",
                                  "قرار الدورة: block «لا تقييم للطرف المقابل»"],
                "remedy": "قائمة منصات مسمّاة + سجلات تدقيق + توزيع حفظ؛ وإلا فسقف المركز مخفَّض 50% إلزاماً",
            },
            {
                "pattern_id": "F-11",
                "agent": "15 (منهج القياس) + المنسّق",
                "description": ("تقييم اتجاهي «صواب/خطأ» على مخرجات عملية اصطناعية حتمية وتغذية قاعدة الأوزان "
                                "(7.4) بها، مع احتساب المحايدين والضبط «مخطئين» اتجاهياً"),
                "occurrence_count": 2,
                "status": "OBSERVED",
                "first_seen": "2026-09-20T21:02:17+00:00",
                "evidence_refs": ["JRN-50D66DF37D97", "JRN-C537BA9599F3 (السلسلة المؤرشفة)",
                                  "تقرير 13 ملاحظة F6"],
                "remedy": "وسم المراجعة SYNTHETIC_TRAINING وإخراجها من تغذية 7.4 — مُنفَّذ في هذا الإدخال وفي سابقه",
            },
            {
                "pattern_id": "F-12",
                "agent": "15/14",
                "description": "دورة تُدقَّق قبل تسجيلها في السجل (خرق 7.1) — تكرار للملاحظة نفسها في دورتين متتاليتين",
                "occurrence_count": 2,
                "status": "OBSERVED",
                "first_seen": "2026-09-20T23:55:00+00:00",
                "evidence_refs": ["CVETO-2026-0920-13-01 (F11)", "CVETO-2026-0921-13-01 (F10)",
                                  "journal/anchor.json قبل هذا الإدخال: records=1, updated_at 00:04:56Z"],
                "remedy": "فتح الدورة في السجل لحظة بدئها (cycle_open) لا بعد التدقيق؛ هذا الإدخال يُغلق الإصابة الثانية",
            },
            {
                "pattern_id": "F-13",
                "agent": "13 (منهج التدقيق)",
                "description": ("نقض مبني على حزمة تسليم ناقصة لا على الأصول: F1 (2.1 = 0/8) وF7 (9.1 = 0/5) "
                                "غير قابلين لإعادة الإنتاج على الملفات الخام المتاحة — 3/3 منها تحمل الحقول الستة "
                                "وabstain_reason كاملة"),
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-21T00:48:52+00:00",
                "evidence_refs": ["six_field_reproduction في هذا الإدخال",
                                  "reports/agent-01-market-structure-2026-09-21.json",
                                  "reports/agent-02-technical-analysis.json",
                                  "reports/agent-08-portfolio-theory.json",
                                  "dissent الوكيل 13 نفسه"],
                "remedy": "قاعدة: لا يُثبت نقص حقل إلا على الأصل المُبصَّم؛ وإذا تعذّر الأصل تُوسم الملاحظة "
                          "UNVERIFIABLE لا PROVEN",
            },
        ],
        "weight_updates": [],
        "weights_before": archive.get("history_weights", {}),
        "weights_after": archive.get("history_weights", {}),
        "effective_weights_01_14": {f"{i:02d}": 1.0 for i in range(1, 15)},
        "weight_decision": {
            "reduction_due": False,
            "reason": (
                "المادة 7.4 تشترط نمطاً واحداً بعينه مكرراً 3 مرات موثَّقاً بمعرّف في مكتبة الفشل. أقصى ما "
                "يتوفر: عيّنة تقييم واحدة لكل وكيل في السلسلة المؤرشفة (JRN-C537BA9599F3) وصفر عيّنات في "
                "السلسلة المعيارية ⇒ max_samples = 1 < 3. والأنماط F-01/F-03/F-04/F-06/F-10/F-11/F-12/F-13 "
                "مُسجَّلة OBSERVED لا PROVEN. لذلك: لا تخفيض ولا رفع — أوزان 01–14 تبقى 1.0"
            ),
            "proven_patterns": [],
            "observed_only": ["F-01", "F-03", "F-04", "F-06", "F-10", "F-11", "F-12", "F-13"],
            "reduction_refused_explicitly": True,
            "refusal_article": "المادة 7.4 (التخفيض بلا نمط مُثبت مكرر 3 مرات مخالفة)",
            "escalation_watch": (
                "F-11 وF-12 بلغا التكرار الثاني على مستوى الديسك (وليس على وكيل بعينه). تكرار ثالث يفرض "
                "تخفيضاً بموجب 7.4 — ويُنبَّه الأطراف الآن بالمنهج المطلوب تصحيحه، لأن 7.4 تشترط إبلاغ الوكيل"
            ),
            "no_reward_reason": "شرط الرفع (+0.10) هو 10 تنبؤات متتالية بمعايرة سليمة (ECE ≤ 0.10) — غير متحقق: صفر تنبؤات مُقيَّمة بعد",
        },
        "distinct_from_4_1": {
            "note": ("تمييز ضروري: خصومات التحقق validation_discounts (02→0.90، 04→0.75، 06→0.95، 07→0.95، "
                     "08→0.95) هي عقوبة المادة 4.1 (إشارة لم تجتز قانون التحقق) وليست تخفيض وزن بالمادة 7.4، "
                     "ولا هي وزن تاريخي history_weights (الكل 1.0)"),
            "source": "reports/agent-09-validation-verdict-2026-09-21.md §1",
        },
        "failure_library_additions": [
            {"pattern_id": "F-01", "description": "آراء غير مؤرشفة كملفات ⇒ تدقيق/تسجيل بلا أصل مُبصَّم",
             "context": "5 من 8 آراء الدورة بلا ملف خام (03,04,05,06,07)؛ وملفات 06 في الشجرة تعود لدورات سابقة",
             "corrective_sop": "أرشفة كل رأي في reports/ بمعرّف دورة صريح + sha256 قبل الترجيح"},
            {"pattern_id": "F-13", "description": "نقض/ملاحظة تُبنى على حزمة تسليم بدل الأصول فيُبالَغ في العيب",
             "context": "F1 وF7 (حقول ناقصة في 8/8، و0/5 سبب امتناع) غير قابلين لإعادة الإنتاج على 3 ملفات خام متاحة",
             "corrective_sop": "لا يُثبت نقص حقل إلا على الأصل المُبصَّم؛ وما تعذّر أصله يُوسم UNVERIFIABLE"},
            {"pattern_id": "F-04", "description": "دائرية بنيوية في العمق/القدرة تُنتج «تحليلاً» بلا محتوى مستقل",
             "context": "depth_base = dv×0.0025 ⇒ العمق المنشور 0.500% من ADV بالبناء",
             "corrective_sop": "فصل مصدر العمق عن مصدر الحجم قبل أي حساب قدرة أو كلفة"},
        ],
        "market_lessons": [
            {"lesson": ("عند مصدر synthetic-deterministic لا يمكن أن يوجد دليل مستوى 1 أو 2 — وكل ترجيح يستند إلى "
                        "3/4/5/7. الأثر هنا أعمق من الدورة السابقة: 139 دليلاً «مستوى 3» مشتقة من مولّد واحد، أي أن "
                        "مؤشر جودة المصادر SQI = 0.842 حدّ أعلى لا تقدير محايد"),
             "validity_conditions": "سارية ما دام _meta.source = synthetic-deterministic والحاوية تُعلن ذلك",
             "confidence": 86},
            {"lesson": ("أقوى ثغرة قياس في هذه الدورة ليست في الاتجاه بل في الهوية النسخية: الوسم "
                        "(seed=11, scenario=bull) أنتج سلسلتين مختلفتين (115.5413/120 شمعة مقابل 51.6221/366 شمعة) "
                        "⇒ أي استشهاد من الذاكرة بلا content-hash للقطة قد يخلط دورتين"),
             "validity_conditions": "صالحة لكل التقارير المحفوظة بأسماء متقاربة قبل إدخال content-hash",
             "confidence": 88},
            {"lesson": ("الامتناع هنا صمد على مسارين مستقلين: نقض مخاطري (5.1) وحجب التزام (13) — لكن أحدهما "
                        "قائم على قياس (53.0 < 65) والآخر على هامش موضع نزاع (36/54 مع F1/F7 غير قابلين للتحقق) "
                        "⇒ لا تُقرأ قوة المسارين كأنها قوة واحدة متكافئة"),
             "validity_conditions": "خاصة بدورة 2026-09-21T00:09:44Z وبالأصول المتاحة في الشجرة",
             "confidence": 74},
            {"lesson": ("درس منهجي مُثبت على أثر: «الحقول الغائبة» في هذه الدورة كانت غالباً غائبة عن حزمة التسليم "
                        "لا عن السجلات — فالتوثيق الناقص والتسليم الناقص يعطيان حكماً واحداً (FAIL) وهو خطأ تصنيف "
                        "يُكلّف الديسك ثقة زائفة في صرامته"),
             "validity_conditions": "مُتحقَّق على 01 و02 و08 فقط؛ يبقى ظنّاً مسنوداً لا برهاناً على 03–07",
             "confidence": 70},
        ],
        "corrections": [
            {"corrects_record_id": PREDECESSOR_RECORD,
             "target_chain": "journal/desk_journal.jsonl",
             "reason": ("إدخال لاحق يشير للإدخال السابق ولا يعدّله (المادة 7.2): هذا سجل الدورة التالية "
                        f"({CYCLE_ID}، بيانات {DATA_AS_OF})، ويُغلق الملاحظة F10/F12 التي وسمت الدورة الحالية "
                        "غير مسجّلة. ولا يُعدَّل أي حقل في الإدخال السابق"),
             "does_not_modify": True},
            {"corrects_record_id": "CVETO-2026-0921-13-01 (وثيقة خارج السجل)",
             "target_chain": "reports/agent-13-compliance-report-2026-09-21.md",
             "reason": ("لا يُعدَّل التقرير — يُسجَّل تعارض مع الأصل المتاح: F1 وF7 غير قابلين لإعادة الإنتاج على "
                        "الملفات الخام لـ01/02/08؛ وأثر ذلك على هامش FAIL يُرفع للمنسّق (نمط F-13)"),
             "does_not_modify": True},
        ],
        "journal_lineage": {
            "canonical_path": "journal/desk_journal.jsonl",
            "records_in_canonical_before": canon["records"],
            "predecessor_record_id": PREDECESSOR_RECORD,
            "predecessor_cycle_id": PREDECESSOR_CYCLE,
            "predecessor_head_hash": canon["head_hash"],
            "predecessor_chain_valid": canon["valid"],
            "prior_chain": {
                "path": str(ARCHIVE.relative_to(ROOT)),
                "sha256": archive.get("sha256"),
                "records": archive.get("records"),
                "head_hash": archive.get("head_hash"),
                "chain_valid": archive.get("chain_valid"),
                "carried_forward": False,
                "reason": "سلسلة تعليمية موسومة demo تُقرأ ولا تُنقل ولا تُعدَّل",
            },
            "pending_post_mortems": [
                {"record_id": PREDECESSOR_RECORD, "cycle_id": PREDECESSOR_CYCLE,
                 "review_date": "2026-09-21T23:00:00+00:00", "status": "PENDING"},
                {"record_id": "(هذا الإدخال — معرّفه يُنتَج لحظة الإضافة)", "cycle_id": CYCLE_ID,
                 "review_date": REVIEW_DATE, "status": "PENDING"},
            ],
        },
        "constitution_fingerprint": {},
        "law_audit": {"total": 0, "errors": 0, "warnings": 0, "by_article": {}, "by_code": {}},
        "constitution_version": "1.0",
        "open_items_for_coordinator": [
            "F-11 وF-12 بلغا التكرار الثاني: تكرار ثالث يفرض تخفيض وزن بموجب 7.4 — أبلِغ الأطراف بالمنهج المطلوب الآن",
            "نقص حقل يُتهم به وكيل يجب أن يُثبت على الأصل المُبصَّم: F1/F7 يسقطان لـ01/02/08 ويبقيان UNVERIFIABLE لـ03–07",
            "حسم دلالة حقل supporting_agents: يضمّ 5 ممتنعين ولا يضمّ الرأي الاتجاهي الوحيد (04)",
            "أرشفة ملف خام لكل رأي بمعرّف دورة + content-hash للقطة (يمنع خلط النسخ ويغلق F-01 وF-15)",
            "المخرجان 11 و12: RiskVerdict لم يُسلَّم كملف، ولا خطة تنفيذ — يُثبَّت الأول لأن النقض قرار حاكم",
            "المادة 8.7/9.3: تعارض «أحمر مقترح» مع «أحمر محفظة» يحتاج وثيقة تصحيحية (10.1) أو تنفيذ إيقاف",
            "المادتان 7.2/F13: تشغيل AVAX_DESK_JOURNAL_SECRET ونقل المرساة خارج نطاق الكتابة (حماية الحماية)",
            "المراجعة البعدية للدورة السابقة مستحقة عند 2026-09-21T23:00Z، وهذه عند 2026-09-22T00:09:44Z — كلتاهما غير مُنجزة بعد",
        ],
        "self_assessment": {
            "confidence": 67,
            "meaning": "ثقة تصف اكتمال التسجيل وصحة التقييم لا صحة القرار المُسجَّل (ملف 15 §7.1)",
            "why_not_higher": ("شريحة 81+ تشترط دورة كاملة موثقة + سلسلة سليمة + مقاييس معايرة محسوبة: السلسلة "
                               "سليمة (تُتحقَّق بعد الإضافة) لكن المعايرة غير قابلة للحساب (صفر عيّنة مُقيَّمة)، "
                               "وعقد المدخلات ناقص (5 آراء بلا ملف خام + الوكيل 12 غائب + RiskVerdict بلا ملف) "
                               "⇒ الدورة تُوسم INCOMPLETE ولا تستحق 81+"),
            "why_not_lower": ("السلسلة مختومة وسليمة، والرأي المخالف محفوظ بنصّه، وكل ادعاء هنا مسنود ببصمة ملف، "
                              "والأوزان لم تُخفَّض بلا نمط مُثبت، والمراجعة البعدية مُجدولة بطابع زمني"),
            "cycle_completeness": "INCOMPLETE (عقد المدخلات §4: ناقص) — مُعلن لا مُخفى",
            "dual_error_note": ("القاعدة المزدوجة في ملف 15 §10.3: خطر التمرير (قبول إدخال معطوب) وخطر التعطيل "
                                "(رفض إدخال سليم). هذا الإدخال يقبل التسجيل مع وسم INCOMPLETE صراحةً، ويرفض "
                                "إضافات لا يسندها أصل (لا رقم لوكيل بلا ملف، ولا حكم RiskVerdict لم يُسلَّم)"),
        },
        "process_disclosure": (
            "إفصاح إجرائي (المادتان 8.4 و9.2): عقد مدخلات الوكيل 15 يوجب الامتناع ووسم الدورة INCOMPLETE عند غياب "
            "مخرجات أي وكيل. الحزمة ناقصة فعلاً (5 آراء بلا ملف خام، والوكيل 12 غائب، والوكيل 11 بلا ملف حكم). "
            "اختار الوكيل 15 تسجيل الإدخال مع وسم INCOMPLETE بدل الامتناع عن التسجيل، لسببين معلنين: (1) المادة 7.1 "
            "توجب كتابة كل دورة، والامتناع عن التسجيل يكرّر خرق 7.1 الذي نقده الوكيل 13 في الملاحظتين F11/F10؛ "
            "(2) نقض الوكيل 13 نفسه (CVETO-2026-0921-13-01) يطالب بإدخال سجل جديد للدورة. ويُسجَّل أن الامتناع عن "
            "التسجيل كان الخيار الحرفي لعقد المدخلات، وأن التعارض مُعلن لا مُسدود"
        ),
    }
    _assert_partitions(payload)
    return payload


def record() -> dict:
    if not INPUT.exists():
        raise SystemExit("⛔ لقطة المدخلات غير موجودة — لا تسجيل بلا لقطة مثبَّتة (المادتان 8.2 و2.5)")
    canon_before = canonical_state()
    if any(r[1] == PREDECESSOR_RECORD for r in canon_before["sequences"]) is False:
        raise SystemExit("⛔ الإدخال السابق غير موجود في السلسلة — راجع journal/desk_journal.jsonl")
    if canon_before["records"] != 1:
        raise SystemExit(f"⛔ السلسلة المعيارية بعدد متوقع 1 إدخالاً، والموجود {canon_before['records']} — لا تُضاف دورة على سلسلة غير متوقعة")

    store = JournalStore(CANONICAL)
    payload = build_payload()

    # استبدال عنصر THIS بمعرّف الإدخال الفعلي بعد الإضافة (يُكتب في إدخال تصحيح مُشير عند اللزوم)
    payload["constitution_fingerprint"] = store.constitution_fingerprint("CONSTITUTION.md")
    payload["constitution_fingerprint"]["note_previous"] = (
        "بصمة الدستور مُسجَّلة في الإدخال السابق JRN-50D66DF37D97 وفي السلسلة المؤرشفة؛ "
        "changed=false يعني صفر تعديل صامت (المادة 10.1)"
    )

    rec = store.append(payload, kind="desk_cycle")
    chain = store.verify_chain()
    md = store.write_markdown_summary()
    write_cycle_markdown(rec, chain, payload)

    return {
        "cycle_id": CYCLE_ID,
        "record_id": rec.record_id,
        "sequence": rec.sequence,
        "previous_hash": rec.previous_hash,
        "record_hash": rec.record_hash,
        "timestamp": rec.timestamp,
        "chain_valid": chain["valid"],
        "chain_records": chain["records"],
        "head_hash": chain["head_hash"],
        "anchor_check": chain["anchor_check"],
        "signed": chain["signed"],
        "journal_path": str(CANONICAL.relative_to(ROOT)),
        "markdown_summary": str(md.relative_to(ROOT)),
        "cycle_markdown": str(CYCLE_MD.relative_to(ROOT)),
        "weights_after": payload["weights_after"],
        "weight_reduction_due": payload["weight_decision"]["reduction_due"],
        "post_mortem_review_date": REVIEW_DATE,
    }


def write_cycle_markdown(record, chain, payload: dict) -> Path:
    dec = payload["decision"]
    dr = payload["dissent_record"]
    raw = payload["six_field_reproduction"]
    lines = [
        "# 【الوكيل 15 — وكيل الذاكرة والسجل】",
        f"## الدورة `{CYCLE_ID}` — إدخال `{record.record_id}` — النوع: `decision` (قرار) — غير قابل للتعديل",
        "",
        "> ملف **مشتق** للقراءة من السجل الأصل `journal/desk_journal.jsonl`. المصدر الوحيد للحقيقة هو JSONL؛ "
        "هذا الملف لا يُعدّل السجل ولا يُحتجّ به عليه. ولا يُعدّل هذا الملف أي إدخال سابق (المادة 7.2).",
        "",
        "## 1. البصمة والسلسلة (المادة 7.2)",
        "",
        "| الحقل | القيمة |",
        "|---|---|",
        f"| معرّف الإدخال | `{record.record_id}` |",
        f"| الرقم التسلسلي | {record.sequence} |",
        f"| بصمة الإدخال السابق | `{record.previous_hash}` |",
        f"| بصمة الإدخال | `{record.record_hash}` |",
        f"| طابع التسجيل | `{record.timestamp}` — ووقت البيانات `{DATA_AS_OF}` |",
        f"| سلامة السلسلة | {'✅ سليمة' if chain['valid'] else '⛔ مكسورة'} عند {chain['records']} إدخالاً، "
        f"أسطر تالفة: {chain['corrupt_lines']} |",
        f"| المرساة الخارجية | {chain['anchor_check']} |",
        f"| التوقيع | {'HMAC بمفتاح خارجي' if chain['signed'] else 'sha256 بلا مفتاح (سلسلة غير موقّعة)'} |",
        "",
        f"**حدود الحماية:** {chain['limits']}",
        "",
        "## 2. القرار المُسجَّل حرفياً (المادتان 6.1 و7.2)",
        "",
        f"- **القرار:** `{dec['action']}` — نوع الامتناع `{dec['abstention_kind']}` — الحجم: **0** — لا entry/stop/target",
        f"- **الثقة المُعلنة:** {dec['confidence']} (شريحة 41–64 «متوسط/للمراقبة فقط» في سلّم §7.1 — غير مؤهلة للدخول)",
        f"- **المعرّف:** `{dec['decision_id']}` ({dec['decision_id_note']})",
        f"- **الطابع الزمني للقرار:** لم يُسلَّم — {dec['timestamp_note']}",
        f"- **الأفق كما قُرّر:** {dec['horizon']}",
        f"- **أسباب الحجب:** {len(dec['blocks'])} سبباً مثبتاً في حقل `blocks` (نقض مخاطر + حجب التزام + عقد إدخال)",
        f"- **حكم المخاطر المنقول:** {payload['risk_verdict']['verdict']} — "
        f"measured={payload['risk_verdict']['measured_vs_limit']['average_supporter_confidence_measured']} "
        f"مقابل limit={payload['risk_verdict']['measured_vs_limit']['entry_confidence_limit']} (المادة 5.3)",
        f"- **حكم الالتزام:** {payload['compliance']['verdict']} — {payload['compliance']['rate_expression']} "
        f"= {payload['compliance']['rate']} — النقض `{payload['compliance']['veto_id']}` — "
        f"{payload['compliance']['serious_findings']} ملاحظات جسيمة",
        "",
        f"**نزاع مُسجَّل لا مُسدود:** {payload['compliance']['contested_basis']}",
        "",
        "### الرأي المخالف بنصّه (المادتان 6.1 و6.3) — لا يُحذف ولا يُخفَّف",
        "",
        dr["strongest_counter_argument"],
        "",
        f"**المخالف الثاني:** {dr['second_dissent']}",
        "",
        "## 3. لقطة الأدلة لحظة القرار (المادة 8.2)",
        "",
        f"{len(payload['evidence_at_decision_time'])} عنصراً مثبَّتاً ببصمة sha256:",
        "",
        "| الملف | البصمة (أول 16) |",
        "|---|---|",
    ]
    for ev in payload["evidence_at_decision_time"]:
        digest = ev["claim"].split()[-1]
        lines.append(f"| `{ev['source']}` | `{digest[:16]}` |")
    lines += [
        "",
        "## 4. المخرجات والآراء — ما هو مُثبَّت وما هو غائب",
        "",
        f"- المؤيدون الأصليون للامتناع: **{dr['supporters']}** | المعارضون: **{dr['opponents']}** | "
        f"الممتنعون: **{dr['abstainers']}** | محايدون غير ممتنعين: **{dr['neutral_non_abstaining']}** | "
        f"اتجاهي: **{dr['directional']}**",
        f"- تنبيه تعداد: {dr['counting_caveat']}",
        f"- الآراء المُثبَّتة كملفات: **{payload['opinions_present_verifiable']}** | منقولة داخل نصّ القرار: "
        f"**{payload['opinions_quoted_only']}** | مُقتصرة على تدقيق 13: **{payload['opinions_audit_only']}** | "
        f"غائبة: **{payload['opinions_absent']}** (من أصل {payload['opinions_expected']})",
        f"- {payload['opinions_digest_source']}",
        "",
        "### 4.1 إعادة إنتاج فحص الحقول الستة على الأصل المتاح (MAD 2.1/9.1) — قياس لا ادّعاء",
        "",
        "| الوكيل | الملف | الحقول الستة | abstain_reason | أدلة في الملف | عدد تدقيق 13 |",
        "|---|---|---|---|---|---|",
    ]
    mism = {m["agent"]: m for m in raw["evidence_count_mismatch"]}
    for aid, info in raw["checked"].items():
        a13 = mism.get(aid, {}).get("audit_13_count", "—")
        lines.append(
            f"| {aid} | `{info['file']}` | {info['six_fields_count']}/6 | "
            f"{'✅' if info['abstain_reason_present'] else '✗'} | {info['evidence_items_in_file']} | {a13} |"
        )
    lines += [
        "",
        f"- **آراء بلا ملف خام (لا يمكن فحصها): {', '.join(raw['unavailable'])}**",
        "- **نتيجة القياس:** ملاحظتا 13 الشكلية F1 (المادة 2.1 = 0/8) وF7 (المادة 9.1 = 0/5) **لا تُعادان** على "
        "الأصل المتاح: 3/3 ملفات مفحوصة تحمل الحقول الستة كاملة و`abstain_reason`. وتفاوت العدّ مؤكَّد عند 02 "
        f"({mism['02']['audit_13_count']} في تدقيق 13 مقابل {mism['02']['raw_file_count']} في الملف الخام).",
        "- **الأثر:** لا يمسّ نقض المخاطر (المادة 5.1) القائم على قياس مستقل (53.0 < 65)، لكنه يمسّ **هامش** حجب "
        "الالتزام (36/54) فيصير موضع نزاع مُعلن لا صفراً. لا يُعدَّل تقرير 13 — يُسجَّل التعارض (المادة 7.2).",
        "",
        "## 5. المراجعة البعدية — الأفق المستحق (المادة 7.3)",
        "",
        "| الحقل | القيمة |",
        "|---|---|",
        f"| **تاريخ المراجعة المستحق** | **`{REVIEW_DATE}`** |",
        f"| نهاية الأفق المُعلن في القرار | `{HORIZON_END}` (اللقطة + 24 ساعة — المادة 3.4) |",
        "| وضع التقييم | `ABSTAINED` — يُقيَّم بمعيار «هل كان الامتناع صحيحاً؟» لا بالربح |",
        f"| وسم التقييم | `{payload['post_mortem']['evaluation_class']}` — مُخرَج من تغذية الأوزان (7.4) |",
        "| المراجعة السابقة (الدورة 2026-09-20T23:22:37Z) | مستحقة عند `2026-09-21T23:00:00Z` — **PENDING** |",
        "",
        "**حدّ صارم:** لا تُؤجَّل المراجعة بعد `2026-09-22T00:09:44Z`؛ بعده تُوسم اللقطة `STALE` بخصم 30% "
        "(المادة 3.4) فيصير التقييم غير قابل للمعايرة. **معايير المراجعة الثلاثة:**",
        "",
    ]
    for i, crit in enumerate(payload["post_mortem"]["review_criteria"], 1):
        lines.append(f"{i}. {crit}")
    lines += [
        "",
        "## 6. الأوزان (المادة 7.4)",
        "",
        "| الوكيل | الوزن التاريخي | تخفيض مستحق؟ |",
        "|---|---|---|",
    ]
    weights = payload["weights_after"] or {}
    for aid in sorted(payload["effective_weights_01_14"]):
        w = weights.get(aid, 1.0)
        lines.append(f"| {aid} | {w} | لا — عيّنة واحدة < 3 |")
    lines += [
        "",
        f"**الحكم:** {payload['weight_decision']['reason']}",
        "",
        f"**مراقبة تصعيد:** {payload['weight_decision']['escalation_watch']}",
        "",
        f"**لا رفع:** {payload['weight_decision']['no_reward_reason']}",
        "",
        f"**بدون لبس:** {payload['distinct_from_4_1']['note']}",
        "",
        "## 7. الأنماط ومكتبة الفشل",
        "",
        "| المعرّف | الوصف | التكرار | الحالة |",
        "|---|---|---|---|",
    ]
    for p in payload["error_patterns"]:
        lines.append(f"| {p['pattern_id']} | {p['description']} | {p['occurrence_count']} | {p['status']} |")
    lines += [
        "",
        "**الحالة:** صفر نمط `PROVEN` (لا نمط مكرر 3 مرات على الوكيل نفسه) ⇒ لا تخفيض أوزان. "
        "الأنماط F-11 وF-12 بلغا التكرار الثاني على مستوى الديسك — إنذار تصعيد لا عقوبة (المادة 7.4).",
        "",
        "## 8. دروس السوق",
        "",
    ]
    for les in payload["market_lessons"]:
        lines.append(f"- {les['lesson']} (شرط الصلاحية: {les['validity_conditions']}؛ ثقة {les['confidence']})")
    lines += [
        "",
        "## 9. التصحيحات (المادة 7.2 — إدخال جديد يشير للقديم، بلا تعديل)",
        "",
    ]
    for c in payload["corrections"]:
        lines.append(f"- `{c['corrects_record_id']}` في `{c['target_chain']}`: {c['reason']} "
                     f"(does_not_modify = {c['does_not_modify']})")
    lines += [
        "",
        "## 10. السلسلة التاريخية والبنود المفتوحة",
        "",
        f"- السلسلة المعيارية قبل الإضافة: {payload['journal_lineage']['records_in_canonical_before']} إدخال "
        f"(`{payload['journal_lineage']['predecessor_record_id']}` — رأس "
        f"`{payload['journal_lineage']['predecessor_head_hash'][:16]}…`)",
        f"- السلسلة المؤرشفة: {payload['journal_lineage']['prior_chain']['records']} إدخالات، سليمة: "
        f"{payload['journal_lineage']['prior_chain']['chain_valid']}، sha256 "
        f"`{(payload['journal_lineage']['prior_chain']['sha256'] or '')[:16]}…` — لا تُنقل ولا تُعدَّل",
        "",
        "**بنود مفتوحة للمنسّق:**",
        "",
    ]
    for item in payload["open_items_for_coordinator"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "## 11. خاتمة الوكيل 15",
        "",
        f"- **الثقة: {payload['self_assessment']['confidence']}/100** — {payload['self_assessment']['meaning']}",
        f"- سبب عدم بلوغ 81+: {payload['self_assessment']['why_not_higher']}",
        f"- سبب عدم الهبوط دون 65: {payload['self_assessment']['why_not_lower']}",
        f"- **اكتمال الدورة:** {payload['self_assessment']['cycle_completeness']}",
        f"- **إفصاح إجرائي:** {payload['process_disclosure']}",
        "- **شرط الإبطال:** يُبطل هذا التسجيل إذا فشل التحقق من السلسلة (تعديل خارجي)، أو إذا لم تُنفَّذ المراجعة "
        f"البعدية عند `{REVIEW_DATE}`، أو إذا ثبت أن لقطة الأدلة المثبَّتة لا تطابق ما اعتُمد وقت القرار، أو إذا "
        "ثبت أن نصّ القرار الذي سُلِّم إلى 15 يخالف ما صدر فعلاً عن المنسّق.",
        "- **المخالف:** السجل يحفظ ما **قيل** لا ما **صحّ**؛ وهذا الإدخال يوثّق امتناعاً لا نتيجة، وقيمته تُختبر "
        f"عند {REVIEW_DATE} لا قبله. ويسجّل أن حجب الالتزام مبني جزئياً على حزمة تسليم لا على الأصول.",
        "- **القرار: تسجيل** (لا امتناع) — الوكيل 15 لا يُصدر قراراً ولا فرضية سوقية (المادتان 1.1 و1.2).",
        "",
    ]
    CYCLE_MD.write_text("\n".join(lines), encoding="utf-8")
    return CYCLE_MD


def verify() -> dict:
    store = JournalStore(CANONICAL)
    chain = store.verify_chain()
    records = store.records()
    return {
        "path": str(CANONICAL.relative_to(ROOT)),
        "records": chain["records"],
        "valid": chain["valid"],
        "broken": chain["broken"],
        "corrupt_lines": chain["corrupt_lines"],
        "head_hash": chain["head_hash"],
        "anchor_check": chain["anchor_check"],
        "signed": chain["signed"],
        "sequences": [(r.sequence, r.record_id, r.timestamp, r.payload.get("cycle_id")) for r in records],
        "actions": [d.get("action") for d in store.decisions()],
        "summary": store.summary(),
        "archive_untouched_sha256": archive_report().get("sha256"),
        "weights": store.agent_weights(),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="تسجيل دورة الوكيل 15 — CYC-2026-0921-0009Z")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true", help="بناء الحمولة بلا كتابة")
    g.add_argument("--record", action="store_true", help="تسجيل الدورة (كتابة)")
    g.add_argument("--verify", action="store_true", help="التحقق من سلامة السلسلة")
    args = ap.parse_args()

    if args.probe:
        payload = build_payload()
        out = {
            "cycle_id": payload["cycle_id"],
            "assigned_decision_id": payload["decision"]["decision_id"],
            "opinions_present_verifiable": payload["opinions_present_verifiable"],
            "six_field_reproduction": payload["six_field_reproduction"],
            "weight_decision": payload["weight_decision"],
            "post_mortem": {k: payload["post_mortem"][k] for k in ("review_date", "horizon_end", "review_mode", "evaluation_class")},
            "canonical_before": canonical_state(),
            "archive": {k: archive_report()[k] for k in ("records", "chain_valid", "sha256", "history_weights")},
            "payload_keys": sorted(payload.keys()),
        }
    elif args.record:
        out = record()
    else:
        out = verify()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
