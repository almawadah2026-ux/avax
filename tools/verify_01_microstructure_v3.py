"""
الوكيل 01 — تدقيق بنية السوق على اللقطة الحيّة (source == "live").

الغرض: فصل ما هو **قياس سوقي** عمّا هو **مخرج مولّد** في ملف اللقطة،
لأن الفرق بينهما هو الفرق بين دليل طبقة 2 ودليل باطل (المادة 3.1/3.3).

المصادر المقروءة فعلياً (لا استشهاد بلا قراءة):
  • data/snapshot_full.json
  • src/avax_desk/data/live.py       (LiveFeed._from_coingecko)
  • src/avax_desk/data/models.py     (MarketSnapshot)
  • src/avax_desk/data/synthetic.py  (SyntheticFeed)
  • src/avax_desk/desks/base.py      (compute_features)
  • src/avax_desk/indicators.py      (amihud / kyle_lambda / market_impact_sqrt)
  • src/avax_desk/desks/knowledge.py (MarketStructureAgent)
  • tools/export_snapshot.py         (مولّد الدفتر والشمعات)

تشغيل:  python tools/verify_01_microstructure_v3.py
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path

try:                                   # وحدة التحكم على Windows قد تكون cp1256
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "snapshot_full.json"

J = json.loads(SNAP.read_text(encoding="utf-8"))
BARS = J["ohlcv_daily"]
OB = J["orderbook"]
CI = J["computed_indicators"]
DER = J["derivatives"]
META = J["_meta"]
N = len(BARS)

C = [b["c"] for b in BARS]
O = [b["o"] for b in BARS]
H = [b["h"] for b in BARS]
L = [b["l"] for b in BARS]
DV = [b["dv"] for b in BARS]
V = [b["v"] for b in BARS]

MID = OB["mid_price"]
DEPTH = OB["bid_depth_usd"]
R = {}


def sec(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def line(*a) -> None:
    print(*a)


# ==========================================================================
sec("1) من أين جاءت أرقام الدفتر؟ — إعادة إنتاج ثوابت المولّد")
# ==========================================================================
# live.py:157-161
spread_assumed_bps = 6.0                       # (1.0003 - 0.9997) * 1e4
bb_model = CI["price"] * 0.9997
ba_model = CI["price"] * 1.0003
depth_model = DV[-1] * 0.002                   # live.py:159-160
venues_model = 8                               # live.py:161 (عدد صريح)

line(f"best_bid   منشور {OB['best_bid']:.4f} | price*0.9997 = {bb_model:.4f} | Δ = {abs(OB['best_bid']-bb_model):.2e}")
line(f"best_ask   منشور {OB['best_ask']:.4f} | price*1.0003 = {ba_model:.4f} | Δ = {abs(OB['best_ask']-ba_model):.2e}")
line(f"bid_depth  منشور {OB['bid_depth_usd']:,.2f} | dv[-1]*0.002 = {depth_model:,.2f} | Δ = {abs(OB['bid_depth_usd']-depth_model):.2e}")
line(f"ask_depth  منشور {OB['ask_depth_usd']:,.2f} | dv[-1]*0.002 = {depth_model:,.2f} | Δ = {abs(OB['ask_depth_usd']-depth_model):.2e}")
line(f"spread_bps منشور {OB['spread_bps']} | مفترض ثابتاً {spread_assumed_bps} (price ±0.03%)")
line(f"venues     منشور {OB['venues_count']} | ثابت في live.py:161 = {venues_model}")
line(f"maker/taker fee منشور {OB['maker_fee_bps']}/{OB['taker_fee_bps']} | "
     f"قيم افتراضية في models.py:36-37 — لم تُجلَب من أي منصة")

# --- إعادة إنتاج سلّم المستويات (tools/export_snapshot.py:70-79) ---
LEVELS = 10
tick = MID * 0.0005
wsum = sum(1.0 / k for k in range(1, LEVELS + 1))
max_px_err = 0.0
max_sz_err = 0.0
max_diff_err = 0.0
ladder_bid_usd = 0.0
ladder_ask_usd = 0.0
for k, (bid, ask) in enumerate(zip(OB["bids"], OB["asks"]), start=1):
    px_b, px_a = MID - k * tick, MID + k * tick
    sz_b = (DEPTH * (1.0 / k) / wsum) / px_b
    sz_a = (DEPTH * (1.0 / k) / wsum) / px_a
    max_px_err = max(max_px_err, abs(px_b - bid["price"]), abs(px_a - ask["price"]))
    max_sz_err = max(max_sz_err, abs(sz_b - bid["size_avax"]), abs(sz_a - ask["size_avax"]))
    pub_diff = bid["size_avax"] - ask["size_avax"]
    max_diff_err = max(max_diff_err, abs((sz_b - sz_a) - pub_diff))
    ladder_bid_usd += bid["price"] * bid["size_avax"]
    ladder_ask_usd += ask["price"] * ask["size_avax"]

line(f"\nسلّم {LEVELS} مستويات: تباعد ثابت = {tick/MID*1e4:.4f} ن.أ | أوزان w_k=1/k مجرَّبة")
line(f"  أقصى خطأ سعري = {max_px_err:.2e} | أقصى خطأ حجمي = {max_sz_err:.4f} AVAX "
     f"(={max_sz_err/max(b['size_avax'] for b in OB['bids']):.2%})")
line(f"  فرق الحجم (bid-ask) ثابت = {OB['bids'][0]['size_avax']-OB['asks'][0]['size_avax']:.4f} AVAX "
     f"عند كل المستويات | أقصى خطأ في إعادة إنتاج الفرق = {max_diff_err:.2e}")
line(f"  Σ(px×sz) bids = {ladder_bid_usd:,.2f} | asks = {ladder_ask_usd:,.2f} | "
     f"مقابل المُعلن {OB['bid_depth_usd']:,.2f} / {OB['ask_depth_usd']:,.2f}")

R["provenance"] = {
    "source": META["source"],
    "best_bid_from_price_x0.9997": True,
    "depth_from_dv_x0.002": True,
    "spread_bps_hardcoded": OB["spread_bps"],
    "venues_hardcoded": OB["venues_count"],
    "ladder_max_px_err": max_px_err,
    "ladder_max_sz_err_avax": max_sz_err,
    "ladder_constant_size_gap_avax": OB["bids"][0]["size_avax"] - OB["asks"][0]["size_avax"],
    "venues_declared": OB["venues_count"],
}

# ==========================================================================
sec("2) سلامة سلسلة OHLCV — الشمعات مُشتقّة لا مقيسة")
# ==========================================================================
# live.py:142-149  highs = c*(1+0.6*rng), lows = c*(1-0.6*rng), rng=|c-prev|/prev
max_h_err = max_l_err = max_o_err = 0.0
for i, b in enumerate(BARS):
    prev = C[i - 1] if i else C[i]
    rng = abs(C[i] - prev) / prev if prev else 0.02
    max_h_err = max(max_h_err, abs(b["h"] - C[i] * (1 + rng * 0.6)))
    max_l_err = max(max_l_err, abs(b["l"] - C[i] * (1 - rng * 0.6)))
    max_o_err = max(max_o_err, abs(b["o"] - (C[i - 1] if i else C[i])))

bad_h = sum(1 for i in range(N) if H[i] < max(O[i], C[i]) - 1e-12)
bad_l = sum(1 for i in range(N) if L[i] > min(O[i], C[i]) + 1e-12)
bad = sum(1 for i in range(N)
          if H[i] < max(O[i], C[i]) - 1e-12 or L[i] > min(O[i], C[i]) + 1e-12)

line(f"إعادة إنتاج h/l من صيغة live.py: أقصى خطأ h = {max_h_err:.2e}, l = {max_l_err:.2e}, o = {max_o_err:.2e}")
line(f"  ⇒ المدى اليومي هو 1.2×|ΔClose| بالبناء، لا مدى سوقي.")
line(f"شمعات تخالف H ≥ max(O,C): {bad_h}/{N} | شمعات تخالف L ≤ min(O,C): {bad_l}/{N}")
line(f"شمعات غير صالحة بنيوياً (OHLC): {bad}/{N} = {bad/N:.1%}  ⇒ ATR/Bollinger/Corwin-Schultz مبنية على مدى مُختلق")

R["ohlcv_integrity"] = {
    "bars": N,
    "h_from_generator_max_err": max_h_err,
    "l_from_generator_max_err": max_l_err,
    "ohlc_invalid_bars": bad,
    "ohlc_invalid_pct": round(100 * bad / N, 2),
    "note": "h/l في الوضع الحيّ مُشتقّان من |ΔClose| — ليست قيماً سوقية",
}

# ==========================================================================
sec("3) λ المعلن — تدقيق كامل (المادة 3.1/3.3، وخطأ «λ بلا تشخيص»)")
# ==========================================================================
declared_kyle = CI["kyle_lambda"]  # من base.py:91-94


def ols(x, y):
    n = len(x)
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    b = sxy / sxx
    a = my - b * mx
    res = [y[i] - (a + b * x[i]) for i in range(n)]
    sse = sum(r * r for r in res)
    sst = sum((v - my) ** 2 for v in y)
    r2 = 1 - sse / sst if sst else 0.0
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 and sxx else float("nan")
    return b, a, r2, se


# إعادة إنتاج ما يفعله base.py حرفياً: ΔP مقابل حجم **غير موقَّع**
N60 = 60
dp = [C[i] - C[i - 1] for i in range(N - N60, N)]
dv60 = [DV[i] for i in range(N - N60, N)]
b60, a60, r2_60, se60 = ols(dv60, dp)
t60 = b60 / se60 if se60 else float("nan")

line(f"base.py:91-94 يستدعي kyle_lambda(ΔP, dollar_volumes) — أي مُنحدر OLS بـ**حجم غير موقَّع**.")
line(f"  المعلن  = {declared_kyle:.6e}")
line(f"  المُعاد = {b60:.6e} | R² = {r2_60:.6f} | SE = {se60:.3e} | t = {t60:.4f}")
line(f"  ⇒ الرقم **صادق حسابياً**: يُعاد إنتاجه من نفس الصيغة بفارق 4 منازل التقريب.")
line("  لكن التسمية خاطئة: λ كايل مُعرَّف على **صافي التدفق الموجَّه**، لا على حجم غير موقَّع.")
line("  المعامل هنا يقيس تلازم تغيّر السعر مع مستوى الحجم (R²=0.40 في نافذة 60 يوماً")
line("  تتضمّن انهياراً ثم طفرة بحجم قياسي) — وليس أثر سعر لكل وحدة تدفق صافٍ.")
line(f"  و SE غير متينة: لا Newey-West، والانحدار على 60 يوماً متغايرة التباين ومترابطة زمنياً.")

line("\nحساسية المعامل لاختيار النافذة والمحاذاة (نفس البيانات، نفس الكود):")
sens = {}
for w in (30, 45, 60, 90, 120, 180):
    row = {}
    for shift in (0, 1):
        x = [DV[i - shift] for i in range(N - w, N)]
        y = [C[i] - C[i - 1] for i in range(N - w, N)]
        bb, _, rr, _ = ols(x, y)
        row[f"shift{shift}"] = bb
    sens[w] = row
    line(f"  N={w:4d}  shift0 = {row['shift0']:+.4e}   shift1 = {row['shift1']:+.4e}")

signs = {math.copysign(1, v) for row in sens.values() for v in row.values()}
vals = [v for row in sens.values() for v in row.values()]
line(f"  ⇒ المدى عبر النوافذ/المحاذاة: [{min(vals):+.3e} , {max(vals):+.3e}] — "
     f"الإشارة {'ثابتة' if len(signs)==1 else 'متقلّبة'} ({len(signs)} إشارة).")
line(f"  تذبذب ×{max(vals)/min(vals):.2f} بين نوافذ متجاورة ⇒ التقدير حسّاس للاختيار، ولا يُبلَّغ عنه فترة ثقة.")
line("  λ كايل الحقيقي يحتاج تدفقاً موقَّعاً (شراء−بيع)؛ الملف لا يحوي أي صفقة (Trades) ولا تصنيف BVC.")

R["lambda_audit"] = {
    "kyle_declared": declared_kyle,
    "kyle_recomputed_60d": b60,
    "r2": r2_60,
    "se": se60,
    "t": t60,
    "unsigned_regressor": True,
    "sign_consistent": len(signs) == 1,
    "range": [min(vals), max(vals)],
    "verdict": ("يُعاد إنتاجه بدقة من الصيغة، لكنه ليس لامبدا كايل: مُنحدر ΔP على حجم "
                "غير موقَّع بلا صافي تدفق، وبلا أخطاء معيارية متينة (Newey-West)"),
}

# ==========================================================================
sec("4) أميهود — القياس الوحيد القابل لإعادة الإنتاج من بيانات حقيقية")
# ==========================================================================
amihud = {}
for w in (30, 60, 90, 180, 365):
    vals = [abs(math.log(C[i] / C[i - 1])) / (DV[i] / 1e6) for i in range(N - w, N)]
    amihud[w] = st.mean(vals)
line("النافذة   amihud_x1e6      الأمر   أثر مقدَّر (ن.أ)")
impacts = {}
for w, a in amihud.items():
    std = a / 1e6
    imp = {q: std * q * 1e4 for q in (1e6, 3e6, 17.6e6, 75.9e6)}
    impacts[w] = imp
    line(f"{w:6d}   {a:.6e}    $1M={imp[1e6]:6.2f}  $3M={imp[3e6]:6.2f}  "
         f"$17.6M={imp[17.6e6]:6.2f}  $75.9M={imp[75.9e6]:6.2f}")
line(f"المعلن في اللقطة = {CI['amihud_illiquidity']:.10e} (نافذة 90 يوماً، اصطلاح الكود = ×1e6)")
line(f"  إعادة الإنتاج 90 يوماً = {amihud[90]:.10e} | فرق نسبي = "
     f"{abs(amihud[90]-CI['amihud_illiquidity'])/CI['amihud_illiquidity']:.2e} (تقريب 4 منازل في الشمعات)")

R["amihud"] = {"by_window": amihud, "declared": CI["amihud_illiquidity"],
               "reproduced_90d": amihud[90], "impact_bps": {str(k): v for k, v in impacts.items()}}

# ==========================================================================
sec("5) مقاييس لا يمكن حسابها — تُعلن ولا تُقرَّب (المادة 0.4/9.1)")
# ==========================================================================
# Roll(1984): S = 2*sqrt(-Cov(ΔP_t, ΔP_{t-1}))
for w in (60, 90, 120):
    d = [C[i] - C[i - 1] for i in range(N - w, N)]
    m = st.mean(d)
    cov = sum((d[i] - m) * (d[i - 1] - m) for i in range(1, len(d))) / (len(d) - 1)
    verdict = f"S = {2*math.sqrt(-cov)/MID*1e4:.2f} ن.أ" if cov < 0 else "غير قابل للتقدير (تغاير ذاتي موجب)"
    line(f"Roll {w} يوماً: Cov = {cov:+.6f} ⇒ {verdict}")
line("\nلم يُقدَّم أي مصدر لهذه المدخلات الإلزامية/الاختيارية:")
unmeasurable = [
    "OFI          — يحتاج تحديثات دفتر L2/L3 مُوقَّتة (لا توجد؛ لقطة واحدة)",
    "VPIN         — يحتاج تدفق صفقات مصنَّفاً (BVC)؛ دلو ADV/50 غير ممكن",
    "kyle_lambda_signed — يحتاج تدفقاً موقَّعاً من صفقات",
    "resilience   — يحتاج زمن استرجاع العمق بعد Sweep",
    "layering/spoofing — يحتاج نسبة إلغاء الأوامر (لا توجد)",
    "venue_fragmentation — venues_count=8 رقم صريح بلا تفصيل منصات",
    "amm_depth    — لا عمق LFJ/Pharaoh ولا Subgraph على C-Chain",
    "gas_mev      — لا رسوم غاز ولا قياس MEV",
    "pchain_dstake— لا نسبة استيكينج ولا عدد مُدقّقين",
    "bridge_flow  — bridge_netflow_7d_usd في missing_fields",
]
for u in unmeasurable:
    line("  ✗ " + u)

# ==========================================================================
sec("6) حجم التداول: نظام متغير + حد المادة 5.3")
# ==========================================================================
adv30 = st.mean(DV[-30:])
adv90 = st.mean(DV[-90:])
adv_pre = st.mean(DV[-60:-30])
dv_last = DV[-1]
line(f"آخر شمعة      = {dv_last/1e6:,.1f}M$")
line(f"متوسط 3 أيام   = {st.mean(DV[-3:])/1e6:,.1f}M$")
line(f"متوسط 7 أيام   = {st.mean(DV[-7:])/1e6:,.1f}M$")
line(f"متوسط 30 يوماً = {adv30/1e6:,.1f}M$   ⇒ الحد 5% = {adv30*0.05/1e6:,.1f}M$")
line(f"متوسط 90 يوماً = {adv90/1e6:,.1f}M$   ⇒ الحد 5% = {adv90*0.05/1e6:,.1f}M$")
line(f"30 يوماً قبل الطفرة = {adv_pre/1e6:,.1f}M$  ⇒ الحد 5% = {adv_pre*0.05/1e6:,.1f}M$")
line(f"  آخر شمعة / ما قبل الطفرة = {dv_last/adv_pre:.2f}×  ⇒ أي حدّ 5% محسوب على آخر شمعة يتضخّم بنفس النسبة")
line(f"إجمالي عمق الدفتر المُعلن = {OB['total_depth_usd']/1e6:,.2f}M$ = "
     f"{OB['total_depth_usd']/dv_last*100:.3f}% من آخر شمعة (0.2% لكل جهة — ثابت المولّد)")
line(f"الحد 5% (30 يوماً) ÷ العمق الكلي = {adv30*0.05/OB['total_depth_usd']:.1f}×")

R["liquidity_capacity"] = {
    "dv_last": dv_last, "adv7": st.mean(DV[-7:]), "adv30": adv30, "adv90": adv90,
    "adv_pre_spike_30d": adv_pre,
    "cap5_from_adv30": adv30 * 0.05,
    "cap5_from_dv_last": dv_last * 0.05,
    "cap5_from_pre_spike": adv_pre * 0.05,
    "declared_total_depth": OB["total_depth_usd"],
    "depth_pct_of_last_dv": OB["total_depth_usd"] / dv_last * 100,
}

# ==========================================================================
sec("7) منحنى الكلفة — **شرطي** على سلّم مولَّد (لا قياس سوقي)")
# ==========================================================================
bids, asks = OB["bids"], OB["asks"]
max_ask_usd = sum(a["price"] * a["size_avax"] for a in asks)
max_bid_usd = sum(b["price"] * b["size_avax"] for b in bids)


def walk(levels, notional):
    rem, cost, qty = notional, 0.0, 0.0
    for lv in levels:
        if rem <= 0:
            break
        lv_usd = lv["price"] * lv["size_avax"]
        take = min(rem, lv_usd)
        cost += take
        qty += take / lv["price"]
        rem -= take
    if rem > 1e-6:
        return None
    return (cost / qty - MID) / MID * 1e4, qty


line(f"سقف الكنس (شرطي): شراء {max_ask_usd:,.0f}$ | بيع {max_bid_usd:,.0f}$ — وهو 0.2% من آخر شمعة بالبناء")
line(f"{'الأمر':>12} {'شراء ن.أ':>10} {'AVAX':>12} | {'بيع ن.أ':>10}")
curve = {}
for q in (100_000, 250_000, 500_000, 1_000_000, 1_500_000, 2_000_000, 2_500_000, 3_000_000, 3_030_000):
    bu = walk(asks, q)
    se = walk(bids, q)
    curve[q] = {"buy": bu[0] if bu else None, "sell": se[0] if se else None}
    line(f"{q:>12,} {(f'{bu[0]:10.2f}' if bu else '   UNFILL'):>10} "
         f"{(f'{bu[1]:12,.0f}' if bu else '           -'):>12} | "
         f"{(f'{se[0]:10.2f}' if se else '   UNFILL'):>10}")
line(f"\nنصف السبريد المُعلن = {OB['spread_bps']/2:.2f} ن.أ لكن أول مستوى منشور على 5.00 ن.أ")
line( "  ⇒ فراغ 2.00 ن.أ بين أفضل سعر معروض وأول حجم منشور (live.py يستخدم ±0.03% والسلّم ±0.05%).")
line(f"تكلفة الذهاب والعودة على كنس كامل: {curve[3030000]['buy']:.1f} + "
     f"{abs(curve[3030000]['sell']):.1f} + 2×{OB['taker_fee_bps']:.0f} رسوم = "
     f"{curve[3030000]['buy']+abs(curve[3030000]['sell'])+2*OB['taker_fee_bps']:.1f} ن.أ")

# مقارنة النماذج الثلاثة
vol30 = CI["vol_30d_annual_pct"] / 100
sig_d = vol30 / math.sqrt(365)
line(f"\nمقارنة النماذج (أثر فقط، بلا رسوم): تقلب يومي مُحقَّق = {sig_d*100:.3f}%")
line(f"{'الأمر':>12} {'سلّم مُولَّد':>12} {'قانون الجذر':>12} {'أميهود(90)':>12}")
am90 = amihud[90] / 1e6
model_cmp = {}
for q in (500_000, 1_000_000, 3_000_000, 17_600_000):
    lad = walk(asks, q)
    sqrt_law = 0.5 * sig_d * math.sqrt(q / DV[-1]) * 1e4
    am = am90 * q * 1e4
    model_cmp[q] = {"ladder": lad[0] if lad else None, "sqrt_law": sqrt_law, "amihud": am}
    line(f"{q:>12,} {(f'{lad[0]:12.2f}' if lad else '     UNFILL'):>12} {sqrt_law:12.2f} {am:12.2f}")

R["cost_curve_conditional"] = {
    "caveat": "السلّم مخرج مولّد (وأوزان 1/k وعمق 0.2%×DV وتباعد 5 ن.أ) — المنحنى شرطي لا مقيس",
    "curve": {str(k): v for k, v in curve.items()},
    "max_sweep_buy_usd": max_ask_usd,
    "max_sweep_sell_usd": max_bid_usd,
    "touch_vs_l1_gap_bps": 2.0,
    "model_comparison": {str(k): v for k, v in model_cmp.items()},
}

# ==========================================================================
sec("8) خلاصة الحكم")
# ==========================================================================
admissible = {
    "closes": "مقيس (CoinGecko) — طبقة 2",
    "dollar_volumes": "مقيس (CoinGecko total_volumes) — طبقة 2",
    "market_cap/supply": "مقيس (CoinGecko) — طبقة 2",
    "realized_vol_close_to_close": "مشتق من أسعار مقيسة — طبقة 3",
    "amihud_illiquidity": "مشتق من أسعار+أحجام مقيسة — طبقة 3",
    "spread_bps": "مولَّد (price±0.03%) — غير مقيس",
    "bid/ask_depth_usd": "مولَّد (dv[-1]×0.002) — غير مقيس",
    "order_book_imbalance": "صفر بالبناء — غير مقيس",
    "venues_count": "ثابت 8 — غير مقيس",
    "maker/taker_fee_bps": "افتراضي في الكود — غير مقيس",
    "orderbook ladder": "مولَّد (mid, depth, 5 ن.أ, 1/k) — غير مقيس",
    "highs/lows/atr/bollinger": "مولَّد من |ΔClose| — غير مقيس",
    "kyle_lambda": "مُعاد إنتاجه بدقة لكنه ليس λ كايل (حجم غير موقَّع، لا Newey-West) — غير صالح لتسعير الأثر",
}
for k, v in admissible.items():
    line(f"  {k:32s} : {v}")

R["admissibility"] = admissible
R["unmeasurable"] = unmeasurable

out = ROOT / "reports" / "agent-01-audit-numbers-live.json"
out.write_text(json.dumps(R, indent=2, ensure_ascii=False), encoding="utf-8")
sec(f"كُتب: {out.relative_to(ROOT)}")
