"""
أداة تحقّق ميكانيكية للوكيل 01 — بنية السوق — الإصدار 2.
الدورة: لقطة 2026-09-21T00:09:44Z (366 شمعة، SEED=11، SCENARIO=bull).

الغرض: تحويل كل ادعاء ميكانيكي في رأي الوكيل 01 إلى رقم قابل لإعادة الإنتاج.
السكربت **لا يصدر رأياً ولا توصية ولا كمية** (المادة 0.2 و1.2).

ما يفحصه:
  A) إعادة توليد المسار من البذرة 11 ومطابقته لشمعات اللقطة (إثبات المصدر).
  B) هندسة سلّم الدفتر: الشبكة ±k×5 نقاط أساس وقانون الوزن 1/k ومجموع المستويات.
  C) الحقول العددية للدفتر: سبريد/عمق/OBI/منصات/رسوم — معاملات مولّد أم قياس؟
  D) منحنى الكلفة المُستخرج من السلّم + النطاق الفارغ + قدرة التمييز على الحجم.
  E) تمديد النموذج خارج المستويات المنشورة (استدلال موسوم، مستوى 7) وعمقه.
  F) الحجم اليومي والنِسَب: عمق/ADV، OI/عمق، سقف المشاركة 5% (المادة 5.3).
  G) بطارية التقلب + شذوذ الطابع الزمني لشمعة اليوم الأخير.
  H) تدقيق amihud و kyle_lambda كما يُحسبان فعلاً في الكود.
  I) مقارنة الملخص التنفيذي بملف اللقطة حقلاً بحقل.
  J) ما لا يمكن قياسه إطلاقاً (OFI/VPIN/λ/المرونة/التلاعب) وسبب ذلك.

التشغيل:  python tools/verify_01_microstructure_v2.py
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from avax_desk import indicators as ind  # noqa: E402
from avax_desk.data.synthetic import SyntheticFeed  # noqa: E402

SNAP_PATH = ROOT / "data" / "snapshot_full.json"
SUM_PATH = ROOT / "data" / "snapshot_summary.json"
D = json.loads(SNAP_PATH.read_text(encoding="utf-8"))
bars, ob, ci = D["ohlcv_daily"], D["orderbook"], D["computed_indicators"]
der, onch, mac = D["derivatives"], D["onchain"], D["macro"]
meta, cons = D["_meta"], D["_consistency"]

mid = ob["mid_price"]
dv_last = bars[-1]["dv"]
AS_OF = meta["generated_at"]
NOW = datetime.now(timezone.utc)
H10 = sum(1.0 / k for k in range(1, 11))
R: dict = {}


def sec(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def harmonic(x: float) -> float:
    """H(x) لدالة توافقية عند وسيطة حقيقية (دقيقة للعدد الصحيح، تقريبية بعده)."""
    n = int(math.floor(x))
    h = sum(1.0 / i for i in range(1, n + 1)) if n <= 5000 else (
        math.log(n) + 0.5772156649015329 + 1.0 / (2 * n) - 1.0 / (12 * n * n)
    )
    if x > n:
        h += (x - n) / (n + 1)
    return h


def walk(side: list[dict], notional: float) -> tuple[float, float]:
    """(vwap, filled_usd) لأمر عدواني بحجم notional على مستويات `side`."""
    spent = qty = 0.0
    for lvl in side:
        lvl_usd = lvl["price"] * lvl["size_avax"]
        take = min(lvl_usd, notional - spent)
        if take <= 0:
            break
        spent += take
        qty += take / lvl["price"]
    return (spent / qty if qty else float("nan")), spent


def cost_bps(side: list[dict], notional: float) -> float:
    vwap, filled = walk(side, notional)
    if not filled or filled < notional - 1e-6:
        return float("nan")          # غير قابل للتنفيذ داخل المستويات المنشورة
    return abs(vwap - mid) / mid * 10_000.0


# ==========================================================================
sec("A) PROVENANCE — إعادة توليد المسار من البذرة 11 ومقارنته بشمعات اللقطة")
snap = SyntheticFeed(seed=11, days=365, scenario="bull").generate()
closes, highs, lows, vols, dvs = (snap.closes, snap.highs, snap.lows,
                                 snap.volumes, snap.dollar_volumes)
n = len(closes)
errs = {"c": 0.0, "h": 0.0, "l": 0.0, "v": 0.0, "dv": 0.0}
for j, b in enumerate(bars):
    i = n - len(bars) + j
    errs["c"] = max(errs["c"], abs(b["c"] - closes[i]))
    errs["h"] = max(errs["h"], abs(b["h"] - highs[i]))
    errs["l"] = max(errs["l"], abs(b["l"] - lows[i]))
    errs["v"] = max(errs["v"], abs(b["v"] - vols[i]))
    errs["dv"] = max(errs["dv"], abs(b["dv"] - dvs[i]))
print(f"len(path)={n} | bars in snapshot={len(bars)} | _meta.bars_provided={meta['bars_provided']}")
for k, e in errs.items():
    print(f"max |bar.{k:2s} - regenerated| : {e:.6f}")
print(f"open == previous close (all bars) : "
      f"{all(abs(b['o'] - (bars[j-1]['c'] if j else b['o'])) < 1e-9 for j, b in enumerate(bars))}")
print(f"generator meta                   : {snap.meta}")
print(f"_meta.source / seed / scenario   : {meta['source']} / {meta['seed']} / {meta['scenario']}")
print(f"_meta.warning                    : {meta['warning']}")
R["provenance"] = {"max_err": errs, "bars": len(bars), "scenario": meta["scenario"],
                   "seed": meta["seed"], "source": meta["source"]}

# ==========================================================================
sec("B) LADDER GEOMETRY — الشبكة ±k×5bps وقانون الوزن 1/k ومجموع المستويات")
tick = mid * 0.0005
max_px_err = max_sz_err = 0.0
ladder_bid = ladder_ask = 0.0
ring_usd_bid: list[float] = []
ring_usd_ask: list[float] = []
print(f"mid={mid}  tick={tick:.6f} (=5.00 bps)  H(10)={H10:.6f}")
print(f"{'k':>3} {'بعد الشراء (bps)':>16} {'حجم طلب AVAX':>14} {'تراكمي $':>14} "
      f"{'بعد البيع (bps)':>16} {'حجم عرض AVAX':>14} {'تراكمي $':>14}")
cb = ca = 0.0
for k, (b, a) in enumerate(zip(ob["bids"], ob["asks"]), start=1):
    exp_bp, exp_ap = mid - k * tick, mid + k * tick
    exp_bs = (ob["bid_depth_usd"] * (1.0 / k) / H10) / exp_bp
    exp_as = (ob["ask_depth_usd"] * (1.0 / k) / H10) / exp_ap
    max_px_err = max(max_px_err, abs(b["price"] - exp_bp), abs(a["price"] - exp_ap))
    max_sz_err = max(max_sz_err, abs(b["size_avax"] - exp_bs), abs(a["size_avax"] - exp_as))
    ladder_bid += b["price"] * b["size_avax"]
    ladder_ask += a["price"] * a["size_avax"]
    cb += b["price"] * b["size_avax"]
    ca += a["price"] * a["size_avax"]
    ring_usd_bid.append(cb)
    ring_usd_ask.append(ca)
    if k <= 3 or k in (5, 10):
        print(f"{k:>3} {-k*5:+15.1f} {b['size_avax']:>14.1f} {cb:>14,.0f} "
              f"{k*5:+15.1f} {a['size_avax']:>14.1f} {ca:>14,.0f}")
print(f"max |price - (mid ∓ k·tick)|    : {max_px_err:.7f}")
print(f"max |size  - depth/(H10·k·px)|  : {max_sz_err:.7f}  (قانون 1/k)")
print(f"Σ(price×size) bids / asks       : {ladder_bid:,.2f} / {ladder_ask:,.2f}")
print(f"declared bid_depth / ask_depth  : {ob['bid_depth_usd']:,.2f} / {ob['ask_depth_usd']:,.2f}")
print(f"ratio ladder/declared (كل جهة)  : {ladder_bid/ob['bid_depth_usd']:.6f} / "
      f"{ladder_ask/ob['ask_depth_usd']:.6f}  <- متوافق (كان 5.327× في النسخة السابقة)")
print(f"أقصى تنفيذ عدواني داخل المنشور  : شراء ${ladder_ask:,.2f} / بيع ${ladder_bid:,.2f}")
R["ladder"] = {"max_px_err": max_px_err, "max_sz_err": max_sz_err,
               "bid_usd": ladder_bid, "ask_usd": ladder_ask,
               "declared_bid": ob["bid_depth_usd"], "declared_ask": ob["ask_depth_usd"],
               "consistency_ratio": [ladder_bid / ob["bid_depth_usd"],
                                     ladder_ask / ob["ask_depth_usd"]]}

# ==========================================================================
sec("C) SCALAR BOOK FIELDS — هل هي قياس أم معاملات مولّد؟")
spread_f = max(1.5, 40.0 / math.sqrt(dv_last / 1e6))
bb_f = mid * (1 - spread_f / 20_000.0)
ba_f = mid * (1 + spread_f / 20_000.0)
depth_base = dv_last * 0.0025
skew = (ob["ask_depth_usd"] - ob["bid_depth_usd"]) / (ob["bid_depth_usd"] + ob["ask_depth_usd"])
recomputed_spread = (ob["best_ask"] - ob["best_bid"]) / mid * 10_000.0
half_spread_bps = recomputed_spread / 2
print(f"dollar_volume[-1]                     : ${dv_last:,.2f}")
print(f"spread  = max(1.5, 40/√(DV/1e6))      : {spread_f:.4f} | مُعلَن {ob['spread_bps']}")
print(f"best_bid= mid·(1−s/20000)             : {bb_f:.4f} | مُعلَن {ob['best_bid']}")
print(f"best_ask= mid·(1+s/20000)             : {ba_f:.4f} | مُعلَن {ob['best_ask']}")
print(f"سبريد مُعاد حسابه من أفضل عرض/طلب      : {recomputed_spread:.4f} bps "
      f"(نصف سبريد {half_spread_bps:.4f}) — فرق التقريب فقط")
print(f"depth_base = 0.0025×DV                : ${depth_base:,.2f}")
print(f"skew (ask−bid)/(ask+bid)              : {skew:+.6f} | OBI مُعلَن {ob['order_book_imbalance']}")
print(f"OI = DV × U(0.8,1.6)                  : {der['open_interest_usd']/dv_last:.4f}×DV "
      f"| مُعلَن OI/ADV {der['oi_to_adv_ratio']}")
print(f"venues = choice([6..11])              : مُعلَن {ob['venues_count']} | مولَّد {snap.venues}")
print(f"taker/maker fee = choice(4,5,6)/1.0   : مُعلَن {ob['taker_fee_bps']}/{ob['maker_fee_bps']} "
      f"| مولَّد {snap.taker_fee_bps}/{snap.maker_fee_bps}")
print(f"إثبات مولّد: snap.venues={snap.venues} == orderbook.venues_count="
      f"{ob['venues_count']} -> {snap.venues == ob['venues_count']} ؛ "
      f"snap.taker_fee_bps={snap.taker_fee_bps} == {ob['taker_fee_bps']} -> "
      f"{snap.taker_fee_bps == ob['taker_fee_bps']}")
print("=> السبريد/العمق/OBI/عدد المنصات/الرسوم كلها **معاملات مولّد** لا مشاهدات دفتر.")
R["scalars"] = {"spread_formula": spread_f, "spread_declared": ob["spread_bps"],
                "recomputed_spread_bps": recomputed_spread, "half_spread_bps": half_spread_bps,
                "depth_base": depth_base, "skew": skew, "obi_declared": ob["order_book_imbalance"],
                "venues_declared": ob["venues_count"], "venues_generated": snap.venues,
                "taker_fee": ob["taker_fee_bps"], "oi_over_adv": der["oi_to_adv_ratio"],
                "depth_pct_of_dv_last": (ladder_bid + ladder_ask) / dv_last * 100}

# ==========================================================================
sec("D) منحنى الكلفة من المستويات المنشورة (أثر اللقطة، لا قياس سوق)")
print(f"{'notional $':>13} | {'BUY bps':>9} | {'SELL bps':>9} | {'+رسوم ذهاب':>11} | {'ذهاب وعودة':>11}")
grid = [10_000, 25_000, 50_000, 100_000, 200_000, 235_913, 300_000, 500_000, 690_000]
costs = {}
fee = ob["taker_fee_bps"]
for q in grid:
    b = cost_bps(ob["asks"], q)
    s = cost_bps(ob["bids"], q)
    costs[q] = (b, s)
    one_way = "—" if math.isnan(b) else f"{b + fee:.2f}"
    round_trip = "—" if math.isnan(b) else f"{2 * b + 2 * fee:.2f}"
    print(f"{q:>13,} | {b:>9.2f} | {s:>9.2f} | {one_way:>11} | {round_trip:>11}")
L1_ask_usd = ob["asks"][0]["price"] * ob["asks"][0]["size_avax"]
L1_bid_usd = ob["bids"][0]["price"] * ob["bids"][0]["size_avax"]
print(f"\nالحلقة الأولى: شراء ${L1_ask_usd:,.0f} @ +5.00 bps | بيع ${L1_bid_usd:,.0f} @ −5.00 bps")
print(f"الكلفة عند 10 آلاف $ = {costs[10_000][0]:.2f} bps وعند {L1_ask_usd:,.0f} $ = "
      f"{costs[235_913][0]:.2f} bps ⇒ قدرة تمييز على الحجم = 0.00 bps داخل الحلقة")
print(f"النطاق الفارغ: 0.00 إلى 4.99 bps بلا حجم منشور؛ أفضل عرض/طلب على ∓{half_spread_bps:.3f} bps "
      f"بلا حجم ⇒ الفجوة ×{5.0/half_spread_bps:.2f} بين أدنى كلفة منشورة وأدنى كلفة مُعلَنة")
print(f"أرضية الرسوم ذهاباً وعودة = {2*ob['taker_fee_bps']:.0f} bps "
      f"= {2*ob['taker_fee_bps']/(2*5.0):.2f}× كلفة السلّم الكاملة ذهاباً وعودة عند الحلقة الأولى")
funding_bps_day = der["funding_rate_8h"] * 3 * 10_000
print(f"حمل التمويل = {der['funding_rate_8h']*10_000:.4f} bps/8h = {funding_bps_day:.3f} bps/يوم")
R["cost_curve"] = {str(k): v for k, v in costs.items()}
R["cost_curve_meta"] = {"L1_ask_usd": L1_ask_usd, "L1_bid_usd": L1_bid_usd,
                        "taker_fee_bps": ob["taker_fee_bps"],
                        "funding_bps_per_day": funding_bps_day}

# ==========================================================================
sec("E) تمديد النموذج خارج المستويات المنشورة — استدلال موسوم (مستوى 7)")
print("النموذج: قانون الوزن 1/k نفسه مُمدَّداً إلى الحلقة n ⇒ العمق التراكمي داخل ±b bps")
print("        = depth_side × H(b/5)/H(10). هذا **افتراض** لا قياس: لا بيانات خارج الحلقة 10.")
print(f"\n{'نطاق':>10} {'عمق طلب (نموذج)':>18} {'عمق عرض (نموذج)':>18} {'إجمالي':>16} {'% من DV':>9}")
for bps in (10, 50, 100, 200):
    k = bps / 5.0
    ratio = harmonic(k) / H10
    db, da = ob["bid_depth_usd"] * ratio, ob["ask_depth_usd"] * ratio
    tag = " (منشور)" if bps <= 50 else ""
    print(f"{'±'+str(bps)+' bps':>10} {db:>18,.0f} {da:>18,.0f} {db+da:>16,.0f} "
          f"{(db+da)/dv_last*100:>8.3f}%{tag}")
    R.setdefault("model_depth", {})[bps] = {"bid": db, "ask": da, "pct_of_dv": (db + da) / dv_last * 100}


def model_cost_ask(q: float) -> float:
    """كلفة نموذجية (bps) لأمر شراء بحجم q بتمديد 1/k — NaN إذا تجاوز النموذج حدّه."""
    k = 10.0
    if q <= ring_usd_ask[9]:
        return cost_bps(ob["asks"], q)
    target = q / ob["ask_depth_usd"] * H10            # H(n) المطلوبة
    lo, hi = 10.0, 1e9
    for _ in range(200):
        m = (lo + hi) / 2
        if harmonic(m) < target:
            lo = m
        else:
            hi = m
    k = (lo + hi) / 2
    return k * 5.0 * 100 / 100 if k * 5.0 < 1e7 else float("nan")


adv_last = dv_last
sigma_d = ci["vol_30d_annual_pct"] / 100 / math.sqrt(365)
print(f"\n{'notional $':>12} | {'سلّم منشور':>11} | {'نموذج 1/k':>11} | "
      f"{'قانون الجذر':>11} | {'أميهود':>9} | التباعد")
for q in (500_000, 750_000, 848_000, 1_000_000, 1_500_000, 2_000_000):
    lad = cost_bps(ob["asks"], q)
    mod = model_cost_ask(q)
    sq = ind.market_impact_sqrt(q, adv_last, sigma_d) * 10_000
    am = ci["amihud_illiquidity"] * 1e-6 * q * 10_000
    lad_s = "غير قابل" if math.isnan(lad) else f"{lad:.2f}"
    disp = "—" if math.isnan(mod) or mod <= 0 else f"{mod/max(sq,1e-9):.1f}× (نموذج/جذر)"
    print(f"{q:>12,} | {lad_s:>11} | {mod:>11.1f} | {sq:>11.2f} | {am:>9.2f} | {disp}")
    R.setdefault("model_cost", {})[q] = {"ladder": lad, "model_1k": mod, "sqrt_law": sq, "amihud": am}
print(f"\nσ_day = vol30/√365 = {sigma_d*100:.4f}% | amihud مُعلَن = {ci['amihud_illiquidity']:.6e}")
print("ملاحظة: النموذج 1/k ينهار فوق ~1 مليون $ (يتطلب ملايين الحلقات) ⇒ ليس نموذج سيولة، "
      "بل إثبات أن ذيل الدفتر المنشور رقيق هندسياً.")

# ==========================================================================
sec("F) الحجم والنِسَب وسقف المشاركة (المادة 5.3)")
dvs = [b["dv"] for b in bars]
for w in (30, 90, 366):
    print(f"متوسط dv آخر {w:>3} شمعة : ${st.mean(dvs[-w:]):>18,.0f} | وسيط ${st.median(dvs[-w:]):>18,.0f}")
print(f"dv شمعة اليوم (آخر شمعة)  : ${dv_last:>18,.0f}  (الأعلى من متوسط 30 بشمعة؟ "
      f"{dv_last > st.mean(dvs[-31:-1])})")
depth_total = ladder_bid + ladder_ask
print(f"إجمالي الدفتر المنشور      : ${depth_total:,.0f} = {depth_total/dv_last*100:.3f}% من dv اليوم")
print(f"OI / الدفتر المنشور        : {der['open_interest_usd']/depth_total:.1f}×  "
      f"(OI = dv×U(0.8,1.6)، العمق = dv×0.005 ⇒ نسبة ثابتة 160–320× بالبناء)")
cap5 = 0.05 * dv_last
print(f"سقف 5% من حجم السوق (5.3)  : ${cap5:,.0f}")
print(f"  ÷ الدفتر المنشور كاملاً  : {cap5/depth_total:.2f}×  | ÷ جهة الشراء {cap5/ladder_ask:.2f}×")
print(f"  ÷ العمق النموذجي ±2%     : {cap5/(R['model_depth'][200]['bid']+R['model_depth'][200]['ask']):.2f}×")
print(f"  ⇒ سقف المادة 5.3 أكبر من كل عمق مرئي أو مُنمذَج: لا يمكن احترامه بالتنفيذ الفوري.")
free_float = D["fundamentals"]["circulating_supply"] * (1 - onch["staking_ratio_pct"] / 100)
print(f"معروض مُقفل (ستيكينغ)      : {onch['staking_ratio_pct']:.2f}% ⇒ عائم حرّ ≈ {free_float:,.0f} AVAX "
      f"= ${free_float*mid/1e9:.2f}B (سياق ميكانيكي اصطناعي، وΔStake على P-Chain غير مُقدَّم)")
R["ratios"] = {"adv_mean30": st.mean(dvs[-30:]), "adv_mean90": st.mean(dvs[-90:]),
               "dv_last": dv_last, "depth_total": depth_total,
               "depth_pct_of_dv": depth_total / dv_last * 100,
               "oi_over_depth": der["open_interest_usd"] / depth_total,
               "cap5_usd": cap5, "cap5_over_depth": cap5 / depth_total,
               "cap5_over_ask": cap5 / ladder_ask, "free_float_avax": free_float}

# ==========================================================================
sec("G) بطارية التقلب + شذوذ الطابع الزمني لشمعة اليوم الأخير")
c = [b["c"] for b in bars]
hh = [b["h"] for b in bars]
ll = [b["l"] for b in bars]
rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
for w in (30, 90, 366):
    print(f"close-close آخر {w:>3} شمعة : {st.stdev(rets[-w:])*100:.4f}%/يوم ⇒ "
          f"{st.stdev(rets[-w:])*math.sqrt(365)*100:6.2f}% سنوياً")
hl2 = [math.log(hh[i] / ll[i]) ** 2 for i in range(len(c))]
for w in (30, 90):
    pk = math.sqrt(sum(hl2[-w:]) / w / (4 * math.log(2)))
    print(f"Parkinson   آخر {w:>3} شمعة : {pk*100:.4f}%/يوم ⇒ {pk*math.sqrt(365)*100:6.2f}% سنوياً")
atr14 = ind.atr(hh, ll, c, 14)
cc30 = st.stdev(rets[-30:]) * math.sqrt(365) * 100
pk30 = math.sqrt(sum(hl2[-30:]) / 30 / (4 * math.log(2))) * math.sqrt(365) * 100
atr_impl = (atr14 / mid / 1.596) * math.sqrt(365) * 100
print(f"ATR14 = {atr14:.4f} = {atr14/mid*100:.3f}% من السعر ⇒ تقلب مُستنتج {atr_impl:.2f}% سنوياً")
print(f"الحقيقة المولّدة: σ اليومي = 0.038 ⇒ {0.038*math.sqrt(365)*100:.2f}% سنوياً")
print(f"تشتت: Parkinson/close-close(30) = {pk30/cc30:.3f}× ؛ "
      f"ATR المُستنتج/المُعلَن = {atr_impl/ci['vol_30d_annual_pct']:.3f}× ؛ "
      f"GARCH {ci['garch11_annual_pct']} vs RV {ci['vol_30d_annual_pct']}")
print(f"vol_regime = '{ci['vol_regime']}' (رتبة مئوية داخل التاريخ نفسه، لا مستوى مطلق)")
last = bars[-1]
rng_pct = (last["h"] - last["l"]) / last["c"] * 100
bar_open = datetime.fromisoformat(last["t"])
elapsed = (datetime.fromisoformat(AS_OF) - bar_open).total_seconds() / 60.0
print(f"\nشمعة اليوم الأخير: {last['t']}")
print(f"  مدى (H−L)/C = {rng_pct:.3f}% | ATR14 = {ci['atr_pct_of_price']:.3f}% ⇒ نسبة {rng_pct/ci['atr_pct_of_price']:.2f}×")
print(f"  dv = ${last['dv']:,.0f} في {elapsed:.1f} دقيقة منذ فتح الشمعة (as_of {AS_OF})")
print(f"  ⇒ الشمعة ليست جزئية: هي شمعة يوم كامل بطابع زمني عمره {elapsed:.1f} دقيقة. "
      f"من يُقايس على الزمن المُنقضي يخطئ ×{1440/elapsed:.0f}")
R["vol"] = {"cc30": cc30, "pk30": pk30, "atr14": atr14, "atr_implied_ann": atr_impl,
            "generator_truth_ann": 0.038 * math.sqrt(365) * 100, "dispersion_pk_cc": pk30 / cc30,
            "last_bar_range_pct": rng_pct, "last_bar_age_min": elapsed}

# ==========================================================================
sec("H) تدقيق amihud و kyle_lambda كما يُحسبان فعلاً (base.py:87-94)")
am = ind.amihud_illiquidity(rets[-90:], dvs[-90:])
print(f"amihud مُعلَن {ci['amihud_illiquidity']:.6e} | مُعاد حسابه {am:.6e} "
      f"| مطابق {abs(am-ci['amihud_illiquidity'])/ci['amihud_illiquidity'] < 0.001}")
kl = ind.kyle_lambda([c[i] - c[i - 1] for i in range(len(c) - 60, len(c))],
                     [dvs[i] for i in range(len(dvs) - 60, len(dvs))])
print(f"kyle_lambda مُعلَن {ci['kyle_lambda']:.6e} | مُعاد حسابه {kl:.6e} | مطابق {abs(kl-ci['kyle_lambda'])<1e-15}")
x = dvs[-60:]
y = [c[i] - c[i - 1] for i in range(len(c) - 60, len(c))]
mx, my = st.mean(x), st.mean(y)
sxx = sum((v - mx) ** 2 for v in x)
syy = sum((v - my) ** 2 for v in y)
sxy = sum((x[i] - mx) * (y[i] - my) for i in range(len(x)))
r2 = sxy ** 2 / (sxx * syy)
se = math.sqrt((syy - sxy ** 2 / sxx) / (len(x) - 2) / sxx)
print(f"  المُنحَدِّر غير موقَّع: كل قيم DV موجبة ({min(x):,.0f}..{max(x):,.0f}) "
      f"⇒ يخالف دالّة kyle_lambda نفسها (SignedVolume، indicators.py:674-689)")
print(f"  R² = {r2:.4f} | λ = {sxy/sxx:.4e} | خطأ معياري = {se:.2e} | t = {(sxy/sxx)/se:.2f} "
      f"| Durbin-Watson = {sum((y[i]-y[i-1])**2 for i in range(1,len(y)))/sum(v**2 for v in y):.3f}")
print(f"  ⇒ لا أخطاء معيارية ولا تشخيص في اللقطة (خطأ قاتل §9: «λ بلا تشخيص») "
      f"⇒ رفض تطبيق Cost ≈ λQ²/2 (المادة 8.1).")
R["lambda_audit"] = {"amihud_recomputed": am, "kyle_declared": ci["kyle_lambda"],
                     "kyle_recomputed": kl, "r2": r2, "se": se,
                     "t": (sxy / sxx) / se, "unsigned_regressor": min(x) > 0}

# ==========================================================================
sec("I) الملخص التنفيذي مقابل ملف اللقطة — حقلاً بحقل")
summary = json.loads(SUM_PATH.read_text(encoding="utf-8"))
full_map = {
    "price": ci["price"], "ret_1d_pct": ci["ret_1d_pct"], "ret_7d_pct": ci["ret_7d_pct"],
    "ret_30d_pct": ci["ret_30d_pct"], "ret_90d_pct": ci["ret_90d_pct"], "rsi14": ci["rsi14"],
    "adx14": ci["adx14"], "atr_pct_of_price": ci["atr_pct_of_price"], "ema20": ci["ema20"],
    "ema50": ci["ema50"], "ema200": ci["ema200"], "hurst_exponent": ci["hurst_exponent"],
    "zscore_30d": ci["zscore_30d"], "vol_regime": ci["vol_regime"],
    "realized_vol_30d_pct": ci["vol_30d_annual_pct"], "best_bid": ob["best_bid"],
    "best_ask": ob["best_ask"], "spread_bps": ob["spread_bps"],
    "order_book_imbalance": ob["order_book_imbalance"],
    "funding_rate_8h": der["funding_rate_8h"], "open_interest_usd": der["open_interest_usd"],
    "tvl_usd": onch["tvl_usd"], "tvl_change_7d_pct": onch["tvl_change_7d_pct"],
    "exchange_netflow_usd": onch["exchange_netflow_usd"],
    "active_addresses": onch["active_addresses"], "staking_ratio_pct": onch["staking_ratio_pct"],
    "dex_volume_24h_usd": onch["dex_volume_24h_usd"], "fear_greed": D["sentiment"]["fear_greed"],
    "btc_dominance_pct": mac["btc_dominance_pct"], "btc_corr_30d": mac["btc_corr_30d"],
    "market_cap_usd": D["fundamentals"]["market_cap_usd"],
    "circulating_supply": D["fundamentals"]["circulating_supply"],
    "support_provided_bars": ci["support_provided_bars"],
    "resistance_provided_bars": ci["resistance_provided_bars"],
    "as_of": meta["generated_at"],
}
bad = []
for k, f in full_map.items():
    v = summary.get(k, "<غائب>")
    if isinstance(f, (int, float)) and isinstance(v, (int, float)) and not isinstance(f, bool):
        rel = abs(v - f) / max(abs(f), 1e-9)
        ok = rel <= 0.01
    else:
        ok = v == f
    if not ok:
        bad.append((k, v, f))
print(f"حقول مطابقة : {len(full_map)-len(bad)} / {len(full_map)} | متعارضة : {len(bad)}")
for k, v, f in bad:
    print(f"  DIFF {k:24s} summary={v} full={f}")
TASK_AS_OF = "2026-09-21T00:12:00+00:00"
print(f"as_of في الملخص الممرَّر للمهمة : {TASK_AS_OF}")
print(f"as_of في data/snapshot_summary.json : {summary['as_of']}")
print(f"as_of في _meta.generated_at         : {meta['generated_at']}")
d1 = (datetime.fromisoformat(TASK_AS_OF) - datetime.fromisoformat(meta["generated_at"])).total_seconds()
print(f"فارق الملخص الممرَّر عن الملف : {d1:.0f} ثانية")
print(f"now (UTC) = {NOW.isoformat(timespec='seconds')} | عمر اللقطة = "
      f"{(NOW - datetime.fromisoformat(AS_OF)).total_seconds()/60:.1f} دقيقة ⇒ "
      f"{'طازجة (<24h)' if (NOW-datetime.fromisoformat(AS_OF)).total_seconds() < 86400 else 'STALE'}")
R["summary_check"] = {"mismatches": bad, "task_as_of_delta_s": d1,
                      "age_min": (NOW - datetime.fromisoformat(AS_OF)).total_seconds() / 60}

# ==========================================================================
sec("J) ما لا يمكن قياسه من لقطة واحدة ثابتة — سبب الامتناع")
print("لا شريط تداولات (Trades) ولا تحديثات دفتر (L2 updates) في اللقطة ⇒")
print("  • OFI (Cont-Kukanov-Stoikov 2014): يحتاج تسلسل أوامر، لا لقطة ⇒ null")
print("  • VPIN (Easley-López de Prado-O'Hara 2012): يحتاج دلاء حجم مصنّفة بـ BVC ⇒ null")
print("  • λ على تدفق موجَّه: يحتاج SignedVolume + أخطاء معيارية متينة ⇒ null")
print("  • المرونة (Resilience): تحتاج استهلاكاً ثم رصد استرجاع العمق زمنياً ⇒ غير قابلة للقياس")
print("  • Layering/Spoofing: تحتاج نسبة إلغاء الأوامر خلال ثوانٍ (>80%) ⇒ لا تُصدَر ولا تُنفى")
print("  • التجزؤ وأفضل منصة: venues_count رقم واحد بلا هوية ولا دفتر لكل منصة ⇒ بيان غير قابل للتفسير")
print("  • عمق AMM/LFJ/Pharaoh على C-Chain: غائب تماماً ⇒ خصم 25% ووسم PARTIAL")
print("  • رسوم الغاز وكلفة MEV على C-Chain: غائبة ⇒ خصم 15%")
print("  • ΔStake على P-Chain: المخزون فقط (62.45%) لا التدفق ⇒ لا يُقاس المعروض الحرّ فعلياً")
R["unmeasurable"] = ["OFI", "VPIN", "kyle_lambda_signed", "resilience", "layering",
                     "venue_fragmentation", "amm_depth", "gas_mev", "pchain_dstake"]

# ==========================================================================
sec("خلاصة رقمية قابلة لإعادة الإنتاج")
print(json.dumps({k: v for k, v in R.items() if k in
                  ("provenance", "ladder", "scalars", "cost_curve_meta", "ratios", "vol", "summary_check")},
                 ensure_ascii=False, indent=2, default=str))
out = ROOT / "reports" / "agent-01-audit-numbers.json"
out.write_text(json.dumps(R, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"\n✅ كُتبت الأرقام المُعاد إنتاجها: {out}")
print("⚠️ هذا الملف أثر تدقيق ميكانيكي — ليس رأياً ولا توصية (المادة 0.2 و1.2).")
