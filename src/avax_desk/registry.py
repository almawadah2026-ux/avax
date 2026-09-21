"""
سجل الوكلاء — تحميل ملفات التعريف من مجلد `agents/`.

الهدف: ربط **الشخصية المكتوبة** (ملف Markdown) بـ **التنفيذ البرمجي** (صنف Python).
هذا يسمح باستخدام نفس ملفات التعريف مع أي نموذج لغوي كبير (LLM) لاحقاً،
بلا إعادة كتابة — الملفات هي المصدر الوحيد للحقيقة المعرفية.

والأهم: يكشف أي وكيل مذكور في الدستور بلا ملف تعريف، أو ملف بلا وكيل مقابل.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .law import AGENT_ROSTER, AgentSpecRef


@dataclass
class AgentSpec:
    """ملف تعريف وكيل محمّل من القرص."""

    id: str
    name_ar: str
    name_en: str
    layer: str
    authority: str
    domain: str
    path: Path
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    sections: list[str] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def line_count(self) -> int:
        return len(self.body.splitlines()) if self.body else 0

    def section(self, title_fragment: str) -> str:
        """استخراج قسم بالعنوان (بحث جزئي)."""
        current: list[str] = []
        capturing = False
        for line in self.body.splitlines():
            if line.startswith("## "):
                if capturing:
                    break
                capturing = title_fragment in line
                continue
            if capturing:
                current.append(line)
        return "\n".join(current).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name_ar": self.name_ar, "name_en": self.name_en,
            "layer": self.layer, "authority": self.authority, "domain": self.domain,
            "file": str(self.path), "exists": self.exists, "lines": self.line_count,
            "sections": self.sections,
        }


# --------------------------------------------------------------------------
# محلّل Frontmatter مبسّط (بلا اعتماد على مكتبات خارجية)
# --------------------------------------------------------------------------

def _parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(p) for p in inner.split(",")]
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """يفصل كتلة `---` العلوية عن متن الملف."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text

    meta: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = _parse_scalar(value)

    body = "\n".join(lines[end + 1:])
    return meta, body


# --------------------------------------------------------------------------
# التحميل
# --------------------------------------------------------------------------

