"""
مصدر CoinMarketCap — بيانات سوق حقيقية.

أفضل من الجالب السابق في ثلاث نقاط:
    1. **OHLCV حقيقي** (أعلى/أدنى فعليان) بدل تقديرهما من فرق الإغلاق.
    2. **هيمنة BTC والسياق الكلي** من `/global-metrics` — كانت حقلين غائبين.
    3. لا حدود `days <= 365` المزعجة في CoinGecko، ومعدّل طلبات أوضح.

القاعدة الدستورية الحاكمة: أي مصدر يفشل **يُعلن** ولا يُختلق بديل (المادة 3.3)،
وكل حقل لم يوفّره المصدر يُدرَج في `missing_fields` فلا يُستشهد به.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from ..contracts import now_iso
from .models import MarketSnapshot
from .synthetic import SyntheticFeed

BASE = "https://pro-api.coinmarketcap.com"
AVAX_CMC_ID = 5805


class CMCEntitlementsError(RuntimeError):
    """المفتاح صالح لكن الخطة لا تشمل نقطة النهاية المطلوبة."""


class CoinMarketCapFeed:
    """جالب بيانات من CoinMarketCap."""

    def __init__(self, api_key: str | None = None, symbol: str = "AVAX",
                 cmc_id: int = AVAX_CMC_ID, days: int = 365,
                 timeout: float = 25.0, fallback_seed: int = 11) -> None:
        self.api_key = api_key or os.environ.get("CMC_API_KEY", "")
        self.symbol = symbol
        self.cmc_id = cmc_id
        self.days = days
        self.timeout = timeout
        self.fallback_seed = fallback_seed
        self.degraded: list[str] = []
        self.entitlements_blocked: list[str] = []

    # ------------------------------------------------------------------ #
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key:
            raise RuntimeError("لا مفتاح CMC — اضبط CMC_API_KEY في .env")
        query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        url = f"{BASE}{path}" + (f"?{query}" if query else "")
        req = urllib.request.Request(url, headers={
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",
            "User-Agent": "avax-desk/1.0 (research; analysis-only)",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:220]
            # 1006/1008 = خطة لا تشمل هذه النقطة
            if e.code in (401, 403) or '"error_code":1006' in body or '"error_code":1008' in body:
                self.entitlements_blocked.append(f"{path}: HTTP {e.code} — {body}")
                raise CMCEntitlementsError(f"{path}: {body}") from e
            raise RuntimeError(f"{path}: HTTP {e.code} — {body}") from e
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"{path}: {type(e).__name__}: {e}") from e

    # ------------------------------------------------------------------ #
    def fetch(self) -> MarketSnapshot:
        """يبني لقطة من CMC، ويتراجع للاصطناعي عند الفشل الكامل — مُعلناً."""
        try:
            return self._from_cmc()
        except (RuntimeError, CMCEntitlementsError) as exc:
            self.degraded.append(f"cmc: {exc}")
            snap = SyntheticFeed(seed=self.fallback_seed, days=self.days).generate()
            snap.meta["fallback_reason"] = str(exc)[:400]
            snap.meta["degraded_sources"] = list(self.degraded)
            snap.meta["entitlements_blocked"] = list(self.entitlements_blocked)
            return snap

    # ------------------------------------------------------------------ #
    def _from_cmc(self) -> MarketSnapshot:
        snap = MarketSnapshot(asset=self.symbol, source="live")
        missing: list[str] = []

        # ── 1) الاقتباس الحالي ───────────────────────────────────────────
        q = self._get("/v1/cryptocurrency/quotes/latest",
                      {"symbol": self.symbol, "convert": "USD"})
        data = (q.get("data") or {}).get(self.symbol) or {}
        if not data:
            raise RuntimeError("استجابة quotes/latest بلا بيانات")
        usd = (data.get("quote") or {}).get("USD") or {}
        price = float(usd.get("price") or 0.0)
        snap.best_bid = price * 0.9997
        snap.best_ask = price * 1.0003
        snap.market_cap_usd = float(usd.get("market_cap") or 0.0)
        supply = float(data.get("circulating_supply") or 0.0)
        snap.circulating_supply = supply

        # ── عمق دفتر الأوامر: **تقدير معلن** لا قياس ─────────────────────
        # CMC لا يوفّر L2، وBinance محجوب جغرافياً في هذه البيئة. بلا عمق
        # يصبح `liquidity_depth_limit = 0` فيُرفض كل مركز — وهو سلوك صحيح
        # لكنه يُجمّد الديسك. الحل: تقدير من الحجم اليومي (0.2%) **موسوم
        # صراحةً** كتقدير، ويُخفَّض دليله من طبقة 2 (سوق) إلى 3 (مشتق).
        vol24 = float(usd.get("volume_24h") or 0.0)
        depth_estimate = vol24 * 0.002
        snap.bid_depth_usd = depth_estimate * 0.5
        snap.ask_depth_usd = depth_estimate * 0.5
        snap.meta["depth_estimated"] = True
        snap.meta["depth_estimate_basis"] = (
            "0.2% من الحجم اليومي المُبلَّغ من CMC — لا قياس L2. "
            "دليله طبقة 3 (مشتق) لا طبقة 2 (سوق)."
        )
        if vol24:
            snap.dollar_volumes.append(vol24)
        self._q = usd  # للاستخدام لاحقاً في الحقول المشتقة

        # ── 2) السياق الكلي (هيمنة BTC) ──────────────────────────────────
        try:
            g = self._get("/v1/global-metrics/quotes/latest", {"convert": "USD"})
            gd = g.get("data") or {}
            snap.btc_dominance = float(gd.get("btc_dominance") or 0.0)
            if not snap.btc_dominance:
                missing.append("btc_dominance")
        except (RuntimeError, CMCEntitlementsError) as exc:
            self.degraded.append(f"global-metrics: {exc}")
            missing.append("btc_dominance")

        # ── 3) OHLCV حقيقي ──────────────────────────────────────────────
        # CMC يحجب OHLCV التاريخي على الطبقة المجانية (خطأ 1006). لا نتوقف:
        # نطلب السلسلة من CoinGecko (مجاني ويعمل) — **مصدر هجين معلن**، ولا
        # نختلق سلسلة ولا نتراجع للاصطناعي بلا داعٍ.
        try:
            self._ohlcv_from_cmc(snap)
            snap.meta["ohlcv_provider"] = "coinmarketcap"
        except (RuntimeError, CMCEntitlementsError) as exc:
            self.degraded.append(f"cmc_ohlcv: {str(exc)[:200]}")
            try:
                self._ohlcv_from_coingecko(snap)
                snap.meta["ohlcv_provider"] = "coingecko (احتياطي — CMC محجوب بالخطة)"
                snap.meta["ohlcv_fallback_reason"] = str(exc)[:220]
            except Exception as exc2:  # noqa: BLE001
                self.degraded.append(f"coingecko_ohlcv: {exc2}")
                raise RuntimeError(
                    "لا مصدر متاح لسلسلة الأسعار (CMC محجوب وCoinGecko فشل) — "
                    "لا يمكن بناء تحليل فني بلا سلسلة"
                ) from exc2

        # ── 4) تفاصيل الرمز (العرض الأقصى، الوسوم) ──────────────────────
        try:
            m = self._get("/v1/cryptocurrency/info", {"symbol": self.symbol})
            info = (m.get("data") or {}).get(self.symbol) or {}
            snap.meta["cmc_info"] = {
                "name": info.get("name"),
                "category": info.get("category"),
                "tags": (info.get("tags") or [])[:6],
                "date_added": info.get("date_added"),
            }
            if info.get("max_supply"):
                snap.meta["max_supply"] = float(info["max_supply"])
            if info.get("total_supply"):
                snap.meta["total_supply"] = float(info["total_supply"])
        except (RuntimeError, CMCEntitlementsError) as exc:
            self.degraded.append(f"info: {exc}")

        # ── 5) الحقول التي لا يوفّرها CMC — تُعلن صريحاً ─────────────────
        missing += [
            "exchange_netflow_usd", "active_addresses", "staking_ratio_pct",
            "validators", "bridge_netflow_7d_usd", "whale_accumulation",
            "dex_volume_24h_usd", "tvl_usd", "tvl_change_7d_pct", "fees_24h_usd",
            "revenue_30d_usd", "iv_pct", "long_short_ratio", "liquidations_24h_usd",
            "oi_change_24h_pct", "unlock_pct_next_30d", "dxy_change_7d_pct",
            "real_yield_10y", "nasdaq_corr_30d", "btc_corr_30d",
            "social_volume_change_pct", "news_sentiment",
        ]
        # التمويل والفائدة المفتوحة من Binance (اختياري)
        self._augment_binance(snap, missing)
        # الخوف والطمع (اختياري)
        self._augment_fear_greed(snap, missing)

        snap.missing_fields = sorted(set(missing))
        snap.meta.update({
            "provider": "coinmarketcap",
            "fetched_at": now_iso(),
            "degraded_sources": list(self.degraded),
            "missing_fields": snap.missing_fields,
            "quote_snapshot": {
                k: self._q.get(k) for k in
                ("percent_change_1h", "percent_change_24h", "percent_change_7d",
                 "percent_change_30d", "percent_change_90d", "volume_24h",
                 "volume_change_24h")
            },
        })
        return snap

    # ------------------------------------------------------------------ #
    def _ohlcv_from_cmc(self, snap: MarketSnapshot) -> None:
        """سلسلة OHLCV من CMC — تتطلب طبقة مدفوعة."""
        o = self._get("/v2/cryptocurrency/ohlcv/historical", {
            "id": self.cmc_id, "convert": "USD",
            "time_start": self._iso_days_ago(self.days),
            "time_end": self._iso_days_ago(0),
            "interval": "daily", "count": min(self.days, 500),
        })
        quotes = (((o.get("data") or {}).get("quotes")) or [])
        if len(quotes) < 60:
            raise RuntimeError(f"نقاط OHLCV غير كافية: {len(quotes)}")
        for row in quotes:
            u = (row.get("quote") or {}).get("USD") or {}
            snap.closes.append(float(u.get("close") or 0.0))
            snap.highs.append(float(u.get("high") or 0.0))
            snap.lows.append(float(u.get("low") or 0.0))
            snap.volumes.append(float(u.get("volume") or 0.0))
            snap.dollar_volumes.append(float(u.get("volume") or 0.0))
        snap.timestamp = quotes[-1].get("time") or now_iso()

    def _ohlcv_from_coingecko(self, snap: MarketSnapshot) -> None:
        """سلسلة الأسعار من CoinGecko — احتياطي مجاني معلن."""
        days = min(self.days, 365)   # الطبقة المجانية ترفض > 365 بـHTTP 401
        url = ("https://api.coingecko.com/api/v3/coins/avalanche-2/market_chart"
               f"?vs_currency=usd&days={days}&interval=daily")
        req = urllib.request.Request(url, headers={
            "User-Agent": "avax-desk/1.0 (research; analysis-only)",
            "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            raw = json.loads(r.read().decode("utf-8"))
        prices = raw.get("prices") or []
        totals = raw.get("total_volumes") or []
        if len(prices) < 60:
            raise RuntimeError(f"نقاط CoinGecko غير كافية: {len(prices)}")
        snap.closes = [float(p[1]) for p in prices]
        snap.dollar_volumes = [float(v[1]) for v in totals][: len(snap.closes)]
        # لا OHLC كامل في هذه النقطة من CoinGecko — أعلى/أدنى مُقدَّران من العائد
        highs, lows = [], []
        for i, c in enumerate(snap.closes):
            prev = snap.closes[i - 1] if i else c
            rng = abs(c - prev) / prev if prev else 0.02
            highs.append(c * (1 + rng * 0.6))
            lows.append(c * (1 - rng * 0.6))
        snap.highs, snap.lows = highs, lows
        n = min(len(snap.closes), len(snap.dollar_volumes))
        snap.closes, snap.highs = snap.closes[-n:], snap.highs[-n:]
        snap.lows, snap.dollar_volumes = snap.lows[-n:], snap.dollar_volumes[-n:]
        snap.volumes = [v / max(1e-9, p) for v, p in zip(snap.dollar_volumes, snap.closes)]
        self.degraded.append(
            "coingecko: أعلى/أدنى اليوم **مُقدَّران** من فرق الإغلاق (لا OHLC كامل) — "
            "أدلة الحجم/المدى من هذا المصدر أضعف من OHLC حقيقي"
        )

    # ------------------------------------------------------------------ #
    def _augment_binance(self, snap: MarketSnapshot, missing: list[str]) -> None:
        """التمويل والفائدة المفتوحة — اختياري تماماً."""
        for name, url, apply_fn in (
            ("binance_funding",
             "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=AVAXUSDT",
             lambda d: setattr(snap, "funding_rate_8h", float(d.get("lastFundingRate", 0.0)))),
            ("binance_oi",
             "https://fapi.binance.com/fapi/v1/openInterest?symbol=AVAXUSDT",
             lambda d: setattr(snap, "open_interest_usd",
                               float(d.get("openInterest", 0.0)) * snap.price)),
        ):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "avax-desk/1.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    apply_fn(json.loads(r.read().decode("utf-8")))
                if name in missing:
                    missing.remove(name)
            except Exception as exc:  # noqa: BLE001
                self.degraded.append(f"{name}: {type(exc).__name__}")

    def _augment_fear_greed(self, snap: MarketSnapshot, missing: list[str]) -> None:
        try:
            req = urllib.request.Request("https://api.alternative.me/fng/?limit=1",
                                         headers={"User-Agent": "avax-desk/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
            snap.fear_greed = int(d["data"][0]["value"])
        except Exception as exc:  # noqa: BLE001
            self.degraded.append(f"fear_greed: {type(exc).__name__}")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _iso_days_ago(days: int) -> str:
        from datetime import timedelta
        return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
