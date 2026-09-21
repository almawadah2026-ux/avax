"""
إدخال تصحيح — يشير إلى JRN-EE42E4AB5CA0 ولا يعدّله (المادتان 7.2 و8.9).

الوكيل 15 — وكيل الذاكرة والسجل.

السبب المُعلن (بلا تجميل — المادة 8.4): خطأ عدّ ذاتي في الإدخال JRN-EE42E4AB5CA0.
حقل `opinions_present_verifiable` كُتب 9 والصحيح 7، فصار مجموع أقسام الآراء 16 بدل 14.
الخطأ كُشف بفحص لاحق على الإدخال نفسه، ولم يُعدَّل الإدخال؛ التصحيح بإدخال جديد مُشير.

الاستعمال:
    python tools/record_cycle_15_20260921_correction.py --probe
    python tools/record_cycle_15_20260921_correction.py --record
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
CORRECTED_RECORD = "JRN-EE42E4AB5CA0"
PREDECESSOR_RECORD = "JRN-50D66DF37D97"
CYCLE_ID = "CYC-2026-0921-0009Z"
DATA_AS_OF = "2026-09-21T00:09:44+00:00"
REVIEW_DATE = "2026-09-22T00:09:44+00:00"
CORRECTION_MD = ROOT / "journal" / "CORRECTION-2026-0921-0009Z.md"

CORRECTED_FIELDS = [
    {
        "field": "opinions_present_verifiable",
        "old_value": 9,
        "corrected_value": 7,
        "proof": ("الملفات الخام المُبصَّمة لهذه الدورة سبعة فقط: 01 (agent-01-market-structure-2026-09-21.json)، "
                  "02 (agent-02-technical-analysis.json)، 08 (agent-08-portfolio-theory.json)، "
                  "09 (agent-09-validation-verdict-2026-09-21.md)، 10 (redteam-10-challenge-2026-09-21.md)، "
                  "13 (agent-13-compliance-report-2026-09-21.md)، 14 (journal/records/CYC-2026-0921-0009Z.input.json). "
                  "والرأي 11 ليس ملفاً بل منقولاً داخل نصّ القرار (opinions_quoted_only = 1)"),
    },
    {
        "field": "opinions_digest_source",
        "old_value": "«9 آراء مُثبَّتة كملفات في الشجرة (01, 02, 08, 09, 10, 13, 14 + 11 منقول داخل نصّ القرار)…»",
        "corrected_value": ("«7 آراء مُثبَّتة كملفات خام مُبصَّمة (01, 02, 08, 09, 10, 13, 14)؛ ورأي واحد (11) "
                            "منقول داخل نصّ القرار بلا ملف حكم مُسلَّم؛ و5 آراء (03,04,05,06,07) لا ملف خام لها؛ "
                            "والوكيل 12 غائب. 7+1+5+1 = 14»"),
        "proof": "النص الأصلي كان يناقض نفسه: يعلن 9 ثم يعدّ 7 ملفات + 1 منقول",
    },
]


def sha256_file(rel: str) -> str | None:
    p = ROOT / rel
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_payload() -> dict:
    store = JournalStore(CANONICAL)
    recs = store.records()
    target = next((r for r in recs if r.record_id == CORRECTED_RECORD), None)
    if target is None:
        raise SystemExit(f"⛔ الإدخال المُصحَّح {CORRECTED_RECORD} غير موجود — لا تصحيح بلا مُصحَّح")
    old = target.payload

    # إثبات الأقسام على الإدخال المُصحَّح نفسه (قياس لا ادّعاء)
    old_partition_total = (old["opinions_present_verifiable"] + old["opinions_quoted_only"]
                           + old["opinions_audit_only"] + old["opinions_absent"])
    file_artifacts = sorted(o["agent_id"] for o in old["opinions_digest"] if o.get("artifact") == "file")

    payload = {
        "cycle_id": CYCLE_ID,
        "record_type": "correction",
        "immutable": True,
        "recorded_by": "15",
        "asset": "AVAX",
        "data_as_of": DATA_AS_OF,
        "corrects_record_id": CORRECTED_RECORD,
        "correction_kind": "self_reported_counting_error",
        "does_not_modify": True,
        "article_refs": ["7.2", "8.4", "8.9"],
        "correction_reason": (
            "خطأ عدّ ذاتي في حقل واحد وفي نصّ مرافق له داخل الإدخال JRN-EE42E4AB5CA0: "
            "`opinions_present_verifiable` كُتب 9 والصحيح 7. الأثر: مجموع أقسام الآراء صار 16 بدل 14، "
            "وهو ما يجعل سطر «الآراء المُثبَّتة كملفات» مضخَّماً ويُوهم اكتمالاً أعلى من الواقع. "
            "كُشف الخطأ بفحص لاحق، والإدخال لم يُعدَّل — التصحيح بهذا الإدخال الجديد (المادة 7.2)"
        ),
        "corrected_fields": CORRECTED_FIELDS,
        "error_forensics": {
            "old_partition_total": old_partition_total,
            "expected_partition_total": 14,
            "file_artifacts_on_record": file_artifacts,
            "file_artifacts_count": len(file_artifacts),
            "root_cause": (
                "كتابة حقل عدّي بلا تحقق آلي من تطابق الأقسام؛ إذ عُدَّ الرأي 11 (منقول لا مُبصَّم) مرتين "
                "ضمن الأقسام. النمط سببي (إجراء لا بيانات): غياب حارس عدّ قبل الكتابة"
            ),
            "detection": "فحص لاحق على الحمولة المكتوبة مقابل `opinions_digest` في السجل نفسه",
            "blast_radius": (
                "محدود: الحقل تشخيصي لتغطية الحزمة؛ ولا يمسّ نصّ القرار المُسجَّل حرفياً، ولا الرأي المخالف، "
                "ولا الأوزان، ولا أفق المراجعة. الأرقام الأخرى في الإدخال (139 دليلاً، 36/54، 53.0/65، 42.6) "
                "غير متأثرة — وقد أُعيد التحقق من أجزاء الثقة: 57.6 − 4 − 6 − 5 = 42.6 ✔"
            ),
        },
        "counting_bases_clarified": {
            "note": ("تصحيح إضافي يمنع لبساً في الإدخال المُصحَّح: فيه قاعدتا عدّ مختلفتان، وتشابههما يوقع في "
                     "قراءة مجموع لا يساوي 14"),
            "base_1_decision_roles_as_delivered": {
                "supporters": 8, "opponents": 1, "abstainers": 5,
                "note": "أدوار تجاه قرار الامتناع كما وردت في نصّ القرار؛ الممتنعون داخل المؤيدين لأن امتناعهم يدعم الامتناع؛ المجموع لا يُقصد به 14",
            },
            "base_2_opinion_orientation_partition": {
                "abstain": 5, "neutral_non_abstaining": 2, "directional": 1, "total": 8,
                "note": "تقسيم طبقة المعرفة 01–08 وحده: 5 ممتنع + 2 محايد + 1 اتجاهي (04 هبوطي مُبطَل)",
            },
            "base_3_artifact_coverage_partition": {
                "file": 7, "quoted_only": 1, "audit_only": 5, "absent": 1, "total": 14,
                "note": "تقسيم تغطية الحزمة لكل الوكلاء 01–14",
            },
        },
        "unaffected_records": [
            {"record_id": CORRECTED_RECORD, "status": "UNCHANGED — لم يُعدَّل حرفاً واحداً (المادتان 7.2 و8.9)"},
            {"record_id": PREDECESSOR_RECORD, "status": "UNCHANGED"},
        ],
        "post_mortem": {
            "status": "PENDING",
            "review_date": REVIEW_DATE,
            "hard_stale_bound": REVIEW_DATE,
            "review_mode": "ABSTAINED",
            "evaluation_class": "SYNTHETIC_TRAINING",
            "excluded_from_weight_updates": True,
            "note": "أفق المراجعة لم يتغيّر عن الإدخال المُصحَّح: 2026-09-22T00:09:44Z (المادة 7.3)",
        },
        "error_patterns": [
            {
                "pattern_id": "F-14",
                "agent": "15 (منهج التسجيل)",
                "description": ("حقل عدّي في سجل دائم يُكتب بلا تحقق آلي من تطابق أقسامه ⇒ رقم تغطية مضخَّم "
                                "يُوهم اكتمالاً أعلى من الواقع"),
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-21T00:58:22+00:00",
                "evidence_refs": [CORRECTED_RECORD, "journal/CORRECTION-2026-0921-0009Z.md"],
                "remedy": ("مُقتَرح ومُنفَّذ جزئياً: حارس `_assert_partitions` في tools/record_cycle_15_20260921.py "
                           "يرفض الكتابة إذا لم يتطابق مجموع الأقسام مع الإجمالي — يُعمَّم على كل سكربتات التسجيل"),
            },
        ],
        "failure_library_additions": [
            {
                "pattern_id": "F-14",
                "description": "رقم تغطية/عدّ في سجل غير قابل للتعديل بلا حارس تحقق من الأقسام",
                "context": "الإدخال JRN-EE42E4AB5CA0: 9 بدل 7 في opinions_present_verifiable ومجموع 16 بدل 14",
                "corrective_sop": ("افرض قبل كل كتابة: مجموع الأقسام = الإجمالي، وعدد العناصر الموصوفة = الحقل "
                                   "المُعلن، ومجموع أجزاء الثقة = الناتج. ورفض الكتابة عند عدم التطابق"),
            },
        ],
        "weight_updates": [],
        "weights_before": store.agent_weights(),
        "weights_after": store.agent_weights(),
        "weight_decision": {
            "reduction_due": False,
            "reason": ("لا تغيير: التصحيح لا يمسّ قاعدة الأوزان. نمط F-14 تكراره الأول (OBSERVED) وسنده وكيل "
                       "التسجيل نفسه (15) لا وكيل معرفي ⇒ لا تخفيض بموجب 7.4، ويكفي التنبيه الذاتي المُوثَّق"),
            "proven_patterns": [],
            "observed_only": ["F-14"],
            "reduction_refused_explicitly": True,
            "refusal_article": "المادة 7.4",
        },
        "market_lessons": [
            {"lesson": ("السجل غير القابل للتعديل لا يحمي من الخطأ — يحميه من الإخفاء فقط: الخطأ هنا بقي ظاهراً "
                        "في السجل، وتصحيحه إدخالٌ جديد. القيمة ليست في «سجل بلا أخطاء» بل في «أخطاء مرئية»"),
             "validity_conditions": "سارية على كل سجل بلا مفتاح HMAC (signed=false) ما دامت السلسلة تُتحقَّق دورياً",
             "confidence": 82},
        ],
        "self_assessment": {
            "confidence": 67,
            "meaning": "ثقة تصف اكتمال التسجيل وصحة التقييم لا صحة القرار المُسجَّل (ملف 15 §7.1)",
            "why_not_higher": ("الإدخال المُصحَّح ظلّ INCOMPLETE (5 آراء بلا ملف خام، والوكيل 12 غائب، وRiskVerdict "
                               "بلا ملف)، وفوقه خطأ عدّ ذاتي استلزم إدخال تصحيح، والمعايرة ما زالت غير قابلة "
                               "للحساب (صفر عيّنة مُقيَّمة)"),
            "why_not_lower": ("الخطأ كُشف وأُعلن وصُحِّح بإدخال مُشير، والسلسلة سليمة، وحارس العدّ صار مُفعَّلاً، "
                              "ولم يُخفَّف أي نصّ ولا حُذف رأي مخالف"),
            "cycle_completeness": "INCOMPLETE (مُعلن) — والتصحيح لا يرفع الاكتمال بل يمنع تجميله (المادة 8.4)",
        },
        "open_items_for_coordinator": [
            "تعميم حارس الأقسام على كل سكربتات التسجيل قبل أي إدخال قادم (F-14)",
            "مراجعة دورية مستقلة لأرقام التغطية في السجل: الوكيل 15 أخفق هنا في حقل واحد كشفه نفسه",
            "بنود الإدخال المُصحَّح تبقى قائمة كما هي (لا يسقط منها شيء بهذا التصحيح)",
        ],
        "process_disclosure": (
            "التصحيح ذو طبيعة إجرائية صرفة (المادتان 7.2 و8.9): لا يُعدّل الإدخال السابق، ولا يغيّر القرار "
            "المُسجَّل ولا الرأي المخالف ولا الأوزان ولا الأفق. والاعتراف بالخطأ واجب بموجب 8.4 (منع تجميل "
            "الأداء) ولو كان الخطأ خطأ وكيل التسجيل نفسه"
        ),
    }
    return payload


def record() -> dict:
    store = JournalStore(CANONICAL)
    before = store.verify_chain()
    if before["records"] != 2:
        raise SystemExit(f"⛔ عدد الإدخالات متوقع 2، والموجود {before['records']} — لا تصحيح على سلسلة غير متوقعة")

    payload = build_payload()
    if payload["error_forensics"]["old_partition_total"] == payload["error_forensics"]["expected_partition_total"]:
        raise SystemExit("⛔ الإدخال المُصحَّح سليم أصلاً — لا مبرر لتصحيح (والتصحيح بلا سبب مخالفة)")

    payload["constitution_fingerprint"] = store.constitution_fingerprint("CONSTITUTION.md")
    rec = store.append(payload, kind="desk_cycle")
    chain = store.verify_chain()
    store.write_markdown_summary()
    write_correction_markdown(rec, chain, payload)

    return {
        "cycle_id": CYCLE_ID,
        "record_id": rec.record_id,
        "sequence": rec.sequence,
        "previous_hash": rec.previous_hash,
        "record_hash": rec.record_hash,
        "timestamp": rec.timestamp,
        "corrects_record_id": payload["corrects_record_id"],
        "chain_valid": chain["valid"],
        "chain_records": chain["records"],
        "head_hash": chain["head_hash"],
        "anchor_check": chain["anchor_check"],
        "weights_after": payload["weights_after"],
        "correction_markdown": str(CORRECTION_MD.relative_to(ROOT)),
        "self_test": {
            "old_partition_total": payload["error_forensics"]["old_partition_total"],
            "expected_partition_total": payload["error_forensics"]["expected_partition_total"],
            "file_artifacts": payload["error_forensics"]["file_artifacts_on_record"],
        },
    }


def write_correction_markdown(record, chain, payload: dict) -> Path:
    lines = [
        "# 【الوكيل 15 — وكيل الذاكرة والسجل】إدخال تصحيح",
        f"## الدورة `{CYCLE_ID}` — إدخال التصحيح `{record.record_id}` يشير إلى `{payload['corrects_record_id']}` "
        "ولا يعدّله (المادة 7.2)",
        "",
        "> ملف **مشتق** من السجل الأصل `journal/desk_journal.jsonl`. الإدخال المُصحَّح لم يُمسّ حرفاً واحداً.",
        "",
        "## 1. البصمة والسلسلة",
        "",
        "| الحقل | القيمة |",
        "|---|---|",
        f"| إدخال التصحيح | `{record.record_id}` (تسلسل {record.sequence}) |",
        f"| بصمة الإدخال السابق | `{record.previous_hash}` |",
        f"| بصمة إدخال التصحيح | `{record.record_hash}` |",
        f"| الإدخال المُصحَّح | `{payload['corrects_record_id']}` — **UNCHANGED** (does_not_modify = true) |",
        f"| طابع التسجيل | `{record.timestamp}` |",
        f"| سلامة السلسلة | {'✅ سليمة' if chain['valid'] else '⛔ مكسورة'} عند {chain['records']} إدخالاً |",
        f"| المرساة | {chain['anchor_check']} |",
        "",
        "## 2. سبب التصحيح (المادة 8.4 — بلا تجميل)",
        "",
        payload["correction_reason"],
        "",
        f"- **نمط السبب:** `{payload['correction_kind']}` — جذر السبب: {payload['error_forensics']['root_cause']}",
        f"- **الكشف:** {payload['error_forensics']['detection']}",
        f"- **نطاق الأثر:** {payload['error_forensics']['blast_radius']}",
        "",
        "## 3. الحقول المُصحَّحة",
        "",
        "| الحقل | القيمة في الإدخال المُصحَّح | القيمة الصحيحة | الإثبات |",
        "|---|---|---|---|",
    ]
    for f in payload["corrected_fields"]:
        lines.append(f"| `{f['field']}` | {f['old_value']} | {f['corrected_value']} | {f['proof']} |")
    lines += [
        "",
        f"- **مجموع الأقسام في الإدخال المُصحَّح:** {payload['error_forensics']['old_partition_total']} "
        f"(والصحيح {payload['error_forensics']['expected_partition_total']})",
        f"- **الملفات الخام المُبصَّمة فعلاً:** {', '.join(payload['error_forensics']['file_artifacts_on_record'])} "
        f"= {payload['error_forensics']['file_artifacts_count']}",
        "",
        "## 4. قواعد العدّ الثلاث — منعاً للبس",
        "",
        payload["counting_bases_clarified"]["note"],
        "",
        f"1. **أدوار القرار كما سُلِّمت:** {json.dumps(payload['counting_bases_clarified']['base_1_decision_roles_as_delivered'], ensure_ascii=False)}",
        "",
        f"2. **تقسيم آراء 01–08:** {json.dumps(payload['counting_bases_clarified']['base_2_opinion_orientation_partition'], ensure_ascii=False)}",
        "",
        f"3. **تقسيم تغطية الحزمة 01–14:** {json.dumps(payload['counting_bases_clarified']['base_3_artifact_coverage_partition'], ensure_ascii=False)}",
        "",
        "## 5. ما لم يتغيّر",
        "",
        "- نصّ القرار المُسجَّل حرفياً، والرأي المخالف بنصّه، وأسباب الحجب الثمانية عشر: **لا تمسّها**.",
        f"- أفق المراجعة البعدية: `{payload['post_mortem']['review_date']}` (المادة 7.3) — لم يتغيّر.",
        f"- الأوزان: التخفيض غير مستحق — {payload['weight_decision']['reason']}",
        "",
        "## 6. الأنماط ومكتبة الفشل",
        "",
        "| المعرّف | الوصف | التكرار | الحالة | العلاج |",
        "|---|---|---|---|---|",
    ]
    for p in payload["error_patterns"]:
        lines.append(f"| {p['pattern_id']} | {p['description']} | {p['occurrence_count']} | {p['status']} | {p['remedy']} |")
    lines += [
        "",
        "## 7. دروس السوق",
        "",
    ]
    for les in payload["market_lessons"]:
        lines.append(f"- {les['lesson']} (شرط الصلاحية: {les['validity_conditions']}؛ ثقة {les['confidence']})")
    lines += [
        "",
        "## 8. الإفصاح والبنود المفتوحة",
        "",
        f"- {payload['process_disclosure']}",
        f"- **الثقة: {payload['self_assessment']['confidence']}/100** — {payload['self_assessment']['meaning']}",
        f"- سبب عدم بلوغ 81+: {payload['self_assessment']['why_not_higher']}",
        f"- سبب عدم الهبوط دون 65: {payload['self_assessment']['why_not_lower']}",
        f"- **اكتمال الدورة:** {payload['self_assessment']['cycle_completeness']}",
        "",
        "**بنود مفتوحة للمنسّق:**",
        "",
    ]
    for item in payload["open_items_for_coordinator"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "- **شرط الإبطال:** يُبطل هذا التصحيح إذا فشل التحقق من السلسلة، أو إذا ثبت أن حقل "
        "`opinions_present_verifiable` في الإدخال المُصحَّح كان صحيحاً (7)، أو إذا كُتب إدخال تصحيح لاحق "
        "يشير إلى هذا الإدخال.",
        "- **المخالف:** الأخذ بأن تصحيح رقم تشخيصي لا يستحق إدخالاً في سلسلة دائمة — والجواب: الرقم الخاطئ في "
        "سجل دائم يُقرأ لاحقاً كحقيقة، وتصحيحه بإدخال جديد هو الوسيلة الوحيدة المشروعة (المادة 7.2).",
        "",
    ]
    CORRECTION_MD.write_text("\n".join(lines), encoding="utf-8")
    return CORRECTION_MD


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="إدخال تصحيح للوكيل 15 — CYC-2026-0921-0009Z")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true")
    g.add_argument("--record", action="store_true")
    args = ap.parse_args()
    if args.probe:
        p = build_payload()
        out = {
            "corrects_record_id": p["corrects_record_id"],
            "corrected_fields": p["corrected_fields"],
            "error_forensics": p["error_forensics"],
            "counting_bases_clarified": p["counting_bases_clarified"],
            "weights_before": p["weights_before"],
        }
    else:
        out = record()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
