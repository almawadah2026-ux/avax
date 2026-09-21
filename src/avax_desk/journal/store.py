"""
سجل الديسك — CONSTITUTION.md المادة 7.

خصائص إلزامية:
    7.1 كل دورة تُكتب في السجل
    7.2 السجل غير قابل للتعديل — مربوط بسلسلة هاش (Hash Chain)
    7.3 كل قرار يُراجَع بعد انتهاء أفقه (Post-Mortem)
    7.4 الوكيل الذي يتكرر خطؤه 3 مرات يُخفَّض وزنه

التصميم يضمن أن أي تعديل يدوي على السجل **يُكشف آلياً** عند التحقق.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from pathlib import Path
from typing import Any

from ..contracts import DeskDecision, JournalRecord, now_iso


class JournalStore:
    """
    سجل JSONL غير قابل للتعديل مع تحقق من السلسلة.

    **حدود الحماية (مهم — لا تبالغ في قراءتها):**
    الشعار الشائع «أي تعديل يدوي يُكشف آلياً» **غير دقيق**. الحقيقة:

    ✅ **يُكشف:** تعديل محتوى سجل (هاشه لا يطابق)، حذف سجل من المنتصف، إعادة ترتيب.
    ❌ **لا يُكشف:** إعادة كتابة الملف **كاملاً** مع إعادة حساب الهاشات — لأن السلسلة
       بلا مرساة خارجية. ولا يُكشف **اقتطاع الذيل** (حذف السجلات الأخيرة).

    للرفع إلى حماية حقيقية: مرّر `secret` (أو اضبط `AVAX_DESK_JOURNAL_SECRET`)
    فتصبح الهاشات HMAC-SHA256 بمفتاح خارج الملف، فلا يستطيع من لا يملك المفتاح
    تزوير سلسلة صحيحة — مع نشر رأس السلسلة خارجياً بشكل دوري لمعالجة اقتطاع الذيل.
    """

    def __init__(self, path: str | Path = "journal/desk_journal.jsonl",
                 secret: str | None = None,
                 anchor_path: str | Path | None = None) -> None:
        self.path = Path(path)
        #: مفتاح التوقيع — يُقرأ من البيئة إن لم يُمرَّر صراحةً
        self.secret = secret or os.environ.get("AVAX_DESK_JOURNAL_SECRET")
        #: مرساة خارجية (عدد السجلات + رأس السلسلة). الموضع الافتراضي بجانب
        #: السجل، ويمكن نقله **خارج** مجلد السجل (أو إلى نظام تحكم إصدارات)
        #: عبر `AVAX_DESK_JOURNAL_ANCHOR` — وهذا ما يكشف اقتطاع الذيل فعلاً.
        env_anchor = os.environ.get("AVAX_DESK_JOURNAL_ANCHOR")
        self.anchor_path = Path(anchor_path or env_anchor or
                                (Path(path).parent / "anchor.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: list[JournalRecord] | None = None

    # ------------------------------------------------------------------ #
    def read_anchor(self) -> dict[str, Any]:
        """المرساة المسجّلة: عدد السجلات ورأس السلسلة."""
        if not self.anchor_path.exists():
            return {}
        try:
            return json.loads(self.anchor_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"__corrupt__": True}

    def write_anchor(self) -> dict[str, Any]:
        """
        تحديث المرساة بعد كل إضافة.

        ⚠️ حدّ صريح: إن استطاع المعتدي الكتابة على **المرساة والسجل معاً** فلن
        يُكشف شيء. القيمة الحقيقية تأتي من نقل المرساة خارج نطاق الكتابة
        (متغير البيئة `AVAX_DESK_JOURNAL_ANCHOR` أو نظام تحكم إصدارات) —
        وعندها يكشف اقتطاع الذيل وإعادة الكتابة الكاملة.
        """
        anchor = {
            "records": self.next_sequence() - 1,
            "head_hash": self.last_hash(),
            "updated_at": now_iso(),
            "signed": bool(self.secret),
        }
        try:
            self.anchor_path.parent.mkdir(parents=True, exist_ok=True)
            self.anchor_path.write_text(
                json.dumps(anchor, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return anchor

    def _digest(self, body: str) -> str:
        if self.secret:
            return hmac.new(self.secret.encode("utf-8"), body.encode("utf-8"),
                            hashlib.sha256).hexdigest()
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ #
    def _read_raw(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    # سطر تالف = دليل على تعديل خارجي (المادة 7.2)
                    rows.append({"__corrupt__": line[:200]})
        return rows

    def records(self) -> list[JournalRecord]:
        if self._cache is not None:
            return self._cache
        out: list[JournalRecord] = []
        for row in self._read_raw():
            if "__corrupt__" in row:
                continue
            out.append(JournalRecord(
                record_id=row.get("record_id", ""),
                sequence=int(row.get("sequence", 0)),
                payload=row.get("payload", {}),
                previous_hash=row.get("previous_hash", "GENESIS"),
                timestamp=row.get("timestamp", ""),
                record_hash=row.get("record_hash", ""),
            ))
        self._cache = out
        return out

    # ------------------------------------------------------------------ #
    def last_hash(self) -> str:
        recs = self.records()
        return recs[-1].record_hash if recs else "GENESIS"

    def next_sequence(self) -> int:
        recs = self.records()
        return (recs[-1].sequence + 1) if recs else 1

    # ------------------------------------------------------------------ #
    def append(self, payload: dict[str, Any], kind: str = "desk_cycle") -> JournalRecord:
        """
        يضيف سجلاً جديداً موقّعاً. لا يعدّل أي سجل سابق.

        حماية الكتابة: إن لم ينتهِ الملف بسطر جديد (كتابة مقطوعة سابقة)، نرفض
        الإضافة بدل أن نُلحق سطراً تالفاً — وإلا بدا السجل الجديد موجوداً للعملية
        الحالية وضائعاً على القرص، ثم يُتّهم المستخدم بتعديل خارجي لم يحدث.
        """
        if self.path.exists() and self.path.stat().st_size > 0:
            with self.path.open("rb") as fh:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    raise IOError(
                        "السجل ينتهي بكتابة مقطوعة (بلا سطر جديد). "
                        "عالِج الملف قبل الإضافة — لن نُلحق سطراً تالفاً."
                    )
            self._cache = None   # أعد القراءة من القرص، لا تعتمد على كاش قديم

        record = JournalRecord(
            record_id=f"JRN-{uuid.uuid4().hex[:12].upper()}",
            sequence=self.next_sequence(),
            payload={"kind": kind, **payload},
            previous_hash=self.last_hash(),
            timestamp=now_iso(),
        ).seal(self._digest)

        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())     # ضمان الوصول للقرص قبل إعلان النجاح

        if self._cache is not None:
            self._cache.append(record)
        self.write_anchor()
        return record

    def append_decision(self, decision: DeskDecision, extras: dict[str, Any] | None = None) -> JournalRecord:
        payload = {"decision": decision.to_dict(), **(extras or {})}
        return self.append(payload, kind="desk_cycle")

    # ------------------------------------------------------------------ #
    def verify_chain(self) -> dict[str, Any]:
        """
        التحقق من سلامة السلسلة (المادة 7.2).

        أي تعديل على محتوى سجل يكسر هاشه، وأي حذف يكسر ارتباط التسلسل.
        """
        recs = self.records()
        broken: list[dict[str, Any]] = []
        prev = "GENESIS"
        for i, rec in enumerate(recs):
            if rec.previous_hash != prev:
                broken.append({"sequence": rec.sequence, "issue": "previous_hash لا يطابق السجل السابق"})
            if not rec.verify(self._digest):
                broken.append({"sequence": rec.sequence, "issue": "التوقيع لا يطابق محتوى السجل (تعديل بعد الكتابة)"})
            prev = rec.record_hash
        corrupt_lines = sum(1 for r in self._read_raw() if "__corrupt__" in r)

        # -- المرساة الخارجية: تكشف اقتطاع الذيل وإعادة الكتابة الكاملة --
        anchor = self.read_anchor()
        tail_truncated = False
        rewritten = False
        anchor_check = "لا مرساة مسجّلة بعد"
        if anchor.get("__corrupt__"):
            anchor_check = "⛔ ملف المرساة تالف"
            rewritten = True
        elif anchor:
            a_count, a_head = int(anchor.get("records", -1)), anchor.get("head_hash")
            if a_count > len(recs):
                tail_truncated = True
                anchor_check = (f"⛔ اقتطاع ذيل: المرساة تسجّل {a_count} سجلاً "
                                f"والموجود {len(recs)}")
                broken.append({"sequence": a_count,
                               "issue": f"اقتطاع ذيل — {a_count - len(recs)} سجلاً مفقوداً من النهاية"})
            elif a_count == len(recs) and a_head and a_head != self.last_hash():
                rewritten = True
                anchor_check = "⛔ رأس السلسلة لا يطابق المرساة — إعادة كتابة كاملة"
                broken.append({"sequence": len(recs),
                               "issue": "رأس السلسلة لا يطابق المرساة (إعادة كتابة)"})
            else:
                anchor_check = f"✅ مطابقة المرساة ({a_count} سجلاً)"

        return {
            "records": len(recs),
            "valid": not broken and corrupt_lines == 0,
            "broken": broken,
            "corrupt_lines": corrupt_lines,
            "head_hash": self.last_hash(),
            "signed": bool(self.secret),
            "anchor_path": str(self.anchor_path),
            "anchor_check": anchor_check,
            "tail_truncated": tail_truncated,
            "rewritten": rewritten,
            "limits": self._limits_text(),
        }

    def _limits_text(self) -> str:
        if self.secret:
            base = ("موقّع بـHMAC بمفتاح خارجي — لا يمكن تزوير سلسلة صحيحة بلا المفتاح")
        else:
            base = ("يُكشف: تعديل المحتوى، الحذف من المنتصف، إعادة الترتيب. "
                    "بلا مفتاح: إعادة كتابة كاملة بإعادة حساب الهاشات غير مكشوفة.")
        if self.anchor_path.exists():
            return (base + " والمرساة الخارجية تكشف **اقتطاع الذيل** وإعادة الكتابة — "
                    "بشرط أن تكون المرساة خارج نطاق كتابة المعتدي "
                    "(`AVAX_DESK_JOURNAL_ANCHOR`).")
        return base + " ولا توجد مرساة بعد، فاقتطاع الذيل غير مكشوف."

    # ------------------------------------------------------------------ #
    def decisions(self) -> list[dict[str, Any]]:
        out = []
        for rec in self.records():
            d = rec.payload.get("decision")
            if d:
                out.append(d)
        return out

    def agent_weights(self, min_samples: int = 3) -> dict[str, float]:
        """
        أوزان الوكلاء من سجل التقييم (المادة 7.4).

        الوكيل الذي يتكرر خطؤه 3 مرات على الأقل يُخفَّض وزنه إلى 0.5.
        الوكيل الدقيق يُرفع وزنه تدريجياً (بحد 1.25).
        """
        stats: dict[str, list[bool]] = {}
        for rec in self.records():
            for entry in rec.payload.get("post_mortem", {}).get("agent_scores", []) or []:
                aid = str(entry.get("agent_id", ""))
                if aid:
                    stats.setdefault(aid, []).append(bool(entry.get("correct", False)))

        weights: dict[str, float] = {}
        for aid, results in stats.items():
            if len(results) < min_samples:
                weights[aid] = 1.0
                continue
            hit = sum(results) / len(results)
            if hit < 0.34:
                weights[aid] = 0.50      # خطأ متكرر 3 مرات أو أكثر
            elif hit < 0.45:
                weights[aid] = 0.75
            elif hit > 0.65:
                weights[aid] = 1.25
            else:
                weights[aid] = 1.0
        return weights

    def summary(self) -> dict[str, Any]:
        chain = self.verify_chain()
        decisions = self.decisions()
        actions: dict[str, int] = {}
        for d in decisions:
            actions[d.get("action", "?")] = actions.get(d.get("action", "?"), 0) + 1
        # المادة 9.2 — «الديسك الذي يمتنع 60% من الوقت ديسك ناجح».
        # كان هذا الحكم بلا أي قياس في النظام.
        total = sum(actions.values())
        abstain = actions.get("ABSTAIN", 0) + actions.get("NO_ACTION", 0)
        abstention_rate = (abstain / total) if total else 0.0
        kinds: dict[str, int] = {}
        for d in decisions:
            k = d.get("abstention_kind") or ""
            if k:
                kinds[k] = kinds.get(k, 0) + 1
        return {
            "path": str(self.path),
            "records": chain["records"],
            "chain_valid": chain["valid"],
            "head_hash": chain["head_hash"][:16],
            "decisions": len(decisions),
            "action_distribution": actions,
            "abstention_rate": round(abstention_rate, 4),
            "abstention_kinds": kinds,
            "abstention_note": (
                "المادة 9.2: نسبة الامتناع مرتفعة — الامتناع ليس فشلاً"
                if abstention_rate >= 0.60 else
                "المادة 9.2: نسبة الامتناع منخفضة — راجع جودة الفلترة"
                if total else "لا قرارات مسجّلة بعد"),
        }

    # ------------------------------------------------------------------ #
    def calibration(self) -> dict[str, Any]:
        """
        معايرة الثقة عبر المراجعات البعدية (Brier Score).

        يربط `indicators.brier_score` — الذي كان **معرّفاً وبلا أي مستدعٍ**،
        فالمنهج يعلّم المعايرة ولا قياس واحد في النظام. الآن يُحسَب من
        ثقة كل قرار مسجّل مقابل نتيجته الفعلية المسجّلة في المراجعة البعدية.
        """
        from ..indicators import brier_score

        decisions = {d.get("decision_id"): d for d in self.decisions()}
        pairs: list[tuple[float, int]] = []
        for rec in self.records():
            pm = rec.payload.get("post_mortem") or {}
            did, outcome = pm.get("decision_id"), pm.get("outcome")
            if not did or outcome not in ("correct", "incorrect"):
                continue
            d = decisions.get(did)
            if not d:
                continue
            p = min(0.99, max(0.01, float(d.get("confidence", 50.0)) / 100.0))
            pairs.append((p, 1 if outcome == "correct" else 0))

        bs = brier_score(pairs) if pairs else None
        return {
            "samples": len(pairs),
            "brier_score": None if bs is None else round(bs, 5),
            "reference_random": 0.25,
            "verdict": ("لا تكفي العيّنة للمعايرة" if len(pairs) < 20 else
                        "معايرة أفضل من التخمين العشوائي" if bs < 0.25 else
                        "معايرة أسوأ من التخمين العشوائي — الثقة غير معايَرة"),
            "note": ("Brier = (1/N)Σ(p−o)² — كلما قلّ كان أفضل، و0.25 = تخمين عشوائي"),
        }

    # ------------------------------------------------------------------ #
    def constitution_fingerprint(self, path: str | Path = "CONSTITUTION.md") -> dict[str, Any]:
        """
        بصمة الدستور — المادة 10.1: «لا يُعدَّل هذا الدستور إلا بوثيقة تصحيحية».

        كانت المادة بلا فرض: `constitution_version: "1.0"` نص مكتوب يدوياً في
        `memory.py`، ولا قراءة ولا بصمة لـ`CONSTITUTION.md` في أي ملف.
        الآن تُحسَب البصمة وتُقارَن بآخر بصمة مسجّلة، فأي تعديل صامت يُكشف.
        """
        p = Path(path)
        if not p.exists():
            return {"path": str(path), "sha256": None, "previous": None,
                    "changed": None, "note": "ملف الدستور غير موجود"}
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        previous = None
        for rec in reversed(self.records()):
            fp = rec.payload.get("constitution_fingerprint") or {}
            if fp.get("sha256"):
                previous = fp["sha256"]
                break
        changed = previous is not None and previous != digest
        return {
            "path": str(p),
            "sha256": digest,
            "previous": previous,
            "changed": bool(changed),
            "note": ("⚠️ بصمة الدستور تغيّرت بلا توثيق — المادة 10.1 تطلب وثيقة تصحيحية "
                     "تحمل السبب والدليل والأثر المتوقع"
                     if changed else
                     "الدستور مطابق لآخر بصمة مسجّلة" if previous else
                     "أول بصمة مسجّلة للدستور"),
        }

    # ------------------------------------------------------------------ #
    def write_markdown_summary(self, path: str | Path | None = None) -> Path:
        """
        ملخّص Markdown للسجل — المادة 7.1 تنص على «JSON + ملخص Markdown».

        هذا الملف **مشتق** من السجل وليس سجلاً: يمكن إعادة توليده في أي وقت،
        والسجل الأصل (JSONL) يبقى المصدر الوحيد للحقيقة.
        """
        target = Path(path) if path else self.path.parent / "SUMMARY.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        chain = self.verify_chain()
        decisions = self.decisions()
        weights = self.agent_weights()

        lines = [
            "# ملخّص سجل ديسك أفالانش",
            "",
            "> ملف **مشتق** من `desk_journal.jsonl` — لا يُعدّل يدوياً (المادة 7.2).",
            "",
            f"- عدد السجلات: **{chain['records']}**",
            f"- سلامة السلسلة: **{'✅ سليمة' if chain['valid'] else '⛔ مكسورة'}**",
            f"- رأس السلسلة: `{chain['head_hash'][:32]}…`",
            f"- عدد الدورات بقرار: **{len(decisions)}**",
            "",
            "## توزيع القرارات",
            "",
            "| القرار | العدد |",
            "|---|---|",
        ]
        counts: dict[str, int] = {}
        for d in decisions:
            counts[d.get("action", "?")] = counts.get(d.get("action", "?"), 0) + 1
        for action, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {action} | {count} |")
        if not counts:
            lines.append("| — | 0 |")

        lines += ["", "## أوزان الوكلاء من الأداء التاريخي (المادة 7.4)", "",
                  "| الوكيل | الوزن |", "|---|---|"]
        if weights:
            for aid, w in sorted(weights.items()):
                lines.append(f"| {aid} | {w} |")
        else:
            lines.append("| — | لا سجل مراجعة بعدية كافٍ (الكل 1.0) |")

        lines += ["", "## آخر 20 قراراً", "",
                  "| # | الأصل | القرار | الثقة | الحجم | التاريخ |",
                  "|---|---|---|---|---|---|"]
        for d in decisions[-20:]:
            lines.append(
                f"| {d.get('decision_id', '?')} | {d.get('asset', '?')} | "
                f"{d.get('action', '?')} | {d.get('confidence', 0):.1f} | "
                f"${d.get('size_usd', 0):,.0f} | {str(d.get('timestamp', ''))[:19]} |"
            )
        lines.append("")
        target.write_text("\n".join(lines), encoding="utf-8")
        return target
