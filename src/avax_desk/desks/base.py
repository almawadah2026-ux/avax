"""
البنية الأساسية للوكلاء + حساب الميزات المشتركة.

مبدأ حاكم: **كل الوكلاء يقرأون من نفس الميزات المحسوبة مرة واحدة**.
هذا يمنع أن يحسب وكيلان نفس المؤشر بطريقتين مختلفتين فيتناقضان بلا سبب حقيقي.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .. import indicators as ind
from ..config import DeskConfig
from ..contracts import (
    AgentOpinion,
    Authority,
    Direction,
    Evidence,
    Layer,
    Strength,
)
from ..data.models import MarketSnapshot
from ..law import LawEngine


# ==========================================================================
# الميزات المشتركة
# ==========================================================================

def compute_features(s: MarketSnapshot) -> dict[str, Any]:
    """يحسب كل المؤشرات مرة واحدة من اللقطة السوقية."""
    c, h, lo, v = s.closes, s.highs, s.lows, s.volumes
    f: dict[str, Any] = {}

    f["price"] = s.price
    f["returns"] = ind.log_returns(c)
    f["ret_1d_pct"] = (c[-1] / c[-2] - 1) * 100.0 if len(c) > 1 else 0.0
    f["ret_7d_pct"] = (c[-1] / c[-8] - 1) * 100.0 if len(c) > 8 else 0.0
    f["ret_30d_pct"] = (c[-1] / c[-31] - 1) * 100.0 if len(c) > 31 else 0.0
    f["ret_90d_pct"] = (c[-1] / c[-91] - 1) * 100.0 if len(c) > 91 else 0.0

    # -- الاتجاه والمؤشرات الفنية --------------------------------------
    f["ema20"] = ind.ema(c, 20)
    f["ema50"] = ind.ema(c, 50)
    f["ema200"] = ind.ema(c, 200)
    f["rsi14"] = ind.rsi(c, 14)
    f["macd"] = ind.macd(c)
    f["bb"] = ind.bollinger(c, 20, 2.0)
    f["atr14"] = ind.atr(h, lo, c, 14)
    f["atr_pct"] = ind.safe_div(f["atr14"], s.price) * 100.0
    f["adx14"] = ind.adx(h, lo, c, 14)
    f["vwap20"] = ind.vwap(h, lo, c, v, 20)
    f["sr"] = ind.support_resistance(h, lo, 60)
    f["slope20"] = ind.slope(c, 20)
    f["price_vs_ema200_pct"] = ind.safe_div(s.price - f["ema200"], f["ema200"]) * 100.0

    # -- التقلب ---------------------------------------------------------
    f["vol_30d_ann_pct"] = ind.realized_vol(c, 30)
    f["vol_90d_ann_pct"] = ind.realized_vol(c, 90)
    f["ewma_vol_pct"] = ind.ewma_vol(c)
    f["garch"] = ind.garch_11(c)
    vol_hist = [
        ind.realized_vol(c[: i + 1], 30)
        for i in range(max(31, len(c) - 120), len(c), 10)
    ]
    f["vol_history"] = vol_hist
    f["vol_regime"] = ind.volatility_regime(f["vol_30d_ann_pct"], vol_hist)

    # -- كمي -------------------------------------------------------------
    f["zscore30"] = ind.zscore(c, 30)
    f["zscore90"] = ind.zscore(c, 90)
    f["hurst"] = ind.hurst_exponent(c)
    f["half_life_days"] = ind.half_life_ou(c)
    f["momentum"] = ind.momentum_score(c)
    f["sharpe_90d"] = ind.annualized_sharpe(ind.log_returns(c)[-90:])
    f["sortino_90d"] = ind.sortino_ratio(ind.log_returns(c)[-90:])
    f["max_dd"] = ind.max_drawdown(c)
    f["ulcer"] = ind.ulcer_index(c)

    # -- بنية السوق -------------------------------------------------------
    f["spread_bps"] = ind.relative_spread_bps(s.best_bid, s.best_ask)
    f["obi"] = ind.order_book_imbalance(s.bid_depth_usd, s.ask_depth_usd)
    f["depth_usd"] = s.bid_depth_usd + s.ask_depth_usd
    f["depth_vs_volume_pct"] = ind.safe_div(f["depth_usd"], s.volume_24h_usd) * 100.0
    f["amihud"] = ind.amihud_illiquidity(f["returns"][-90:], s.dollar_volumes[-90:])
    f["vpin_proxy"] = ind.depth_imbalance_pressure(
        s.bid_depth_usd, s.ask_depth_usd, max(1e-9, f["depth_usd"])
    )
    f["kyle_lambda"] = ind.kyle_lambda(
        [c[i] - c[i - 1] for i in range(max(1, len(c) - 60), len(c))],
        [s.dollar_volumes[i] for i in range(max(0, len(s.dollar_volumes) - 60), len(s.dollar_volumes))],
    )

    # -- مخاطر ------------------------------------------------------------
    f["var"] = ind.value_at_risk(f["returns"], 0.95)
    f["monte_carlo"] = ind.monte_carlo_terminal(c, days=30, paths=600, seed=7)

    # -- اكتمال البيانات: يفحص **الصلاحية** لا مجرد عدم الفراغ ---------------
    # ثغرة مُصلَحة: كان يفحص `if getattr(s, r)` فقط، فسلسلة حجوم كلها أصفار
    # أو تاريخ من نقطتين يُعطي اكتمالاً 100%، فلا يعمل فرع «بيانات ناقصة ⇒
    # تخفيض 50%» (المادة 9.3) إطلاقاً.
    checks: list[bool] = []

    def _valid(seq: list[float], minimum: int = 60) -> bool:
        if not seq or len(seq) < minimum:
            return False
        nonzero = sum(1 for x in seq if x)
        return nonzero >= max(2, len(seq) // 2)     # أغلبية غير صفرية

    checks.append(_valid(s.closes, 200))
    checks.append(_valid(s.highs, 200))
    checks.append(_valid(s.lows, 200))
    checks.append(_valid(s.dollar_volumes, 60))
    checks.append(_valid(s.volumes, 60))
    checks.append(bool(s.best_bid and s.best_ask and s.best_ask > s.best_bid))
    checks.append(bool(s.bid_depth_usd and s.ask_depth_usd))
    # تناسق الأطوال — كان `len(closes)=201` مع `len(volumes)=200` يُزيح كل
    # الميزات المرتبطة بالحجم بشمعة واحدة.
    checks.append(len(s.closes) == len(s.volumes) == len(s.dollar_volumes))
    # حقول غائبة من المصدر تُخفّض الاكتمال: الصفر الافتراضي ليس قياساً (المادة 3.3)
    if s.missing_fields:
        missing_ratio = min(1.0, len(s.missing_fields) / 20.0)
        checks.append(missing_ratio < 0.5)
        f["missing_fields"] = list(s.missing_fields)
        f["missing_fields_count"] = len(s.missing_fields)
    f["completeness"] = sum(checks) / len(checks)
    f["length_aligned"] = len(s.closes) == len(s.volumes) == len(s.dollar_volumes)
    return f


# ==========================================================================
# سياق الوكيل
# ==========================================================================

@dataclass
class AgentContext:
    """كل ما يحتاجه الوكيل ليعمل — لا شيء غير هذا."""

    snapshot: MarketSnapshot
    config: DeskConfig
    law: LawEngine
    features: dict[str, Any] = field(default_factory=dict)
    opinions: dict[str, AgentOpinion] = field(default_factory=dict)
    #: قناة التنسيق بين الطبقات (المقترح، حكم المخاطر، خطة التنفيذ...)
    shared: dict[str, Any] = field(default_factory=dict)

    def add(self, op: AgentOpinion) -> AgentOpinion:
        self.opinions[op.agent_id] = op
        return op

    def opinions_of_layer(self, layer: Layer) -> list[AgentOpinion]:
        from ..law import ROSTER_BY_ID
        return [
            o for aid, o in self.opinions.items()
            if (spec := ROSTER_BY_ID.get(aid)) and spec.layer == layer
        ]

    def knowledge_opinions(self) -> list[AgentOpinion]:
        return self.opinions_of_layer(Layer.KNOWLEDGE)


# ==========================================================================
# أدوات بناء الرأي
# ==========================================================================

def direction_from_score(score: float, dead_zone: float = 0.08) -> str:
    """تحويل درجة في [−1, +1] إلى اتجاه. منطقة ميتة تمنع الإشارات الوهمية."""
    if score > dead_zone:
        return Direction.BULLISH.value
    if score < -dead_zone:
        return Direction.BEARISH.value
    return Direction.NEUTRAL.value


def confidence_from(score: float, direction: str, completeness: float = 1.0,
                    cap: float = 88.0) -> float:
    """
    الثقة مشتقة من قوة الإشارة واكتمال البيانات.

    المعايرة: نستخدم دالة جذر تربيعي لا خطية، لأن الإشارات المركّبة نادراً ما
    تقترب من ±1 (كل وكيل يمزج مكوّنات اتجاهية وعكسية)، فالخطية تُنتج ثقات
    منخفضة دائماً وتجعل حد الدخول (65) غير قابل للوصول — وهو خلل معماري.

        |الدرجة| = 0.10 ⇒ ثقة ≈ 59
        |الدرجة| = 0.25 ⇒ ثقة ≈ 68
        |الدرجة| = 0.50 ⇒ ثقة ≈ 77

    سقف 88 مقصود: لا وكيل يعلن ثقة شبه مطلقة — المادة 8.8 تمنع لغة اليقين.
    """
    mag = min(1.0, abs(score))
    if direction == Direction.NEUTRAL.value:
        base = 34.0 + mag * 20.0          # الحياد ثقة منخفضة بطبيعته
    else:
        base = 45.0 + 45.0 * math.sqrt(mag)
    return round(ind.clamp(base * (0.6 + 0.4 * completeness), 0.0, cap), 1)


class BaseAgent:
    """الأساس المشترك لكل الوكلاء."""

    id: str = "00"
    name_ar: str = "وكيل"
    name_en: str = "Agent"
    layer: Layer = Layer.KNOWLEDGE
    authority: Authority = Authority.ADVISORY
    domain: str = ""
    horizon: str = "أيام"
    file: str = ""

    # ------------------------------------------------------------------ #
    def run(self, ctx: AgentContext) -> AgentOpinion:
        """
        تنفيذ الوكيل.

        ملاحظة دستورية: الوكيل **لا يفحص نفسه**. الفحص من سلطة وكيل الالتزام (13)
        حتى لا يكون الخصم حكماً في قضيته — المادة 1.1 (فصل السلطات).
        """
        op = self.analyze(ctx)
        ctx.add(op)
        return op

    def analyze(self, ctx: AgentContext) -> AgentOpinion:  # pragma: no cover
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    def ev(self, ctx: AgentContext, claim: str, source: str, kind: str,
           strength: str = Strength.MEDIUM.value, value: float | None = None) -> Evidence:
        """
        بناء دليل موقّع بالطابع الزمني للقطة — المادة 2.5.

        **حارس المنشأ (المادة 3.1/3.3):** البيانات الاصطناعية **لا يجوز** أن
        تُصنَّف «أونشين مباشر» (طبقة 1) أو «سوق متعدد المنصات» (طبقة 2).
        كان وكيل الأونشين يثبّت المصدر `avalanche-c-chain` نصاً، فيمنح بيانات
        محاكاة **طبقة 1** — وهي أخطر جريمة في الدستور (الاختلاق، المادة 3.3)
        وتُسقط هرمية الأدلة التي يبني عليها وكيلا التحقق والالتزام.

        الحل: التصنيف يُشتق من **منشأ اللقطة** لا من نيّة الوكيل.
        """
        if ctx.snapshot.source != "live" and kind in ("onchain", "market"):
            claim = f"[محاكاة — ليست بيانات شبكة حقيقية] {claim}"
            source = f"synthetic-sim/{source}"
            kind = "derived"
            strength = Strength.LOW.value if strength == Strength.HIGH.value else strength
        return Evidence(
            claim=claim,
            source=source,
            timestamp=ctx.snapshot.timestamp,
            kind=kind,
            strength=strength,
            value=value,
        )

    def make(
        self,
        ctx: AgentContext,
        score: float,
        thesis: str,
        evidence: list[Evidence],
        invalidation: str,
        dissent: str,
        metrics: dict[str, Any] | None = None,
        horizon: str | None = None,
        dead_zone: float = 0.08,
        notes: list[str] | None = None,
    ) -> AgentOpinion:
        """يبني رأياً مكتمل الحقول الستة (المادة 2.1)."""
        direction = direction_from_score(score, dead_zone)
        completeness = float(ctx.features.get("completeness", 1.0))
        confidence = confidence_from(score, direction, completeness)
        return AgentOpinion(
            agent_id=self.id,
            agent_name=self.name_ar,
            thesis=thesis,
            evidence=evidence,
            confidence=confidence,
            horizon=horizon or self.horizon,
            invalidation=invalidation,
            dissent=dissent,
            direction=direction,
            metrics={**(metrics or {}), "raw_score": round(score, 4)},
            notes=list(notes or []),
        )

    def source_tag(self, ctx: AgentContext) -> str:
        """وسم المصدر — بيانات حيّة أم اصطناعية (المادة 3.1)."""
        return ("live:avalanche-ecosystem" if ctx.snapshot.source == "live"
                else "synthetic:avax-sim")


def make_opinion(agent: BaseAgent, ctx: AgentContext, **kwargs: Any) -> AgentOpinion:
    return agent.make(ctx, **kwargs)
