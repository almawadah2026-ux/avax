"""
أداة تحقّق ميكانيكية للوكيل 01 — بنية السوق.

الغرض: تحويل كل ادعاء ميكانيكي في رأي الوكيل 01 إلى رقم قابل لإعادة الإنتاج،
لا إلى تقدير بالنظر. السكربت **لا يصدر رأياً** ولا توصية (المادة 0.2 و1.2).

ما يفحصه:
  A) إعادة توليد مسار السعر من البذرة 11 ومطابقته لملف اللقطة (إثبات المصدر).
  B) إعادة بناء سلّم الدفتر من صيغة المولّد ومقارنته بالمستويات المُصدَّرة.
  C) إعادة بناء سبريد/عمق/OBI من صيغ المولّد ومقارنتها بالحقول المعلنة.
  D) بطارية مقاييس التقلب (Close-Close / Parkinson / EWMA / ATR) وكشف التناقض.
  E) منحنى الانزلاق المُستخرج من السلّم (مع وسم أنه أثر مولّد لا قياس سوق).
  F) مقارنة ثلاث طرق داخلية لتقدير الكلفة + نِسَب العمق إلى الحجم وOI.

التشغيل:  python tools/verify_01_microstructure.py
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from avax_desk import indicators as ind  # noqa: E402
from avax_desk.data.synthetic import SyntheticFeed  # noqa: E402

SNAP = ROOT / "data" / "snapshot_full.json"
data = json.loads(SNAP.read_text(encoding="utf-8"))
bars = data["ohlcv_daily"]
ob = data["orderbook"]
ci = data["computed_indicators"]
der = data["derivatives"]
onch = data["onchain"]

mid = ob["mid_price"]
dv_last = bars[-1]["dv"]
AS_OF = data["_meta"]["generated_at"]

print("=" * 78)
print("A) PROVENANCE — regenerate path from seed 11 and compare to snapshot")
print("=" * 78)
snap = SyntheticFeed(seed=11, days=365, scenario="bull").generate()
closes, highs, lows = snap.closes, snap.highs, snap.lows
n = len(closes)
err_c = err_h = err_l = 0.0
for j, b in enumerate(bars):
    i = n - len(bars) + j
    err_c = max(err_c, abs(b["c"] - closes[i]))
    err_h = max(err_h, abs(b["h"] - highs[i]))
    err_l = max(err_l, abs(b["l"] - lows[i]))
print(f"bars compared                 : {len(bars)}  (path len {n})")
print(f"max |close diff|              : {err_c:.6f}")
print(f"max |high  diff|              : {err_h:.6f}")
print(f"max |low   diff|              : {err_l:.6f}")
print(f"generator scenario/seed       : {snap.meta}")
print(f"open == previous close (all)  : "
      f"{all(abs(b['o'] - (bars[j-1]['c'] if j else b['o'])) < 1e-9 for j, b in enumerate(bars))}"
      "  -> no gaps: TrueRange == High-Low")

print()
print("=" * 78)
print("B) ORDER BOOK LADDER — rebuild from generator formula (export_snapshot.py:52-60)")
print("=" * 78)
tick = mid * 0.0005
max_px_err = 0.0
max_sz_err = 0.0
ladder_bid_usd = ladder_ask_usd = 0.0
for k, (bid, ask) in enumerate(zip(ob["bids"], ob["asks"]), start=1):
    exp_bp = mid - k * tick
    exp_ap = mid + k * tick
    exp_bs = ob["bid_depth_usd"] / (mid * k * 0.55)
    exp_as = ob["ask_depth_usd"] / (mid * k * 0.55)
    max_px_err = max(max_px_err, abs(bid["price"] - exp_bp), abs(ask["price"] - exp_ap))
    max_sz_err = max(max_sz_err, abs(bid["size_avax"] - exp_bs), abs(ask["size_avax"] - exp_as))
    ladder_bid_usd += bid["price"] * bid["size_avax"]
    ladder_ask_usd += ask["price"] * ask["size_avax"]
    if k <= 4 or k == 10:
        print(f"  k={k:2d}  bid {bid['price']:9.4f} ({-k*5.0:+4.0f}bps) size {bid['size_avax']:9.2f} "
              f"| ask {ask['price']:9.4f} ({k*5.0:+4.0f}bps) size {ask['size_avax']:9.2f}")
print(f"max |price - (mid +- k*5bps)| : {max_px_err:.6f}")
print(f"max |size  - depth/(mid*k*.55)|: {max_sz_err:.6f}  (1/k law, exact)")
print(f"D1 bid = depth_bid/(mid*0.55) : {ob['bid_depth_usd']/(mid*0.55):.2f} AVAX")
print(f"D1 ask = depth_ask/(mid*0.55) : {ob['ask_depth_usd']/(mid*0.55):.2f} AVAX")
print(f"ladder total to +-50bps       : bid ${ladder_bid_usd:,.0f} / ask ${ladder_ask_usd:,.0f}")
reported_total = ob["total_depth_usd"]
print(f"reported total_depth_usd      : ${reported_total:,.2f}")
print(f"ladder/reported ratio         : {(ladder_bid_usd+ladder_ask_usd)/reported_total:.3f}x"
      "   <- same object, two scales")
print(f"ratio per side                : bid {ladder_bid_usd/ob['bid_depth_usd']:.3f}x / "
      f"ask {ladder_ask_usd/ob['ask_depth_usd']:.3f}x")

print()
print("=" * 78)
print("C) SCALAR BOOK FIELDS — rebuild from generator formulas")
print("=" * 78)
spread_formula = max(1.5, 40.0 / math.sqrt(dv_last / 1e6))
bb_formula = mid * (1 - spread_formula / 20000.0)
ba_formula = mid * (1 + spread_formula / 20000.0)
depth_base = dv_last * 0.0025
implied_skew = (ob["ask_depth_usd"] - ob["bid_depth_usd"]) / reported_total
print(f"dollar_vols[-1] (last bar dv) : ${dv_last:,.2f}")
print(f"spread = max(1.5, 40/sqrt(dv/1e6)) : {spread_formula:.4f} bps   | declared {ob['spread_bps']}")
print(f"best_bid = mid*(1-s/20000)    : {bb_formula:.4f}       | declared {ob['best_bid']}")
print(f"best_ask = mid*(1+s/20000)    : {ba_formula:.4f}       | declared {ob['best_ask']}")
print(f"total depth = 2*0.0025*dv     : ${2*depth_base:,.2f}     | declared ${reported_total:,.2f}")
print(f"OBI = -skew                   : {-implied_skew:.4f}          | declared {ob['order_book_imbalance']}")
print(f"venues_count=11               : a random choice from [6,7,8,9,10,11] (synthetic.py:68),"
      " not a venue census")
print(f"taker/maker fee bps           : {ob['taker_fee_bps']}/{ob['maker_fee_bps']}"
      " (synthetic.py:69-70, random taker from 4/5/6)")
print("=> depth_usd, OBI, spread, venues are PARAMETERS of the generator, not book observations.")
print(f"   depth_usd as share of ADV  : {reported_total/snap.volume_24h_usd*100:.3f}% of last-bar DV")
print(f"   OI / visible depth         : {der['open_interest_usd']/reported_total:.1f}x"
      f"   (ladder scale: {der['open_interest_usd']/(ladder_bid_usd+ladder_ask_usd):.1f}x)")

print()
print("=" * 78)
print("D) VOLATILITY ESTIMATOR BATTERY — same tape, five answers")
print("=" * 78)
c = [b["c"] for b in bars]
h = [b["h"] for b in bars]
lo = [b["l"] for b in bars]
rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
for w in (30, 90, 120):
    s = st.stdev(rets[-w:])
    print(f"close-close sd last {w:3d} bars : {s*100:.3f}%/day  -> x sqrt(365) = {s*math.sqrt(365)*100:6.2f}% ann")
hl2 = [math.log(h[i] / lo[i]) ** 2 for i in range(len(c))]
for w in (30, 90, 120):
    sp = math.sqrt(sum(hl2[-w:]) / len(hl2[-w:]) / (4 * math.log(2)))
    print(f"Parkinson    last {w:3d} bars : {sp*100:.3f}%/day  -> x sqrt(365) = {sp*math.sqrt(365)*100:6.2f}% ann")
rng = [(h[i] - lo[i]) / c[i] * 100 for i in range(len(c))]
atr14 = ind.atr(h, lo, c, 14)
print(f"mean (H-L)/close last 30      : {st.mean(rng[-30:]):.3f}%   last 90: {st.mean(rng[-90:]):.3f}%")
print(f"ATR14 (repo function, Wilder) : {atr14:.4f} = {atr14/mid*100:.3f}% of price   | declared {ci['atr14']} / {ci['atr_pct_of_price']}%")
print(f"declared vol_30d_ann_pct      : {ci['vol_30d_annual_pct']} | vol_90d {ci['vol_90d_annual_pct']}"
      f" | ewma {ci['ewma_vol_annual_pct']} | garch {ci['garch11_annual_pct']}")
cc30 = st.stdev(rets[-30:]) * math.sqrt(365) * 100
pk30 = math.sqrt(sum(hl2[-30:]) / 30 / (4 * math.log(2))) * math.sqrt(365) * 100
atr_implied = (atr14 / mid / 1.596) * math.sqrt(365) * 100
print(f"RATIO Parkinson/close-close 30: {pk30/cc30:.3f}x")
print(f"ATR-implied ann vol (E[H-L]=1.596 sigma) : {atr_implied:.2f}%  vs declared {ci['vol_30d_annual_pct']}%"
      f"  => {atr_implied/ci['vol_30d_annual_pct']:.3f}x")
print(f"generator truth: daily sigma = 0.038 (bull) => {0.038*math.sqrt(365)*100:.2f}% ann")
print(f"vol_regime declared           : {ci['vol_regime']} (percentile of its own 120-bar history,"
      " NOT an absolute level)")

print()
print("=" * 78)
print("E) SLIPPAGE CURVE from the ladder (GENERATOR ARTIFACT, not a measurement)")
print("=" * 78)


def curve(side: list[dict], notional: float) -> float:
    """VWAP cost in bps vs mid for an aggressive order of `notional` USD."""
    spent = qty = 0.0
    for lvl in side:
        lvl_usd = lvl["price"] * lvl["size_avax"]
        take = min(lvl_usd, notional - spent)
        if take <= 0:
            break
        spent += take
        qty += take / lvl["price"]
    if qty <= 0 or spent < notional - 1e-6:
        return float("nan")
    vwap = spent / qty
    return abs(vwap - mid) / mid * 10_000.0


print(f"{'notional':>12} | {'BUY bps':>9} | {'SELL bps':>9}")
for q in (100_000, 500_000, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 8_000_000):
    b = curve(ob["asks"], q)
    s = curve(ob["bids"], q)
    print(f"${q:>11,} | {b:>9.2f} | {s:>9.2f}")
full_buy = curve(ob["asks"], ladder_ask_usd * 0.999)
full_sell = curve(ob["bids"], ladder_bid_usd * 0.999)
print(f"full ladder : buy ${ladder_ask_usd:,.0f} -> {full_buy:.2f} bps | "
      f"sell ${ladder_bid_usd:,.0f} -> {full_sell:.2f} bps")
print(f"top-of-book band 0..4.14 bps has NO size in the snapshot (ladder starts at +-5bps)")

print()
print("=" * 78)
print("F) THREE INTERNAL COST MEASURES for the SAME synthetic asset")
print("=" * 78)
adv = snap.volume_24h_usd
amihud = ind.amihud_illiquidity([math.log(c[i] / c[i - 1]) for i in range(1, len(c))][-90:],
                                [b["dv"] for b in bars][-90:])
print(f"declared amihud_illiquidity   : {ci['amihud_illiquidity']:.6e} | recomputed {amihud:.6e}")
print(f"  -> |r| = ILLIQ*1e-6 * DV  => per $1M of daily volume: "
      f"{ci['amihud_illiquidity']*1e-6*1e6*10_000:.3f} bps ; per $5M: "
      f"{ci['amihud_illiquidity']*1e-6*5e6*10_000:.3f} bps (linear in DV)")
sigma_d = ci["vol_30d_annual_pct"] / 100 / math.sqrt(365)
for q in (1_000_000, 5_000_000):
    impact = ind.market_impact_sqrt(q, adv, sigma_d) * 10_000
    print(f"sqrt-law (repo ind.market_impact_sqrt) at ${q:,} : {impact:.2f} bps")
print(f"ladder curve at $5,000,000    : buy {curve(ob['asks'],5e6):.2f} bps / sell {curve(ob['bids'],5e6):.2f} bps")
print(f"spread alone (declared)       : {ob['spread_bps']:.2f} bps ; taker fee one way: {ob['taker_fee_bps']:.1f} bps")
print(f"ADV (last bar dv)             : ${adv:,.0f} ; OI/ADV declared {der['oi_to_adv_ratio']}")
print(f"kyle_lambda declared          : {ci['kyle_lambda']:.4e} (USD per USD, regressor = UNSIGNED dv)")

print()
print("=" * 78)
print("G) EXECUTIVE SUMMARY vs FULL SNAPSHOT (same as_of, same price)")
print("=" * 78)
summary = {"best_bid": 115.5124, "best_ask": 115.5702, "active_addresses": 48000,
           "dex_volume_24h_usd": 140_000_000, "open_interest_usd": 430_000_000,
           "ema20": 108.02, "ema50": 101.55, "ema200": 88.2, "support_60d": 96.4,
           "resistance_60d": 121.9, "realized_vol_30d_pct": 55.55, "atr_pct_of_price": 3.03,
           "tvl_change_7d_pct": 6.1, "btc_dominance": 52.4, "validators": 1250,
           "ret_90d_pct": 71.2, "ret_7d_pct": 4.9, "staking_ratio_pct": 60.8}
full = {"best_bid": ob["best_bid"], "best_ask": ob["best_ask"],
        "active_addresses": onch["active_addresses"],
        "dex_volume_24h_usd": onch["dex_volume_24h_usd"],
        "open_interest_usd": der["open_interest_usd"],
        "ema20": ci["ema20"], "ema50": ci["ema50"], "ema200": ci["ema200"],
        "support_60d": ci["support_60d"], "resistance_60d": ci["resistance_60d"],
        "realized_vol_30d_pct": ci["vol_30d_annual_pct"], "atr_pct_of_price": ci["atr_pct_of_price"],
        "tvl_change_7d_pct": onch["tvl_change_7d_pct"],
        "btc_dominance": data["macro"]["btc_dominance_pct"], "validators": onch["validators"],
        "ret_90d_pct": ci["ret_90d_pct"], "ret_7d_pct": ci["ret_7d_pct"],
        "staking_ratio_pct": onch["staking_ratio_pct"]}
bad = 0
for k, v in summary.items():
    f = full[k]
    rel = abs(v - f) / max(abs(f), 1e-9)
    mark = "DIFF" if rel > 0.01 else "ok"
    if rel > 0.01:
        bad += 1
    print(f"  {k:24s} summary {v:>16,.4f} | full {f:>16,.4f} | {rel*100:7.2f}%  {mark}")
print(f"fields disagreeing >1%        : {bad} / {len(summary)}")
s_implied = (summary["best_ask"] - summary["best_bid"]) / mid * 10_000
print(f"summary BBO implies spread    : {s_implied:.3f} bps vs its own spread_bps 1.73 "
      f"=> {s_implied/1.73:.2f}x internal contradiction")
print(f"as_of (both)                  : {AS_OF}")
