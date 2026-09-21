"""
تصدير لقطة كاملة يقرأها الوكلاء الذكيون.

السبب: في تشغيل سابق امتنع 7 من 8 وكلاء لأن اللقطة المختصرة افتقدت حقولاً
يفرضها **عقد المدخلات** في ملفات تعريفهم (سلسلة OHLCV، عمق دفتر الأوامر،
سلسلة الخيارات، نسبة Long/Short، جدول Unlock…). هذا السكربت يبني لقطة
تُستوفى فيها تلك المدخلات، ويصدّرها JSON ليقرأها الوكلاء بأنفسهم.

⚠️ المصدر اصطناعي حتمي وموسوم — المادة 3.1/3.3 تمنع تقديمه كبيانات شبكة.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from avax_desk import indicators as ind          # noqa: E402
from avax_desk.data.synthetic import SyntheticFeed  # noqa: E402
from avax_desk.desks.base import compute_features   # noqa: E402

SEED = 11
SCENARIO = "bull"
BARS = 366          # كل الشمعات — حتى تكون كل مؤشرات اللقطة قابلة لإعادة الإنتاج
LEVELS = 10         # مستويات دفتر الأوامر لكل جهة
LIVE = "--live" in sys.argv

if LIVE:
    from avax_desk.data.live import LiveFeed
    # CoinGecko (الطبقة المجانية) يرفض `days > 365` بـHTTP 401 لا برسالة واضحة.
    feed = LiveFeed(days=365, timeout=20.0, fallback_seed=SEED)
    snap = feed.fetch()
    if snap.source != "live":
        print(f"⛔ تعذّر الوضع الحيّ: {str(snap.meta.get('fallback_reason'))[:160]}")
        for d in feed.degraded[:3]:
            print(f"   - {d[:150]}")
    else:
        print(f"🌐 بيانات حيّة: {len(snap.closes)} نقطة | تدهور={len(feed.degraded)}")
else:
    snap = SyntheticFeed(seed=SEED, days=365, scenario=SCENARIO).generate()

f = compute_features(snap)

end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
n = len(snap.closes)

# ── سلسلة OHLCV: الشمعات الأخيرة مع طوابع زمنية ──────────────────────────
bars = []
for i in range(n - BARS, n):
    ts = end - timedelta(days=(n - 1 - i))
    bars.append({
        "t": ts.isoformat(timespec="seconds"),
        "o": round(snap.closes[i - 1] if i else snap.closes[i], 4),
        "h": round(snap.highs[i], 4),
        "l": round(snap.lows[i], 4),
        "c": round(snap.closes[i], 4),
        "v": round(snap.volumes[i], 2),
        "dv": round(snap.dollar_volumes[i], 2),
    })

# ── دفتر أوامر بعشرة مستويات — **متوافق مع العمق المُعلن** ──────────────
# ثغرة كشفها الوكلاء: كانت الأحجام تُحسب بـ`depth/(mid·k·0.55)` فمجموع
# المستويات = 5.327× العمق المُعلن (14.24M مقابل 2.67M). الآن الأوزان
# w_k = 1/k تُطبَّع لتساوي مجموعها العمق المُعلن بالضبط.
mid = snap.mid_price
tick = mid * 0.0005
weights = [1.0 / k for k in range(1, LEVELS + 1)]
wsum = sum(weights)
bids, asks = [], []
for k in range(1, LEVELS + 1):
    size_bid = (snap.bid_depth_usd * (1.0 / k) / wsum) / (mid - k * tick)
    size_ask = (snap.ask_depth_usd * (1.0 / k) / wsum) / (mid + k * tick)
    bids.append({"price": round(mid - k * tick, 4), "size_avax": round(size_bid, 4)})
    asks.append({"price": round(mid + k * tick, 4), "size_avax": round(size_ask, 4)})

# ── مشتقات: يُضاف ما لا يوجد في النموذج بقيم مُعلنة كمشتقة ───────────────
rv_daily = f["vol_30d_ann_pct"] / 100.0 / (365 ** 0.5)
iv_annual = snap.iv_pct        # من اللقطة لا من الميزات
oi = snap.open_interest_usd
adv = snap.volume_24h_usd

payload = {
    "_meta": {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asset": "AVAX",
        "source": snap.source,
        "seed": None if LIVE else SEED,
        "scenario": None if LIVE else SCENARIO,
        "missing_fields": list(snap.missing_fields or []),
        "warning": ("بيانات سوق حيّة من مصادر عامة (CoinGecko للأسعار، DefiLlama لـTVL، "
                    "Binance للتمويل والفائدة المفتوحة، alternative.me للخوف والطمع). "
                    "الحقول في `missing_fields` **لم يوفّرها أي مصدر** — الصفر فيها يعني "
                    "«لا بيانات» لا «قياس صفري»، ويُمنع الاستشهاد بها (المادة 3.3)."
                    if LIVE else
                    "بيانات اصطناعية حتمية — ليست شبكة حقيقية ولا سوقاً حقيقياً "
                    "(المادتان 3.1 و3.3). طبقات الأدلة 1–2 غير مستحقة لها."),
        "bars_provided": len(bars),
    },

    # 1) سلسلة OHLCV اليومية
    "ohlcv_daily": bars,

    # 2) دفتر الأوامر (L2)
    "orderbook": {
        "timestamp": snap.timestamp,
        "mid_price": round(mid, 4),
        "best_bid": round(snap.best_bid, 4),
        "best_ask": round(snap.best_ask, 4),
        "spread_bps": round(f["spread_bps"], 3),
        "bid_depth_usd": round(snap.bid_depth_usd, 2),
        "ask_depth_usd": round(snap.ask_depth_usd, 2),
        "total_depth_usd": round(f["depth_usd"], 2),
        "order_book_imbalance": round(f["obi"], 4),
        "venues_count": snap.venues,
        "maker_fee_bps": snap.maker_fee_bps,
        "taker_fee_bps": snap.taker_fee_bps,
        "bids": bids,
        "asks": asks,
    },

    # 3) المشتقات
    "derivatives": {
        "funding_rate_8h": snap.funding_rate_8h,
        "funding_annualized_pct": round(snap.funding_rate_8h * 3 * 365 * 100, 3),
        "basis_annualized_pct": round(snap.basis_pct, 3),
        "open_interest_usd": round(oi, 2),
        "oi_change_24h_pct": snap.oi_change_24h_pct,
        "oi_to_adv_ratio": round(oi / adv, 4) if adv else None,
        "long_short_ratio": snap.long_short_ratio,
        "liquidations_24h_usd": round(snap.liquidations_24h_usd, 2),
        "implied_vol_annual_pct": round(iv_annual, 2),
        "realized_vol_30d_annual_pct": round(f["vol_30d_ann_pct"], 2),
        "variance_risk_premium": round(iv_annual - f["vol_30d_ann_pct"], 2),
        "note": ("سلسلة خيارات AVAX غير مُقدَّمة؛ التقلب الضمني تقديري "
                 "(مستوى 3 لا مستوى 2)."),
    },

    # 4) الأونشين
    "onchain": {
        "active_addresses": snap.active_addresses,
        "active_addresses_change_7d_pct": snap.active_addresses_change_7d_pct,
        "exchange_netflow_usd": round(snap.exchange_netflow_usd, 2),
        "exchange_netflow_pct_of_adv": round(snap.exchange_netflow_usd / adv * 100, 3) if adv else None,
        "staking_ratio_pct": snap.staking_ratio_pct,
        "validators": snap.validators,
        "tvl_usd": round(snap.tvl_usd, 2),
        "tvl_change_7d_pct": snap.tvl_change_7d_pct,
        "dex_volume_24h_usd": round(snap.dex_volume_24h_usd, 2),
        "bridge_netflow_7d_usd": round(snap.bridge_netflow_7d_usd, 2),
        "whale_accumulation_score": snap.whale_accumulation,
        "fees_24h_usd": round(snap.fees_24h_usd, 2),
        "note": "وسوم المنصات وP-Chain ΔStake غير مُقدَّمة.",
    },

    # 5) الماكرو
    "macro": {
        "dxy_change_7d_pct": snap.dxy_change_7d_pct,
        "real_yield_10y_pct": snap.real_yield_10y,
        "btc_dominance_pct": snap.btc_dominance,
        "nasdaq_corr_30d": snap.nasdaq_corr_30d,
        "btc_corr_30d": snap.btc_corr_30d,
    },

    # 6) الأساسيات والتوكنوميكس
    "fundamentals": {
        "market_cap_usd": round(snap.market_cap_usd, 2),
        "circulating_supply": snap.circulating_supply,
        "unlock_pct_next_30d": snap.unlock_pct_next_30d,
        "revenue_30d_usd": round(snap.revenue_30d_usd, 2),
        "pf_ratio": round(snap.market_cap_usd / max(1.0, snap.revenue_30d_usd * 12), 1),
    },

    # 7) المعنويات
    "sentiment": {
        "fear_greed": snap.fear_greed,
        "social_volume_change_pct": snap.social_volume_change_pct,
        "news_sentiment": snap.news_sentiment,
        "news_events": snap.news_events,
        "note": "Social Volume وWeighted Sentiment وCoordination Score غير مُقدَّمة.",
    },

    # 8) المؤشرات المحسوبة مسبقاً (حتى لا يعيد كل وكيل الحساب)
    "computed_indicators": {
        "price": round(f["price"], 4),
        "ret_1d_pct": round(f["ret_1d_pct"], 3),
        "ret_7d_pct": round(f["ret_7d_pct"], 3),
        "ret_30d_pct": round(f["ret_30d_pct"], 3),
        "ret_90d_pct": round(f["ret_90d_pct"], 3),
        "ema20": round(f["ema20"], 4), "ema50": round(f["ema50"], 4),
        "ema200": round(f["ema200"], 4),
        "rsi14": round(f["rsi14"], 2),
        "macd": {k: round(v, 4) for k, v in f["macd"].items()},
        "bollinger": {k: round(v, 4) for k, v in f["bb"].items()},
        "atr14": round(f["atr14"], 4),
        "atr_pct_of_price": round(f["atr_pct"], 3),
        "adx14": round(f["adx14"], 2),
        "vwap20": round(f["vwap20"], 4),
        "slope20_pct_per_bar": round(f["slope20"], 4),
        # الدعم/المقاومة محسوبان على **نفس الشمعات المُصدَّرة** لا على قمة
        # آخر شمعة — كان resistance_60d يساوي أعلى قمة في الملف (إحصاء
        # نفس-الشمعة) وهو ما رصده الوكلاء.
        "support_provided_bars": round(min(b["l"] for b in bars), 4),
        "resistance_provided_bars": round(max(b["h"] for b in bars), 4),
        "support_60d_internal": round(f["sr"]["support"], 4),
        "resistance_60d_internal": round(f["sr"]["resistance"], 4),
        "vol_30d_annual_pct": round(f["vol_30d_ann_pct"], 2),
        "vol_90d_annual_pct": round(f["vol_90d_ann_pct"], 2),
        "ewma_vol_annual_pct": round(f["ewma_vol_pct"], 2),
        "garch11_annual_pct": round(f["garch"]["sigma_annual_pct"], 2),
        "vol_regime": f["vol_regime"],
        "zscore_30d": round(f["zscore30"], 3),
        "zscore_90d": round(f["zscore90"], 3),
        "hurst_exponent": round(f["hurst"], 4),
        "half_life_days": (None if f["half_life_days"] == float("inf")
                           else round(f["half_life_days"], 2)),
        "momentum": {k: round(v, 3) for k, v in f["momentum"].items()},
        "sharpe_90d": round(f["sharpe_90d"], 3),
        "sortino_90d": round(f["sortino_90d"], 3),
        "max_drawdown_pct": round(f["max_dd"]["max_dd_pct"], 3),
        "ulcer_index": round(f["ulcer"], 3),
        "amihud_illiquidity": f["amihud"],
        "kyle_lambda": f["kyle_lambda"],
        "var95_historical_pct": round(f["var"]["var_hist_pct"], 3),
        "cvar95_pct": round(f["cvar"]["cvar_pct"] if "cvar" in f else f["var"]["cvar_pct"], 3),
        "monte_carlo_30d": {k: round(v, 4) if isinstance(v, float) else v
                            for k, v in f["monte_carlo"].items()},
        "liquidity_completeness": f["completeness"],
    },
}

# ── فحص اتساق ذاتي: يمنع تسليم لقطة متناقضة للوكلاء ─────────────────────
# الوكلاء في تشغيل حقيقي رصدوا تعارضاً بين ملخص مكتوب يدوياً وهذا الملف في
# 9 من 11 حقلاً. هذا الفحص يمنع تكرار ذلك: أي تعارض داخلي يُعلن هنا.
bid_sum = sum(b["price"] * b["size_avax"] for b in bids)
ask_sum = sum(a["price"] * a["size_avax"] for a in asks)
sym = sum(1 for b in bars if abs((b["h"] - b["c"]) - (b["c"] - b["l"])) < 1e-6)
checks = {
    "orderbook_bid_sum_usd": round(bid_sum, 2),
    "orderbook_ask_sum_usd": round(ask_sum, 2),
    "orderbook_declared_bid_usd": round(snap.bid_depth_usd, 2),
    "orderbook_declared_ask_usd": round(snap.ask_depth_usd, 2),
    "orderbook_consistent": abs(bid_sum - snap.bid_depth_usd) <= max(1.0, snap.bid_depth_usd * 1e-4),
    "candles_total": len(bars),
    "candles_perfectly_symmetric": sym,
    "candles_symmetric_ratio": round(sym / len(bars), 4),
    "indicators_computable_from_provided_bars": len(bars) >= 200,
    "note": ("كل مؤشر في computed_indicators قابل لإعادة الحساب من ohlcv_daily "
             "المُصدَّرة هنا. أي ملخص يُمرَّر للوكلاء يجب أن يُشتق من هذا الملف "
             "لا من الذاكرة — وإلا فهو خرق للمادة 2.5 (تعارض مصدرين)."),
}
payload["_consistency"] = checks

validated = (checks["orderbook_consistent"]
             and checks["indicators_computable_from_provided_bars"])
payload["_meta"]["self_validated"] = bool(validated)
if not validated:
    payload["_meta"]["validation_warnings"] = [
        k for k, v in checks.items()
        if isinstance(v, bool) and v is False
    ]

out = ROOT / "data" / "snapshot_full.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

# ── الملخص المُشتق: يمنع تعارض المصدرين الذي كشفه الوكلاء ────────────────
# أي ملخص يُمرَّر للوكلاء يجب أن يُشتق **من هذا الملف** لا من الذاكرة.
ci = payload["computed_indicators"]
summary = {
    "asset": "AVAX",
    "as_of": payload["_meta"]["generated_at"],
    "source": payload["_meta"]["source"],
    "price": ci["price"],
    "ret_1d_pct": ci["ret_1d_pct"],
    "ret_7d_pct": ci["ret_7d_pct"],
    "ret_30d_pct": ci["ret_30d_pct"],
    "ret_90d_pct": ci["ret_90d_pct"],
    "rsi14": ci["rsi14"],
    "adx14": ci["adx14"],
    "atr_pct_of_price": ci["atr_pct_of_price"],
    "ema20": ci["ema20"],
    "ema50": ci["ema50"],
    "ema200": ci["ema200"],
    "hurst_exponent": ci["hurst_exponent"],
    "zscore_30d": ci["zscore_30d"],
    "vol_regime": ci["vol_regime"],
    "realized_vol_30d_pct": ci["vol_30d_annual_pct"],
    "best_bid": payload["orderbook"]["best_bid"],
    "best_ask": payload["orderbook"]["best_ask"],
    "spread_bps": payload["orderbook"]["spread_bps"],
    "order_book_imbalance": payload["orderbook"]["order_book_imbalance"],
    "funding_rate_8h": payload["derivatives"]["funding_rate_8h"],
    "open_interest_usd": payload["derivatives"]["open_interest_usd"],
    "tvl_usd": payload["onchain"]["tvl_usd"],
    "tvl_change_7d_pct": payload["onchain"]["tvl_change_7d_pct"],
    "exchange_netflow_usd": payload["onchain"]["exchange_netflow_usd"],
    "active_addresses": payload["onchain"]["active_addresses"],
    "staking_ratio_pct": payload["onchain"]["staking_ratio_pct"],
    "dex_volume_24h_usd": payload["onchain"]["dex_volume_24h_usd"],
    "fear_greed": payload["sentiment"]["fear_greed"],
    "btc_dominance_pct": payload["macro"]["btc_dominance_pct"],
    "btc_corr_30d": payload["macro"]["btc_corr_30d"],
    "market_cap_usd": payload["fundamentals"]["market_cap_usd"],
    "circulating_supply": payload["fundamentals"]["circulating_supply"],
    "support_provided_bars": ci["support_provided_bars"],
    "resistance_provided_bars": ci["resistance_provided_bars"],
    "notes_for_agents": ("البيانات الكاملة في data/snapshot_full.json — اقرأه بأداة read. "
                         "هذا الملخص مُشتق آلياً من الملف، فأي تعارض بينه وبين الملف مستحيل بالبناء."),
}
sum_path = ROOT / "data" / "snapshot_summary.json"
sum_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✅ ملخص مُشتق: {sum_path}")

print(f"✅ كُتبت اللقطة الكاملة: {out}")
print(f"   شمعات OHLCV: {len(bars)} | مستويات دفتر: {len(bids)}×2")
print(f"   السعر: {payload['computed_indicators']['price']} | "
      f"RSI: {payload['computed_indicators']['rsi14']} | "
      f"ADX: {payload['computed_indicators']['adx14']} | "
      f"Hurst: {payload['computed_indicators']['hurst_exponent']}")
print(f"   اتساق الدفتر: {checks['orderbook_consistent']} "
      f"(bid {bid_sum:,.0f} مقابل معلن {snap.bid_depth_usd:,.0f})")
print(f"   شمعات متماثلة تماماً: {sym}/{len(bars)} "
      f"({checks['candles_symmetric_ratio']*100:.1f}% — يجب أن تكون أقل بكثير من 100%)")
print(f"   المشاهدات القابلة لإعادة الحساب: {checks['indicators_computable_from_provided_bars']}")
print(f"   الحجم: {out.stat().st_size/1024:.1f} KB")
