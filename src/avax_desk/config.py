"""إعدادات الديسك والحدود الملزمة — ترجمة المادة 5 من الدستور إلى قيم قابلة للفرض."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Limits:
    """
    الحدود الملزمة — CONSTITUTION.md المادة 5.3.

    تحذير: تغيير أي قيمة هنا يعدّلاً للمادة 5.3 ويتطلب وثيقة تصحيحية
    (CONSTITUTION.md المادة 10.1). هذا الكائن مقصود أن يكون frozen.
    """

    #: أقصى خسارة يومية مقبولة، نسبة مئوية من رأس المال
    max_daily_loss_pct: float = 2.0

    #: أقصى تراجع من القمة، نسبة مئوية
    max_drawdown_pct: float = 15.0

    #: أقصى حجم لمركز واحد، نسبة مئوية من المحفظة
    max_position_pct: float = 10.0

    #: أقصى تركّز في قطاع واحد، نسبة مئوية
    max_sector_concentration_pct: float = 25.0

    #: الحد الأدنى للثقة لقبول قرار دخول
    min_confidence: float = 65.0

    #: أقصى نسبة من **عمق دفتر الأوامر** يجوز أن يمثلها المركز (قيود السيولة اللحظية)
    max_depth_participation_pct: float = 10.0

    #: أقصى نسبة مشاركة من حجم السوق اليومي
    max_market_participation_pct: float = 5.0

    #: أقصى جزء من Kelly الكامل يُسمح باستخدامه
    max_kelly_fraction: float = 0.5

    #: عمر البيانات بعد الذي تُوسم STALE (بالساعات) — المادة 3.4
    stale_hours: float = 24.0

    #: نسبة تخفيض الثقة للبيانات القديمة — المادة 3.4
    stale_confidence_penalty: float = 0.30

    #: عتبة كشف الإجماع المريب — المادة 4.4
    groupthink_threshold: float = 0.95

    #: أقصى خسارة مقبولة لكل صفقة، نسبة مئوية من رأس المال
    max_risk_per_trade_pct: float = 1.0

    #: أدنى حجم مركز قابل للتنفيذ فعلياً (دولار).
    #: القيمة الرمزية التي تُقرَّب إلى صفر ليست مركزاً — والسماح بها يُنتج
    #: «قرار اتجاهي بحجم 0$» وهو تناقض منطقي يجب رفضه (المادة 5.2).
    min_position_usd: float = 100.0

    #: مضاعف ATR لوقف الخسارة
    atr_stop_multiple: float = 2.0

    def as_dict(self) -> dict[str, float]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class DeskConfig:
    """إعدادات تشغيل الديسك."""

    #: الأصل محل التحليل
    asset: str = "AVAX"

    #: رأس المال الافتراضي بالدولار
    capital_usd: float = 1_000_000.0

    #: المعدل الخالي من المخاطر السنوي (لحساب Sharpe)
    risk_free_rate: float = 0.04

    #: بذرة العشوائية — تضمن تكرارية النتائج في الوضع الاصطناعي
    seed: int = 42

    #: سيناريو السوق للبيانات الاصطناعية (auto | bull | bear | chop | crisis | recovery)
    scenario: str = "auto"

    #: عدد نقاط البيانات التاريخية
    lookback_days: int = 365

    #: هل نستخدم بيانات حيّة من الشبكة؟ (خطأ = بيانات اصطناعية حتمية)
    live_data: bool = False

    #: مهلة طلبات الشبكة بالثواني
    network_timeout: float = 10.0

    #: حدّ الخسارة اليومية المتراكمة الحالي (يُحدَّث من السجل)
    daily_pnl_pct: float = 0.0

    #: التراجع الحالي من القمة
    current_drawdown_pct: float = 0.0

    #: التعرّض الحالي للقطاع الذي ينتمي إليه الأصل (لحد التركّز — المادة 5.3)
    current_sector_exposure_pct: float = 0.0

    #: اسم القطاع (layer-1 افتراضياً لأفالانش)
    sector: str = "layer-1"

    #: المراكز المفتوحة حالياً — [{notional_usd, sector}] لمنع الالتفاف بتقسيم المراكز (المادة 8.7)
    open_positions: list[dict] = field(default_factory=list)

    #: مسار الدستور — يُبصَم للتأكد أنه لم يُعدّل بلا وثيقة تصحيحية (المادة 10.1)
    constitution_path: str = "CONSTITUTION.md"

    #: هل نُجبر على الامتناع؟ (يُفعَّل عند الأحمر)
    halted: bool = False

    #: سبب الإيقاف ووقته وملاحظة رفعه — للتدقيق (المادتان 5.4 و7)
    halt_reason: str = ""
    halted_at: str = ""
    resume_note: str = ""

    limits: Limits = field(default_factory=Limits)
    verbose: bool = True

    def halt(self, reason: str) -> None:
        """
        إيقاف كامل فوري — المادة 9.3 مستوى أحمر، والمادة 5.4 («لبقية اليوم»).

        الإيقاف **يبقى** حتى يُرفع صراحةً بـ`resume()` — لأنه لا يجوز أن يُرفع
        تلقائياً بمجرد تحسّن رقم، وإلا لكان الإيقاف شكلياً.
        """
        self.halted = True
        self.halt_reason = reason
        self.halted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.verbose and print(f"  [🔴 إيقاف كامل] {reason}")

    def resume(self, operator_note: str = "") -> None:
        """
        رفع الإيقاف — فعل بشري صريح مطلوب.

        ملاحظة دستورية: المادة 5.4 تنص على الإيقاف «لبقية اليوم»، والرفع يحتاج
        قراراً واعياً لا مجرد تغيّر رقم. لذلك لا يوجد رفع تلقائي في أي مسار.
        """
        self.halted = False
        self.resume_note = operator_note or "رفع يدوي بلا ملاحظة"
        self.verbose and print(f"  [🟢 رُفع الإيقاف] {self.resume_note}")
