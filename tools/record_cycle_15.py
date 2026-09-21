"""
تسجيل دورة القرار ABSTAIN (CYC-2026-0920-2322Z) في السجل غير القابل للتعديل.

الوكيل 15 — وكيل الذاكرة والسجل (المادة 1.1 «التسجيل»، والمواد 6، 7.1–7.4، 8.2، 8.4، 8.9).

المبدأ:
  * لا يُعدّل أي إدخال سابق؛ التصحيح بإدخال جديد يشير للقديم (المادة 7.2).
  * لا يُحمَّل «ما عرفناه لاحقاً» على القرار: لقطة المدخلات مثبَّتة بـsha256 (المادة 8.2).
  * لا تخفيض أوزان بلا نمط مُثبت مكرر 3 مرات (المادة 7.4) — وهذا السكربت يرفض التخفيض ويشرحه.

الاستعمال:
    python tools/record_cycle_15.py --probe     # تحليل السجل التاريخي بلا كتابة
    python tools/record_cycle_15.py --record    # تسجيل الدورة (كتابة مرة واحدة)
    python tools/record_cycle_15.py --verify    # التحقق من سلامة السلسلة

السجل التاريخي المؤرشَف (سلسلة منفصلة) يُقرأ ولا يُكتب:
    journal/archive/desk_journal_demo.jsonl   (4 إدخالات، سلسلة سليمة)
السجل المعياري المُنتَج:
    journal/desk_journal.jsonl                (سلسلة جديدة تبدأ من GENESIS)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from avax_desk.journal.store import JournalStore  # noqa: E402

ARCHIVE = ROOT / "journal" / "archive" / "desk_journal_demo.jsonl"
CANONICAL = ROOT / "journal" / "desk_journal.jsonl"
INPUT = ROOT / "journal" / "records" / "CYC-2026-0920-2322Z.input.json"
CYCLE_MD = ROOT / "journal" / "CYC-2026-0920-2322Z.md"

CYCLE_ID = "CYC-2026-0920-2322Z"
DATA_AS_OF = "2026-09-20T23:22:37+00:00"
REVIEW_DATE = "2026-09-21T23:00:00+00:00"          # مقترح 14، مُعتمد
HARD_STALE_BOUND = "2026-09-21T23:22:37+00:00"      # اللقطة + 24 ساعة (المادة 3.4)
ASSIGNED_DECISION_ID = "DEC-B93B313812"             # مُنشأ من الوكيل 15 (لم يُسلَّم معرّف من 14)

# ملفات لقطة الأدلة لحظة القرار — بصمات تُثبَّت (المادة 8.2)
EVIDENCE_FILES = [
    ("CONSTITUTION.md", "الدستور الملزم — بصمته داخل السجل (المادة 10.1)"),
    ("data/snapshot_full.json", "لقطة البيانات as_of 2026-09-20T23:22:37Z — synthetic-deterministic seed=11 scenario=bull"),
    ("reports/agent-01-market-structure.json", "رأي 01 — الحقول الستة كاملة"),
    ("reports/agent-06-derivatives-volatility-seed11.json", "رأي 06 (نسخة seed11) — الحقول الستة كاملة"),
    ("reports/agent-09-validation-verdict.md", "حكم التحقق 09 = INSUFFICIENT_DATA"),
    ("reports/redteam-10-consensus-neutral.md", "محامي الشيطان 10 — الحجة المضادة"),
    ("reports/agent-13-compliance-report.md", "تقرير الالتزام 13 = FAIL (0.731) + النقض CVETO-2026-0920-13-01"),
    ("reports/demo-bull-seed11.md", "المخرج الآلي الموازي (LONG) المُستشهد به في الرأي المخالف"),
    ("AUDIT_REPORT.md", "التدقيق السابق المرجعي"),
    ("journal/archive/desk_journal_demo.jsonl", "السجل التاريخي المؤرشَف (سلسلة خوانية منفصلة) — لا يُعدَّل"),
]


def sha256_file(rel: str) -> str | None:
    p = ROOT / rel
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def archive_report() -> dict:
    """تحليل السجل التاريخي المؤرشف — قراءة فقط، بلا أي كتابة (المادة 7.2)."""
    if not ARCHIVE.exists():
        return {"available": False}
    store = JournalStore(ARCHIVE)
    chain = store.verify_chain()
    weights = store.agent_weights()
    calibration = store.calibration()
    decisions = store.decisions()

    pm = None
    for rec in store.records():
        payload = rec.payload.get("post_mortem") or {}
        if payload.get("agent_scores"):
            pm = {"record_id": rec.record_id, "sequence": rec.sequence, **payload}
    scores = (pm or {}).get("agent_scores", [])
    below = sorted(a for a, ok in ((s["agent_id"], s["correct"]) for s in scores) if not ok)
    above = sorted(a for a, ok in ((s["agent_id"], s["correct"]) for s in scores) if ok)

    return {
        "available": True,
        "path": str(ARCHIVE.relative_to(ROOT)),
        "sha256": sha256_file("journal/archive/desk_journal_demo.jsonl"),
        "records": chain["records"],
        "chain_valid": chain["valid"],
        "head_hash": chain["head_hash"],
        "anchor": chain["anchor_check"],
        "signed": chain["signed"],
        "decisions": [{"decision_id": d.get("decision_id"), "action": d.get("action"),
                       "confidence": d.get("confidence"), "timestamp": d.get("timestamp")}
                      for d in decisions],
        "history_weights": weights,
        "calibration": calibration,
        "last_post_mortem": pm,
        "scored_incorrect": below,
        "scored_correct": above,
    }


def projected_wrong_cut(archive: dict) -> dict:
    """
    إسقاط تحذيري: لو تكرر نفس نمط التقييم (F-11) ثلاث مرات كما هو، ماذا ستفعل قاعدة
    `JournalStore.agent_weights` (store.py:258-286)؟ الغرض إظهار أثر الخطر لا إقراره.
    """
    scores = (archive.get("last_post_mortem") or {}).get("agent_scores", [])
    if not scores:
        return {"applicable": False}
    once = {s["agent_id"]: [bool(s["correct"])] for s in scores}
    thrice = {a: v * 3 for a, v in once.items()}
    out = {}
    for aid, results in sorted(thrice.items()):
        hit = sum(results) / len(results)
        if hit < 0.34:
            out[aid] = 0.50
        elif hit < 0.45:
            out[aid] = 0.75
        elif hit > 0.65:
            out[aid] = 1.25
        else:
            out[aid] = 1.0
    return {
        "applicable": True,
        "note": ("إسقاط افتراضي على النمط الحالي ثلاث مرات — لا يُنفَّذ: النمط OBSERVED لا PROVEN "
                 "(المادة 7.4) والمراجعة البعدية مُوسَمة SYNTHETIC_TRAINING"),
        "weights_if_pattern_repeats_3x": out,
        "penalized_agents": sorted(a for a, w in out.items() if w < 1.0),
        "rewarded_agents": sorted(a for a, w in out.items() if w > 1.0),
    }


def build_payload(archive: dict) -> dict:
    delivered = json.loads(INPUT.read_text(encoding="utf-8"))
    dec_in = delivered["delivered_decision"]
    rv_in = delivered["delivered_risk_verdict"]

    evidence = []
    for rel, note in EVIDENCE_FILES:
        digest = sha256_file(rel)
        evidence.append({
            "claim": f"بصمة الملف {rel}: {digest or 'غير موجود'}",
            "source": rel,
            "timestamp": DATA_AS_OF,
            "kind": "derived",
            "strength": "high" if digest else "low",
            "note": note,
        })

    decision = {
        "decision_id": ASSIGNED_DECISION_ID,
        "decision_id_note": ("معرّف مُنشأ من الوكيل 15 لحظة التسجيل — القرار المُسلَّم لم يحمل معرّفاً "
                             "ولا طابعاً زمنياً؛ لم يُختلق أي منهما (المادتان 2.5 و8.1)"),
        "asset": "AVAX",
        "action": dec_in["action"],
        "confidence": dec_in["confidence"],
        "horizon": dec_in["horizon"],
        "invalidation": dec_in["invalidation"],
        "rationale": dec_in["rationale"],
        "supporting_agents": dec_in["supporting_agents"],
        "opposing_agents": dec_in["opposing_agents"],
        "abstaining_agents": ["01", "03", "04", "07", "08"],
        "strongest_dissent": dec_in["strongest_dissent"],
        "dissent_source": "agent",
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
            "violations": [],
            "checked_agents": 12,
            "blocked": True,
            "notes": [
                "تقرير الوكيل 13 كما ورد = FAIL: Compliance_Rate = 0.731 (19/26)، 16 ملاحظة، "
                "12 مخالفة جسيمة + 4 شكلية، ونقض CVETO-2026-0920-13-01",
                "ملاحظة المنسّق المرافقة «الالتزام متوافق» تُسجَّل ولا تنقض مضمون التقرير",
            ],
            "timestamp": "2026-09-20T23:55:00+00:00",
        },
        "evidence_summary": evidence,
        "timestamp": "",
        "timestamp_note": ("القرار المُسلَّم إلى الوكيل 15 لم يحمل طابعاً زمنياً؛ وقت التسجيل مثبَّت في "
                            "حقل الإدخال أعلى السجل، ووقت البيانات هو data_as_of. لم أُسند للقرار وقتاً "
                            "لم يُقدَّم (المادتان 2.5 و8.1)"),
    }

    opinions_digest = [
        {"agent_id": "01", "direction": "abstain", "confidence": None, "stake": "امتناع — استبعاد الطبقتين 1–2"},
        {"agent_id": "02", "direction": "neutral", "confidence": None, "stake": "محايد اتجاهياً + بنية فنية صاعدة (معارض مسجَّل)"},
        {"agent_id": "03", "direction": "abstain", "confidence": None, "stake": "امتناع"},
        {"agent_id": "04", "direction": "abstain", "confidence": None, "stake": "امتناع"},
        {"agent_id": "05", "direction": "neutral", "confidence": None, "stake": "محايد"},
        {"agent_id": "06", "direction": "neutral", "confidence": None, "stake": "محايد"},
        {"agent_id": "07", "direction": "abstain", "confidence": None, "stake": "امتناع"},
        {"agent_id": "08", "direction": "abstain", "confidence": None, "stake": "امتناع"},
        {"agent_id": "09", "direction": "neutral", "confidence": 34.0, "stake": "INSUFFICIENT_DATA — لا حافة مُجازة"},
        {"agent_id": "10", "direction": "bearish", "confidence": None, "stake": "حجة مضادة (السجل الأصلي: قطبية الحجة لا اتجاه القرار)"},
        {"agent_id": "11", "direction": "neutral", "confidence": 78.0, "stake": "VETOED — نقض نافذ، risk_level=red، حجم 0"},
        {"agent_id": "12", "direction": "neutral", "confidence": None, "stake": "لا خطة تنفيذ مُقدَّمة (اختياري)"},
        {"agent_id": "13", "direction": "neutral", "confidence": 90.0, "stake": "FAIL (0.731) + نقض CVETO-2026-0920-13-01"},
        {"agent_id": "14", "direction": "neutral", "confidence": 0.0, "stake": "ABSTAIN (abstention_kind=risk_veto)"},
    ]

    payload = {
        "cycle_id": CYCLE_ID,
        "record_type": "decision",
        "immutable": True,
        "recorded_by": "15",
        "asset": "AVAX",
        "data_as_of": DATA_AS_OF,
        "opinions_expected": 14,
        "opinions_present": len(opinions_digest),
        "opinions_digest": opinions_digest,
        "opinions_digest_source": ("مُعاد بناؤه من نصّ قرار 14 + حكم 11 + تقرير 13؛ ملفات الآراء الخام "
                                   "غائبة لـ02,03,04,05,07,08 (ملاحظة 13: F1) ⇒ لا thesis/horizon/dissent "
                                   "قابلة للتحقق لهذه الآراء (المادة 2.1)"),
        "decision": decision,
        "risk_verdict": rv_in,
        "proposal": {
            "direction": "neutral",
            "score": 0.0,
            "confidence": 0.0,
            "agreement": 0.0,
            "supporters": [],
            "opposers": ["10", "02"],
            "abstainers": ["01", "03", "04", "07", "08"],
            "base_confidence": 0.0,
            "penalties": [
                "−6 بوابة الجودة (المادة 4.1 غير مستوفاة لأي فرضية)",
                "−5 لقلة المؤيدين عن 3",
            ],
            "validation_discounts": {},
            "history_weights": archive.get("history_weights", {}),
            "validated": False,
            "note": "لا ترجيح هذه الدورة: البروتوكول انتهى عند البوابة 3 (نقض نافذ، المادة 5.1)",
        },
        "compliance": decision["compliance"],
        "snapshot_meta": {
            "asset": "AVAX",
            "source": "synthetic-deterministic",
            "timestamp": DATA_AS_OF,
            "seed": 11,
            "scenario": "bull",
            "bars_provided": 120,
            "warning": ("بيانات اصطناعية حتمية — ليست شبكة حقيقية ولا سوقاً حقيقياً (المادتان 3.1 و3.3). "
                        "طبقات الأدلة 1–2 غير مستحقة."),
        },
        "evidence_at_decision_time": evidence,
        "dissent_record": {
            "supporters": 3,
            "supporters_raw_field": dec_in["supporting_agents"],
            "supporters_note": ("حقل supporting_agents يحمل 8 أرقام لأنه يضمّ الممتنعين 01/03/04/07/08؛ "
                                "العدد التصحيحي للمؤيدين الفاعلين للامتناع = 3 (11 نقض، 09 حدّ أدنى للبيانات، "
                                "13 حجب/FAIL). المادة 6.2 تطلب عدداً صحيحاً لا مضخَّماً"),
            "opponents": 2,
            "abstainers": 5,
            "neutral": 3,
            "strongest_counter_argument": dec_in["strongest_dissent"],
            "source_agent": "10",
            "verbatim_preserved": True,
            "dissent_source_chain": ("10 (حجة مضادة) + 02 (بنية فنية صاعدة) + إشارة إلى المخرج الآلي الموازي "
                                     "reports/demo-bull-seed11.md — بقي حجة لا دليل قرار، المادة 1.4"),
        },
        "post_mortem": {
            "status": "pending",
            "due_horizon": dec_in["horizon"],
            "evaluation_class": "SYNTHETIC_TRAINING",
            "excluded_from_weight_updates": True,
            "review_date": REVIEW_DATE,
            "hard_stale_bound": HARD_STALE_BOUND,
            "review_mode": "ABSTAINED",
            "review_criteria": [
                "هل كان الامتناع صحيحاً؟ يُقاس بثلاثة أسئلة منفصلة عن الربح: (أ) هل بقيت أسباب النقض السبعة قائمة؟ "
                "(ب) المسار المضاد الواقعي من P0=115.5413 مع وقف 2×ATR=13.73% — هل كان مركز LONG سيُوقف أم سيُربح؟ "
                "(ج) هل أُغلقت ملاحظات 13 (F1/F2/F3/F11) ونُفِّذ علاج F6/F11؟",
                "لا يُقيَّم قرار 2026-09-20 بأي معلومة لم تكن متاحة 23:22:37Z؛ ما يُعرف لاحقاً يُسجَّل ملاحظة لا حكماً (المادة 8.2)",
                "إن رُفع النقض قبل REVIEW_DATE وفق شروط الإبطال، تُقدَّم المراجعة إلى لحظة رفع النقض + دورة واحدة",
            ],
            "agent_scores": [],
            "scores_excluded_reason": ("لا صحة اتجاهية في هذه الدورة (0 آراء اتجاهية)؛ وتقييم عملية اصطناعية حتمية "
                                       "بـ«صواب/خطأ» نمط يجب ألا يغذّي الأوزان (المادة 7.4)"),
        },
        "outcome": {
            "status": "PENDING",
            "review_date": REVIEW_DATE,
            "hard_stale_bound": HARD_STALE_BOUND,
            "realized_pnl_pct": 0.0,
            "max_adverse_excursion_pct": 0.0,
            "invalidation_triggered": False,
            "hindsight_notes": "لا شيء بعد — تُملأ عند REVIEW_DATE بمقارنة اللقطة بسعر السوق الفعلي",
        },
        "agent_scores": [],
        "calibration": {
            "samples_canonical_chain": 0,
            "samples_archive_chain": archive.get("calibration", {}).get("samples"),
            "brier_archive": archive.get("calibration", {}).get("brier_score"),
            "note": ("Brier = 0.08922 على عيّنة واحدة اصطناعية: رقم يبدو ممتازاً ولا يعني شيئاً — "
                     "المعايرة تحتاج عدداً كافياً من الحالات (ملف 15 §3.3أ و§3.4)، ولا يُقرأ Hit Rate أو "
                     "Brier وحده"),
            "curve": [],
        },
        "error_patterns": [
            {
                "pattern_id": "F-11",
                "agent": "15 (منهج القياس) + المنسّق",
                "description": ("تقييم اتجاهي «صواب/خطأ» على مخرجات عملية اصطناعية حتمية وتغذية قاعدة الأوزان "
                                "(7.4) بها، مع احتساب الوكلاء المحايدين (09–14) «مخطئين» اتجاهياً"),
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-20T21:02:17+00:00",
                "evidence_refs": ["JRN-C537BA9599F3", "تقرير 13 ملاحظة F6"],
                "remedy": "وسم المراجعة SYNTHETIC_TRAINING وإخراجها من تغذية 7.4 — مُنفَّذ في هذا الإدخال",
            },
            {
                "pattern_id": "F-12",
                "agent": "15",
                "description": "سجل الدورة غائب عند التدقيق (خرق 7.1)، وتسمية السجل المؤرشف غير موضَّحة",
                "occurrence_count": 1,
                "status": "OBSERVED",
                "first_seen": "2026-09-20T23:55:00+00:00",
                "evidence_refs": ["CVETO-2026-0920-13-01 (F11)", "تقرير 13 §4"],
                "remedy": "هذا الإدخال يُنتج سجلاً للدورة 23:22:37Z (لا يُعدّل سابقاً) — وتسمية الأرشيف تُرفع للمنسّق",
            },
        ],
        "weight_updates": [],
        "weights_before": archive.get("history_weights", {}),
        "weights_after": archive.get("history_weights", {}),
        "weight_decision": {
            "reduction_due": False,
            "reason": ("المادة 7.4 تشترط نمطاً واحداً مكرراً 3 مرات موثَّقاً بمعرّف في مكتبة الفشل. "
                       "أقصى ما في السجل إدخال مراجعة بعدية واحد (JRN-C537BA9599F3) لكل وكيل = عيّنة واحدة "
                       "< min_samples=3 ⇒ لا تخفيض ولا رفع: الأوزان التاريخية تبقى 1.0 لكل الوكلاء 01–14"),
            "proven_patterns": [],
            "observed_only": ["F-11", "F-12"],
            "reduction_refused_explicitly": True,
            "refusal_article": "المادة 7.4 (التخفيض بلا نمط مُثبت مكرر 3 مرات مخالفة)",
        },
        "distinct_from_7_4": {
            "note": ("تمييز ضروري: خصومات التحقق validation_discounts (01→0.80، 07→0.55) في الدورات المسجّلة "
                     "هي عقوبة المادة 4.1 (إشارة لم تجتز قانون التحقق) وليست تخفيض وزن بالمادة 7.4؛ "
                     "ولا هي وزن تاريخي history_weights (الكل 1.0)"),
            "source": "journal/archive/desk_journal_demo.jsonl (JRN-656FCC207CB0 وJRN-6FAE7B5C64D3)",
        },
        "failure_library_additions": [
            {"pattern_id": "F-11", "description": "قياس دقة وكيل على مخرجات غير سوقية (اصطناعية حتمية) واحتساب الحياد خطأً اتجاهياً",
             "context": "démo seed=11 scenario=bull؛ مراجعة بعدية واحدة سجّلت 8 وكلاء «مخطئين» بينهم كل طبقة الضبط 09–13",
             "corrective_sop": "وسم SYNTHETIC_TRAINING + إخراج من تغذية 7.4 + عدم تقييم وكيل غير اتجاهي بالاتجاه"},
            {"pattern_id": "F-12", "description": "دورة تُدقَّق بلا إدخال سجل (خرق 7.1) ومسار سجل مُبهم (archive مقابل canonical)",
             "context": "الدورة 2026-09-20T23:22:37Z دُقّقت 23:55Z وآخر إدخال كان 22:50:46Z في ملف مؤرشف",
             "corrective_sop": "تسجيل الدورة في journal/desk_journal.jsonl قبل التدقيق وبعده؛ وتوثيق الانتقالات ببيان صريح"},
        ],
        "market_lessons": [
            {"lesson": ("تحت مصدر synthetic-deterministic لا يمكن أن يوجد دليل مستوى 1 أو 2؛ فكل ترجيح يستند إلى "
                        "3/4/5/7 — ووسم «بيانات أونشين مباشرة» على مخرجات اصطناعية خرق موسم (ملاحظة 13: F4)"),
             "validity_conditions": "سارية ما دام _meta.source = synthetic-deterministic والحاوية تُعلن نفسها كذلك",
             "confidence": 85},
            {"lesson": ("ضغط «لا مركز» يظهر مرتين في هذه الدورة على مسارين مستقلين (نقض 11، وحجب/FAIL 13) "
                        "ويتقاربان إلى النتيجة نفسها — أي أن الامتناع هنا صامد لا هشّ"),
             "validity_conditions": "صالح لهذه الدورة (23:22:37Z)؛ لا يُعمَّم على دورات بمصدر موقّع",
             "confidence": 78},
        ],
        "corrections": [
            {"corrects_record_id": "JRN-C537BA9599F3",
             "target_chain": "journal/archive/desk_journal_demo.jsonl",
             "reason": ("تقييم اتجاهي على عملية اصطناعية حتمية واحتساب المحايدين (09–14) «مخطئين»، ودرس مكتوب "
                        "بلغة يقين اتجاهي في سجل دائم (تقرير 13: F6 — المادتان 8.2 و8.8). التصحيح بإدخال جديد: "
                        "وسم النتيجة SYNTHETIC_TRAINING وإخراجها من تغذية 7.4"),
             "does_not_modify": True},
            {"corrects_record_id": "JRN-F10FD990406A",
             "target_chain": "journal/archive/desk_journal_demo.jsonl",
             "reason": ("وسوم «بيانات أونشين مباشرة» بمستوى 1 ومصادر منصات على تشغيل يعلن حاويه أنه اصطناعي "
                        "(تقرير 13: F4). لا يُعدَّل الإدخال؛ يُسجَّل الوسم الصحيح: مستوى 3 مشتق"),
             "does_not_modify": True},
        ],
        "journal_lineage": {
            "canonical_path": "journal/desk_journal.jsonl",
            "records_in_canonical_before": 0,
            "prior_chain": {
                "path": str(ARCHIVE.relative_to(ROOT)),
                "sha256": archive.get("sha256"),
                "records": archive.get("records"),
                "head_hash": archive.get("head_hash"),
                "chain_valid": archive.get("chain_valid"),
                "carried_forward": False,
                "reason": ("لم يُنقل أي إدخال مؤرشف إلى السلسلة المعيارية: الإدخالات الأربعة دورات اصطناعية "
                           "تعليمية (الملف موسوم demo) ونقلها كان سيُلبسها صفة دورات إنتاج. تُقرأ كسلسلة "
                           "خوانية منفصلة وتُستشهد ببصمتها"),
                "open_item_for_coordinator": "حسم تسمية/موقع السجل التاريخي (تقرير 13 §4: «تسمية/أرشفة تحتاج توضيح المنسّق»)",
            },
        },
        "constitution_fingerprint": {},
        "law_audit": {"total": 0, "errors": 0, "warnings": 0, "by_article": {}, "by_code": {}},
        "constitution_version": "1.0",
        "open_items_for_coordinator": [
            "F-11/F-12 مُسجَّلان OBSERVED — لا تخفيض أوزان قبل إثبات نمط مكرر 3 مرات (المادة 7.4)",
            "القرار المُسلَّم بلا طابع زمني وبلا معرّف: وقت التسجيل ووقت البيانات مُثبَّتان، والفجوة مُعلنة لا مُسدودة",
            "حقل supporting_agents يخلط المؤيدين بالممتنعين (8 مقابل 3) — تصحيح الحقل عند المصدر",
            "مسار السجل التاريخي (archive demo مقابل canonical) يحتاج قرار المنسّق",
            "ملاحظات 13 (F1/F2/F3) تمنع اكتمال عقد الرأي لستة آراء ⇒ الدورة INCOMPLETE بمعيار عقد المدخلات",
        ],
        "self_assessment": {
            "confidence": 70,
            "meaning": "ثقة تصف اكتمال التسجيل وصحة التقييم لا صحة القرار المُسجَّل (ملف 15 §7.1)",
            "why_not_higher": ("شريحة 81+ تشترط دورة كاملة موثقة + سلسلة سليمة + مقاييس معايرة محسوبة: "
                               "السلسلة سليمة لكن المعايرة غير قابلة للحساب (1 عيّنة اصطناعية) وعقد الرأي "
                               "ناقص لستة آراء ⇒ لا استحقاق لأعلى من 80"),
            "why_not_lower": "السلسلة مختومة وسليمة، والرأي المخالف محفوظ بنصّه، والأوزان لم تُخفَّض بلا نمط مُثبت",
        },
        "recorded_at_note": "طابع الإدخال في السجل يُنتجه now_iso() لحظة الكتابة (المادة 2.5) — منفصل عن وقت البيانات data_as_of",
    }
    return payload


def record() -> dict:
    archive = archive_report()
    if not archive.get("available"):
        raise SystemExit("⛔ السجل التاريخي غير موجود — لا يمكن بناء تحليل الأوزان")

    store = JournalStore(CANONICAL)
    payload = build_payload(archive)
    payload["constitution_fingerprint"] = store.constitution_fingerprint("CONSTITUTION.md")
    payload["constitution_fingerprint"]["note_archive"] = (
        "بصمة الدستور نفسها (697c9003…) مسجّلة في السلسلة المؤرشفة بإدخال JRN-F10FD990406A ⇒ changed=false عبر السلسلتين")

    record = store.append(payload, kind="desk_cycle")

    chain = store.verify_chain()
    md = store.write_markdown_summary()
    write_cycle_markdown(record, chain, archive, payload)

    return {
        "cycle_id": CYCLE_ID,
        "record_id": record.record_id,
        "sequence": record.sequence,
        "previous_hash": record.previous_hash,
        "record_hash": record.record_hash,
        "timestamp": record.timestamp,
        "chain_valid": chain["valid"],
        "chain_records": chain["records"],
        "head_hash": chain["head_hash"],
        "anchor_check": chain["anchor_check"],
        "journal_path": str(CANONICAL.relative_to(ROOT)),
        "markdown_summary": str(md.relative_to(ROOT)),
        "cycle_markdown": "journal/CYC-2026-0920-2322Z.md",
        "weights_after": payload["weights_after"],
        "weight_reduction_due": payload["weight_decision"]["reduction_due"],
        "post_mortem_review_date": REVIEW_DATE,
    }


def write_cycle_markdown(record, chain, archive, payload: dict) -> Path:
    dec = payload["decision"]
    dr = payload["dissent_record"]
    lines = [
        "# 【الوكيل 15 — وكيل الذاكرة والسجل】",
        f"## الدورة `{CYCLE_ID}` — إدخال `{record.record_id}` — النوع: `decision` (قرار) — غير قابل للتعديل",
        "",
        "> ملف **مشتق** للقراءة من السجل الأصل `journal/desk_journal.jsonl`. المصدر الوحيد للحقيقة هو JSONL؛ "
        "هذا الملف لا يُعدّل السجل ولا يُحتجّ به عليه.",
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
        f"**تحذير حدود الحماية:** {chain['limits']}",
        "",
        "## 2. القرار المُسجَّل حرفياً (المادتان 6.1 و7.2)",
        "",
        f"- **القرار:** `{dec['action']}` — نوع الامتناع `{dec['abstention_kind']}` — الحجم: **0** — لا entry/stop/target",
        f"- **الثقة المُعلنة:** {dec['confidence']} (شريحة «تخمين» في سلّم 7.1 — وغير مؤهلة للدخول)",
        f"- **المعرّف:** `{dec['decision_id']}` ({dec['decision_id_note']})",
        f"- **الطابع الزمني للقرار:** لم يُسلَّم — {dec['timestamp_note']}",
        f"- **الأفق كما قُرّر:** {dec['horizon']}",
        f"- **سبب الامتناع:** حجب المخاطر (المادة 5.1) — {len(dec['blocks'])} سبباً مُثبتاً في حقل `blocks`",
        "",
        "### الرأي المخالف بنصّه (المادتان 6.1 و6.3) — لا يُحذف ولا يُخفَّف",
        "",
        dec["strongest_dissent"],
        "",
        "## 3. لقطة الأدلة لحظة القرار (المادة 8.2)",
        "",
        f"{len(payload['evidence_at_decision_time'])} عنصراً مثبَّتاً ببصمة sha256:",
        "",
        "| الملف | البصمة (أول 16) |",
        "|---|---|",
    ]
    for ev in payload["evidence_at_decision_time"]:
        lines.append(f"| `{ev['source']}` | `{(ev['claim'].split()[-1] or '—')[:16]}` |")
    lines += [
        "",
        "## 4. المخرجات والآراء",
        "",
        f"- المؤيدون الفاعلون للامتناع: **{dr['supporters']}** (11 نقض · 09 حدّ أدنى للبيانات · 13 حجب/FAIL) | "
        f"المعارضون: **{dr['opponents']}** (10، 02) | الممتنعون: **{dr['abstainers']}** | المحايدون: **{dr['neutral']}**",
        f"- تنبيه تعداد: {dr['supporters_note']}",
        f"- الآراء المُحصاة في نصّ القرار: {payload['opinions_present']} من أصل {payload['opinions_expected']} "
        f"وكيلاً — لكن الحقول الستة غير قابلة للتحقق لستة آراء (02,03,04,05,07,08) لغياب ملف دائم لكل "
        f"منها، وواحد فقط من الآراء الاتجاهية شهد تحققاً مُجازاً (ملاحظة 13: F1)",
        f"- تقرير الالتزام 13: **FAIL** — Compliance_Rate = 0.731، 16 ملاحظة، 12 جسيمة + 4 شكلية، "
        f"ونقض `CVETO-2026-0920-13-01`",
        "",
        "## 5. المراجعة البعدية — الأفق المستحق (المادة 7.3)",
        "",
        "| الحقل | القيمة |",
        "|---|---|",
        f"| **تاريخ المراجعة المستحق** | **`{REVIEW_DATE}`** |",
        f"| الحد الخارجي للتقادم | `{HARD_STALE_BOUND}` (اللقطة + 24 ساعة — المادة 3.4) |",
        "| وضع التقييم | `ABSTAINED` — يُقيَّم بمعيار «هل كان الامتناع صحيحاً؟» لا بالربح |",
        f"| وسم التقييم | `{payload['post_mortem']['evaluation_class']}` — مُخرَج من تغذية الأوزان (7.4) |",
        "",
        "**الأفق:** القرار بلا أفق تداول (لا مركز)؛ فأقرب أفق قابل للقياس هو دورة التحليل التالية، وحدّه الأعلى "
        "24 ساعة قبل وسم اللقطة `STALE`. لذلك تجب المراجعة عند `2026-09-21T23:00Z`، ولا يجوز تأخيرها بعد "
        "`2026-09-21T23:22:37Z` — وإلا صار القرار غير قابل للتقييم بمعياره (المادتان 7.3 و3.4).",
        "",
        "**معايير المراجعة الثلاثة:**",
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
    for aid in sorted(weights):
        lines.append(f"| {aid} | {weights[aid]} | لا — عيّنة واحدة < 3 |")
    if not weights:
        lines.append("| — | لا سجل مراجعة بعدية | لا |")
    lines += [
        "",
        f"**الحكم:** {payload['weight_decision']['reason']}",
        "",
        f"**بدون لبس:** {payload['distinct_from_7_4']['note']}",
        "",
        "### تحذير إسقاطي (لا يُنفَّذ)",
        "",
    ]
    proj = projected_wrong_cut(archive)
    if proj.get("applicable"):
        lines += [
            "لو تكرر نمط التقييم F-11 ثلاث مرات كما هو، لقاعدة `agent_weights` هذه النتيجة:",
            "",
            f"- يُخفَّض إلى 0.50: {', '.join(proj['penalized_agents'])}",
            f"- يُرفع إلى 1.25: {', '.join(proj['rewarded_agents'])}",
            "",
            "أي أن طبقة الضبط (09–13) ستُعاقب على عملية اصطناعية حتمية والفارق سيبلغ 2.5× — ولهذا مُنع "
            "التخفيض (المادة 7.4) ووُسم التقييم `SYNTHETIC_TRAINING`.",
            "",
        ]
    lines += [
        "## 7. الأنماط ومكتبة الفشل",
        "",
        "| المعرّف | الوصف | التكرار | الحالة | العلاج |",
        "|---|---|---|---|---|",
    ]
    for p in payload["error_patterns"]:
        lines.append(f"| {p['pattern_id']} | {p['description']} | {p['occurrence_count']} | {p['status']} | {p['remedy']} |")
    lines += [
        "",
        "## 8. التصحيحات (المادة 7.2 — إدخال جديد يشير للقديم، بلا تعديل)",
        "",
    ]
    for c in payload["corrections"]:
        lines.append(f"- `{c['corrects_record_id']}` في `{c['target_chain']}`: {c['reason']} "
                     f"(does_not_modify = {c['does_not_modify']})")
    lines += [
        "",
        "## 9. السلسلة التاريخية (خوانية لا موروثة)",
        "",
        f"- الملف: `{payload['journal_lineage']['prior_chain']['path']}` — "
        f"{payload['journal_lineage']['prior_chain']['records']} إدخالات، "
        f"سليمة: {payload['journal_lineage']['prior_chain']['chain_valid']}",
        f"- البصمة sha256: `{payload['journal_lineage']['prior_chain']['sha256']}`",
        f"- رأس السلسلة: `{payload['journal_lineage']['prior_chain']['head_hash']}`",
        f"- **هل نُقلت الإدخالات المؤرشفة إلى السلسلة الجديدة؟** لا. {payload['journal_lineage']['prior_chain']['reason']}",
        f"- بند مفتوح: {payload['journal_lineage']['prior_chain']['open_item_for_coordinator']}",
        "",
        "## 10. دروس السوق",
        "",
    ]
    for les in payload["market_lessons"]:
        lines.append(f"- {les['lesson']} (شرط الصلاحية: {les['validity_conditions']}؛ ثقة {les['confidence']})")
    lines += [
        "",
        "## 11. بنود مفتوحة للمنسّق",
        "",
    ]
    for item in payload["open_items_for_coordinator"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "## 12. خاتمة الوكيل 15",
        "",
        f"- **الثقة: {payload['self_assessment']['confidence']}/100** — {payload['self_assessment']['meaning']}",
        f"- سبب عدم بلوغ 81+: {payload['self_assessment']['why_not_higher']}",
        f"- سبب عدم الهبوط دون 65: {payload['self_assessment']['why_not_lower']}",
        "- **شرط الإبطال:** يُبطل هذا التسجيل إذا فشل التحقق من السلسلة (تعديل خارجي)، أو إذا لم تُنفَّذ "
        "المراجعة البعدية عند `" + REVIEW_DATE + "`، أو إذا ثبت أن لقطة الأدلة المثبَّتة لا تطابق ما اعتُمد وقت القرار.",
        "- **المخالف:** السجل يحفظ ما **قيل** لا ما **صحّ**؛ وهذا الإدخال يوثّق امتناعاً لا نتيجة، وقيمته "
        "تُختبر عند 2026-09-21T23:00Z لا قبله.",
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
        "sequences": [(r.sequence, r.record_id, r.timestamp) for r in records],
        "actions": [d.get("action") for d in store.decisions()],
        "summary": store.summary(),
        "archive_untouched_sha256": archive_report().get("sha256"),
    }


def rebuild_summaries() -> dict:
    """
    يُعيد توليد الملفات المشتقة من السجل فقط — بلا أي إضافة إلى السلسلة.

    الحدود: الملخصات مشتقة وقابلة لإعادة التوليد؛ السجل (JSONL) هو المصدر الوحيد
    للحقيقة ولا يُعدَّل هنا (المادة 7.2).
    """
    store = JournalStore(CANONICAL)
    records = store.records()
    if not records:
        raise SystemExit("⛔ لا إدخالات في السلسلة المعيارية — لا شيء لإعادة التوليد")
    record = records[-1]
    archive = archive_report()
    chain = store.verify_chain()
    md = store.write_markdown_summary()
    cycle_md = write_cycle_markdown(record, chain, archive, record.payload)
    return {
        "regenerated_from": record.record_id,
        "records": chain["records"],
        "chain_valid": chain["valid"],
        "head_hash": chain["head_hash"],
        "summary": str(md.relative_to(ROOT)),
        "cycle_markdown": str(cycle_md.relative_to(ROOT)),
        "appended": False,
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="تسجيل دورة الوكيل 15")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true", help="تحليل السجل التاريخي بلا كتابة")
    g.add_argument("--record", action="store_true", help="تسجيل الدورة (كتابة)")
    g.add_argument("--verify", action="store_true", help="التحقق من سلامة السلسلة المعيارية")
    g.add_argument("--rebuild-summary", action="store_true",
                   help="إعادة توليد الملخصات المشتقة من السجل بلا إضافة إدخال")
    args = ap.parse_args()

    if args.probe:
        archive = archive_report()
        out = {"archive": archive, "projection": projected_wrong_cut(archive),
               "canonical_exists": CANONICAL.exists()}
    elif args.record:
        out = record()
    elif args.rebuild_summary:
        out = rebuild_summaries()
    else:
        out = verify()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
