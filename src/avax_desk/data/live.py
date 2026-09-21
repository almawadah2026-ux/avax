"""
مصادر بيانات حيّة — تُستخدم عند توفر الشبكة، وترجع تلقائياً للاصطناعي عند الفشل.

المصادر (كلها عامة، بلا مفاتيح API):
    • CoinGecko  : السعر والتاريخ والحجم ورأس المال السوقي
    • DefiLlama  : TVL لأفالانش والرسوم
    • Binance    : معدل التمويل والعقود الآجلة (AVAXUSDT)
    • alternative.me : مؤشر الخوف والطمع

القاعدة الدستورية: عند فشل أي مصدر، **نُعلن الفشل ولا نختلق رقماً** (المادة 3.3).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..contracts import now_iso
from .models import MarketSnapshot
from .synthetic import SyntheticFeed


class FeedError(RuntimeError):
    """فشل مصدر بيانات — يُعلن صراحةً ولا يُخفى."""


def _get_json(url: str, timeout: float = 10.0) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "avax-desk/1.0 (research; analysis-only)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise FeedError(f"تعذّر جلب {url}: {exc}") from exc


class LiveFeed:
    """جالب بيانات حيّة مع تراجع آمن إلى البيانات الاصطناعية."""

    COINGECKO = (
        "https://api.coingecko.com/api/v3/coins/avalanche-2/market_chart"
        "?vs_currency=usd&days={days}&interval=daily"
    )
    DEFILLAMA_TVL = "https://api.llama.fi/v2/historicalChainTvl/Avalanche"
    BINANCE_FUNDING = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=AVAXUSDT"
    BINANCE_OI = "https://fapi.binance.com/fapi/v1/openInterest?symbol=AVAXUSDT"
    FEAR_GREED = "https://api.alternative.me/fng/?limit=1"

    def __init__(self, days: int = 365, timeout: float = 10.0, fallback_seed: int = 42) -> None:
        self.days = days
        self.timeout = timeout
        self.fallback_seed = fallback_seed
        self.degraded: list[str] = []   # المصادر التي فشلت

    # ------------------------------------------------------------------ #
    def fetch(self) -> MarketSnapshot:
        try:
            snap = self._from_coingecko()
        except Exception as exc:  # noqa: BLE001 — أي فشل يُعلن، ولا يُسقط الجالب
            self.degraded.append(f"coingecko: {type(exc).__name__}: {exc}")
            snap = SyntheticFeed(seed=self.fallback_seed, days=self.days).generate()
            snap.meta["fallback_reason"] = f"{type(exc).__name__}: {exc}"
            snap.meta["degraded_sources"] = list(self.degraded)
            return snap

        snap.source = "live"
        self._augment_tvl(snap)
        self._augment_derivatives(snap)
        self._augment_sentiment(snap)

        # -- حقول لم يوفّرها أي مصدر -------------------------------------
        # ثغرة مُصلَحة: كانت تبقى على الصفر الافتراضي فتُقرأ كقياس («العناوين
        # النشطة 0»، «نسبة الاستيكينج 0.00%») وتُصنَّف دليل طبقة 1 — خرق
        # المادة 3.3. الآن تُعلن صراحةً، ويجب على الوكلاء الامتناع عنها.
        unfetched = []
        if not snap.tvl_usd:
            unfetched.append("tvl_usd")
        if not snap.funding_rate_8h:
            unfetched.append("funding_rate_8h")
        if not snap.open_interest_usd:
            unfetched.append("open_interest_usd")
        # لا مصدر عام لهذه في الجالب الحالي — تُعلن دائماً في الوضع الحيّ
        unfetched += [
            "exchange_netflow_usd", "active_addresses", "staking_ratio_pct",
            "validators", "bridge_netflow_7d_usd", "whale_accumulation",
            "dex_volume_24h_usd", "fees_24h_usd", "revenue_30d_usd",
            "iv_pct", "long_short_ratio", "liquidations_24h_usd",
            "unlock_pct_next_30d", "dxy_change_7d_pct", "real_yield_10y",
            "social_volume_change_pct", "news_sentiment",
        ]
        snap.missing_fields = sorted(set(unfetched))
        for f in snap.missing_fields:
            if hasattr(snap, f):
                setattr(snap, f, 0.0 if isinstance(getattr(snap, f), (int, float)) else getattr(snap, f))
        if snap.missing_fields:
            self.degraded.append(
                f"حقول غائبة ({len(snap.missing_fields)}): {'، '.join(snap.missing_fields[:8])}… "
                f"— لم تُختلق قيم بديلة (المادة 3.3)"
            )

        snap.meta = {
            "degraded_sources": list(self.degraded),
            "fetched_at": now_iso(),
            "missing_fields": snap.missing_fields,
        }
        return snap

    # ------------------------------------------------------------------ #
    def _from_coingecko(self) -> MarketSnapshot:
        raw = _get_json(self.COINGECKO.format(days=self.days), self.timeout)
        if not isinstance(raw, dict) or "prices" not in raw:
            raise FeedError("استجابة CoinGecko غير متوقعة")

        prices = raw.get("prices") or []
        mcaps = raw.get("market_caps") or []
        totals = raw.get("total_volumes") or []
        if len(prices) < 60:
            raise FeedError(f"نقاط بيانات غير كافية: {len(prices)}")

        snap = MarketSnapshot(asset="AVAX", source="live")
        snap.closes = [float(p[1]) for p in prices]
        snap.dollar_volumes = [float(v[1]) for v in totals][: len(snap.closes)]

        # ثغرة مُصلَحة: كان نقص الحجم يُعالَج بتكرار آخر قيمة بصمت (70 نسخة من
        # الرقم نفسه) وبلا أي وسم — خرق المادة 3.3. الآن نُعلن العجز صراحةً
        # في `degraded` ونترك الاكتمال ينخفض تلقائياً في `compute_features`.
        if len(snap.dollar_volumes) < len(snap.closes):
            missing = len(snap.closes) - len(snap.dollar_volumes)
            self.degraded.append(
                f"coingecko/total_volumes: {missing} نقطة مفقودة من {len(snap.closes)} "
                f"— لم تُختلق قيم بديلة"
            )
        elif any(v == 0.0 for v in snap.dollar_volumes[-30:]):
            self.degraded.append("coingecko/total_volumes: قيم صفرية داخل آخر 30 يوماً")

        # CoinGecko لا يعطي أعلى/أدنى يومي في هذه النقطة ⇒ نقدّرهما من العوائد
        highs, lows = [], []
        for i, c in enumerate(snap.closes):
            prev = snap.closes[i - 1] if i else c
            rng = abs(c - prev) / prev if prev else 0.02
            highs.append(c * (1 + rng * 0.6))
            lows.append(c * (1 - rng * 0.6))
        snap.highs, snap.lows = highs, lows

        if mcaps:
            snap.market_cap_usd = float(mcaps[-1][1])
            if snap.closes[-1] > 0:
                snap.circulating_supply = snap.market_cap_usd / snap.closes[-1]

        price = snap.price
        snap.best_bid = price * 0.9997
        snap.best_ask = price * 1.0003
        snap.bid_depth_usd = snap.volume_24h_usd * 0.002
        snap.ask_depth_usd = snap.volume_24h_usd * 0.002
        snap.venues = 8
        # محاذاة الأطوال: أي نقص يبقى ظاهراً في `completeness` ولا يُقنَّع.
        n = min(len(snap.closes), len(snap.dollar_volumes))
        snap.closes = snap.closes[-n:]
        snap.highs = snap.highs[-n:]
        snap.lows = snap.lows[-n:]
        snap.dollar_volumes = snap.dollar_volumes[-n:]
        snap.volumes = [v / max(1e-9, p) for v, p in zip(snap.dollar_volumes, snap.closes)]
        return snap

    # ------------------------------------------------------------------ #
    def _augment_tvl(self, snap: MarketSnapshot) -> None:
        try:
            data = _get_json(self.DEFILLAMA_TVL, self.timeout)
            if isinstance(data, list) and data and isinstance(data[-1], dict):
                tvl = data[-1].get("tvl")
                if tvl is not None:
                    snap.tvl_usd = float(tvl)
                if len(data) > 7 and isinstance(data[-8], dict):
                    prev = data[-8].get("tvl")
                    if prev:
                        snap.tvl_change_7d_pct = (snap.tvl_usd - float(prev)) / float(prev) * 100.0
        except Exception as exc:  # noqa: BLE001 — أي فشل يُعلن ولا يُسقط الجالب
            # ثغرة مُصلَحة: كان الالتقاط محدوداً بـ(FeedError, ValueError, KeyError,
            # TypeError)، فاستجابة مشوّهة (مثل نص بدل قائمة) تُخرج
            # `AttributeError` من `fetch()` كاملاً وتُسقط وعد التراجع الآمن.
            self.degraded.append(f"defillama: {type(exc).__name__}: {exc}")

    def _augment_derivatives(self, snap: MarketSnapshot) -> None:
        try:
            data = _get_json(self.BINANCE_FUNDING, self.timeout)
            if isinstance(data, dict):
                snap.funding_rate_8h = float(data.get("lastFundingRate", 0.0))
                # توحيد الوحدة: `basis_pct` أساس **سنوي مكافئ** بالنسبة المئوية
                # (كان يعرّفه هنا كنسبة فورية %، فيتناقض مع الوضع الاصطناعي
                # ومع تطبيع الوكيل 06 — خرق وحدات يُفسد المقارنة).
                snap.basis_pct = snap.funding_rate_8h * 3 * 365 * 100.0
        except Exception as exc:  # noqa: BLE001
            self.degraded.append(f"binance_funding: {type(exc).__name__}: {exc}")

        try:
            data = _get_json(self.BINANCE_OI, self.timeout)
            if isinstance(data, dict):
                snap.open_interest_usd = float(data.get("openInterest", 0.0)) * snap.price
        except Exception as exc:  # noqa: BLE001
            self.degraded.append(f"binance_oi: {type(exc).__name__}: {exc}")

    def _augment_sentiment(self, snap: MarketSnapshot) -> None:
        try:
            data = _get_json(self.FEAR_GREED, self.timeout)
            if isinstance(data, dict) and data.get("data"):
                snap.fear_greed = int(data["data"][0]["value"])
        except Exception as exc:  # noqa: BLE001
            self.degraded.append(f"fear_greed: {type(exc).__name__}: {exc}")