def default_agents_dir(root: str | Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    return Path(root) / "agents"


def load_specs(agents_dir: str | Path | None = None) -> dict[str, AgentSpec]:
    """يحمّل كل ملفات `agents/*.md` (عدا القالب) ويفهرسلها بالمعرّف."""
    directory = Path(agents_dir) if agents_dir else default_agents_dir()
    specs: dict[str, AgentSpec] = {}
    if not directory.exists():
        return specs

    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = parse_frontmatter(text)
        aid = str(meta.get("id", "")).strip()
        if not aid:
            continue
        sections = [
            ln.strip("# ").strip()
            for ln in body.splitlines() if ln.startswith("## ")
        ]
        specs[aid] = AgentSpec(
            id=aid,
            name_ar=str(meta.get("name_ar", "")),
            name_en=str(meta.get("name_en", "")),
            layer=str(meta.get("layer", "")),
            authority=str(meta.get("authority", "")),
            domain=str(meta.get("domain", "")),
            path=path,
            frontmatter=meta,
            body=body,
            sections=sections,
        )
    return specs


def audit_roster(agents_dir: str | Path | None = None) -> dict[str, Any]:
    """
    تدقيق الاتساق الكامل: كل حقل في الكشف الرسمي يُقارَن بترويسة الملف.

    ⚠️ **تصحيح موثّق (تدقيق):** كانت الدالة تفحص `layer` و`authority` فقط،
    فأعلنت «✅ متسق» رغم **19 عدم تطابق** في `name_ar`/`name_en`، ولم تفحص
    مسار الملف ولا `outputs`، و`extra` لم يدخل في `ok`. أداة تدقيق تبالغ في
    الاتساق أسوأ من غياب الأداة لأنها تمنح ثقة زائفة.
    """
    specs = load_specs(agents_dir)
    missing: list[dict[str, str]] = []
    mismatched: list[dict[str, str]] = []
    domain_notes: list[dict[str, str]] = []

    for ref in AGENT_ROSTER:
        spec = specs.get(ref.id)
        if spec is None:
            missing.append({"id": ref.id, "name": ref.name_ar, "expected_file": ref.file})
            continue

        # الحقول **التعاقدية** — أي اختلاف فيها خرق مفروض
        checks = (
            ("layer", ref.layer.value, str(spec.frontmatter.get("layer", ""))),
            ("authority", ref.authority.value, str(spec.frontmatter.get("authority", ""))),
            ("name_ar", ref.name_ar, str(spec.frontmatter.get("name_ar", ""))),
            ("name_en", ref.name_en, str(spec.frontmatter.get("name_en", ""))),
        )
        for field, expected, actual in checks:
            if actual != expected:
                mismatched.append({
                    "id": ref.id, "field": field,
                    "roster": expected, "file": actual,
                })

        # `domain`: الكشف يحمل **سلَغاً داخلياً** والملف يحمل وصفاً بشرياً أوسع.
        # وظيفتان مختلفتان لا تعارض ⇒ تُسجَّل للمعلومة لا كمخالفة.
        file_domain = str(spec.frontmatter.get("domain", ""))
        if file_domain and file_domain != ref.domain:
            domain_notes.append({"id": ref.id, "slug": ref.domain, "file": file_domain})

        # مسار الملف: الكشف يحدّد `agents/NN-*.md` — يجب أن يطابق الملف المحمّل
        expected_name = Path(ref.file).name
        if spec.path.name != expected_name:
            mismatched.append({
                "id": ref.id, "field": "file",
                "roster": expected_name, "file": spec.path.name,
            })

        # `outputs` يجب أن يكون قائمة غير فارغة
        outputs = spec.frontmatter.get("outputs", [])
        if not outputs:
            mismatched.append({"id": ref.id, "field": "outputs",
                               "roster": "غير فارغة", "file": "غائبة"})

    known = {r.id for r in AGENT_ROSTER}
    extra = [aid for aid in specs if aid not in known]

    return {
        "expected": len(AGENT_ROSTER),
        "loaded": len(specs),
        "missing": missing,
        "mismatched": mismatched,
        "domain_notes": domain_notes,
        "extra": extra,
        # `extra` تُدخل في الحكم: ملف بلا كشف = وكيل غير مخوّل يعمل بلا صلاحية
        "ok": not missing and not mismatched and not extra,
        "fields_checked": ["id", "layer", "authority", "name_ar", "name_en",
                           "file", "outputs"],
        "specs": {aid: spec.to_dict() for aid, spec in specs.items()},
    }


def consistency_report(agents_dir: str | Path | None = None) -> str:
    """
    تقرير نصي مقروء يجمع **ثلاثة** تدقيقات:
        1. تطابق ملفات `agents/*.md` مع الكشف الرسمي
        2. تطابق **أصناف التنفيذ** مع الكشف (لا وكيل في الكشف بلا صنف)
        3. تقرير ربط السمات بالكشف (هل انحرفت نسخة محلية؟)
    """
    audit = audit_roster(agents_dir)
    try:
        from .desks._binding import audit_implementations
        impl = audit_implementations()
    except Exception as exc:  # noqa: BLE001
        impl = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    lines = [
        "═" * 66,
        "  تدقيق اتساق ديسك أفالانش — ثلاثة محاور",
        "═" * 66,
        f"  1) ملفات الوكلاء: {audit['expected']} متوقع | {audit['loaded']} محمّل | "
        f"{'✅ متسق' if audit['ok'] else '⚠️ يحتاج مراجعة'}",
        f"  2) أصناف التنفيذ: {impl.get('implemented_classes', '?')} صنف | "
        f"{'✅ مكتمل' if impl.get('ok') else '⚠️ ناقص'}",
    ]
    if audit["missing"]:
        lines.append("\n  ملفات مفقودة:")
        for m in audit["missing"]:
            lines.append(f"    ⛔ [{m['id']}] {m['name']} ← {m['expected_file']}")
    if audit["mismatched"]:
        lines.append("\n  تعارض في الحقول التعاقدية:")
        for m in audit["mismatched"]:
            lines.append(f"    ⚠️ [{m['id']}] {m['field']}: الكشف={m['roster']} الملف={m['file']}")
    if audit["extra"]:
        lines.append(f"\n  ملفات زائدة بلا كشف: {', '.join(audit['extra'])}")
    if impl.get("missing_implementations"):
        lines.append("\n  وكلاء في الكشف بلا صنف تنفيذي:")
        for m in impl["missing_implementations"]:
            lines.append(f"    ⛔ [{m['id']}] {m['name']} (طبقة {m['expected_layer']})")
    if impl.get("wrong_layer"):
        lines.append("\n  أصناف في طبقة مخالفة للكشف:")
        for m in impl["wrong_layer"]:
            lines.append(f"    ⚠️ [{m['id']}] الكشف={m['roster_layer']} التنفيذ={m['implemented_in']}")
    if impl.get("extra_implementations"):
        lines.append(f"\n  أصناف بلا كشف: {', '.join(impl['extra_implementations'])}")
    if impl.get("error"):
        lines.append(f"\n  ⚠️ تعذّر تدقيق التنفيذ: {impl['error']}")

    if audit.get("domain_notes"):
        lines.append(f"\n  ℹ️ {len(audit['domain_notes'])} ملفاً يصف `domain` بنص بشري أوسع "
                     f"من السلَغ الداخلي في الكشف — وظيفتان مختلفتان لا تعارض")
    lines.append(f"\n  الحقول المفحوصة في الملفات: {', '.join(audit['fields_checked'])}")
    lines.append("═" * 66)
    return "\n".join(lines)
