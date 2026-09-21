"""
نموذج اللقطة السوقية — المدخل الموحّد لكل الوكلاء.

كل وكيل يقرأ من نفس اللقطة، فلا يمكن أن يختلف وكيلان على "ما هي البيانات".
هذا يمنع أحد أخطر أنواع الخطأ: أن يبني كل وكيل صورة مختلفة عن السوق.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..contracts import now_iso


@dataclass
class MarketSnapshot:
    """لقطة كاملة لحالة AVAX ومنظومتها في لحظة زمنية واحدة."""

    asset: str = "AVAX"
    timestamp: str = field(default_factory=now_iso)

    # -- السعر والحجم ------------------------------------------------------
    closes: list[float] = field(default_factory=list)
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)
    volumes: list[float] = field(default_factory=list)          # حجم بالوحدات
    dollar_volumes: list[float] = field(default_factory=list)   # حجم بالدولار

    # -- دفتر الأوامر (بنية السوق) ----------------------------------------
    best_bid: float = 0.0
    best_ask: float = 0.0
    bid_depth_usd: float = 0.0
    ask_depth_usd: float = 0.0
    venues: int = 1
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0

    # -- المشتقات ----------------------------------------------------------
    funding_rate_8h: float = 0.0        # ككسر عشري، مثال 0.0001 = 0.01%
    open_interest_usd: float = 0.0
    oi_change_24h_pct: float = 0.0
    basis_pct: float = 0.0              # الأساس **السنوي المكافئ** بالنسبة المئوية
    iv_pct: float = 0.0                 # التقلب الضمني السنوي
    long_short_ratio: float = 1.0
    liquidations_24h_usd: float = 0.0

    # -- الأونشين ----------------------------------------------------------
    active_addresses: int = 0
    active_addresses_change_7d_pct: float = 0.0
    exchange_netflow_usd: float = 0.0   # موجب = تدفق إلى المنصات (بيعي)
    staking_ratio_pct: float = 0.0
    validators: int = 0
    tvl_usd: float = 0.0
    tvl_change_7d_pct: float = 0.0
    dex_volume_24h_usd: float = 0.0
    bridge_netflow_7d_usd: float = 0.0  # موجب = صافي دخول للمنظومة
    whale_accumulation: float = 0.0     # -1 توزيع .. +1 تجميع
    fees_24h_usd: float = 0.0

    # -- المعنويات ---------------------------------------------------------
    fear_greed: int = 50                # 0 = خوف شديد، 100 = طمع شديد
    social_volume_change_pct: float = 0.0
    news_sentiment: float = 0.0         # -1 سلبي .. +1 إيجابي
    news_events: list[str] = field(default_factory=list)

    # -- الماكرو -----------------------------------------------------------
    dxy_change_7d_pct: float = 0.0
    real_yield_10y: float = 0.0
    btc_dominance: float = 0.0
    nasdaq_corr_30d: float = 0.0
    btc_corr_30d: float = 0.0

    # -- الأساسيات ---------------------------------------------------------
    market_cap_usd: float = 0.0
    circulating_supply: float = 0.0
    unlock_pct_next_30d: float = 0.0
    revenue_30d_usd: float = 0.0

    # -- مقاييس سوقية محسوبة -----------------------------------------------
    source: str = "synthetic"
    #: حقول لم يُجلَب لها **أي قيمة** من المصدر. الصفر هنا ليس قياساً بل غياب
    #: بيانات — ومعاملته كدليل «طبقة 1» خرق للمادة 3.3 (اختلاق رقم).
    missing_fields: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    @property
    def price(self) -> float:
        return self.closes[-1] if self.closes else 0.0

    @property
    def mid_price(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2.0
        return self.price

    @property
    def volume_24h_usd(self) -> float:
        return self.dollar_volumes[-1] if self.dollar_volumes else 0.0

    @property
    def avg_volume_30d_usd(self) -> float:
        if not self.dollar_volumes:
            return 0.0
        w = self.dollar_volumes[-30:]
        return sum(w) / len(w)

    def series(self, field_name: str) -> list[float]:
        return list(getattr(self, field_name, []) or [])

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # لا نضخّم السجل بالسلاسل الكاملة
        for k in ("closes", "highs", "lows", "volumes", "dollar_volumes"):
            v = d.get(k) or []
            d[k] = {"n": len(v), "last": v[-1] if v else None}
        return d

    def summary(self) -> str:
        return (
            f"{self.asset} @ {self.price:,.4f} | "
            f"حجم24س ${self.volume_24h_usd/1e6:,.1f}M | "
            f"TVL ${self.tvl_usd/1e6:,.1f}M | "
            f"تمويل {self.funding_rate_8h*100:.4f}% | "
            f"خوف/طمع {self.fear_greed}"
        )
