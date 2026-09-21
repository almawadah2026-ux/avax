"""
المكتبة الرياضية للديسك — كل الحسابات الفنية والكمية والإحصائية.

مكتوبة بـ Python القياسي فقط (بلا numpy/pandas) لتعمل في أي بيئة بلا تثبيت.

كل دالة هنا هي "أداة"، لا "قرار". الأداة تُنتج رقماً؛ الوكيل هو من يفسّره.
"""

from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence


# ==========================================================================
# 1. أدوات مساعدة أساسية
# ==========================================================================

def mean(xs: Sequence[float]) -> float:
    return statistics.fmean(xs) if xs else 0.0


def stdev(xs: Sequence[float], sample: bool = True) -> float:
    if len(xs) < 2:
        return 0.0
    return statistics.stdev(xs) if sample else statistics.pstdev(xs)


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b not in (0, 0.0) else default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pct_change(series: Sequence[float]) -> list[float]:
    """العوائد البسيطة."""
    return [safe_div(series[i] - series[i - 1], series[i - 1]) for i in range(1, len(series))]


def log_returns(series: Sequence[float]) -> list[float]:
    """العوائد اللوغاريتمية."""
    out = []
    for i in range(1, len(series)):
        if series[i - 1] > 0 and series[i] > 0:
            out.append(math.log(series[i] / series[i - 1]))
    return out


def correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    a, b = xs[-n:], ys[-n:]
    sa, sb = stdev(a), stdev(b)
    if sa == 0 or sb == 0:
        return 0.0
    ma, mb = mean(a), mean(b)
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    return clamp(cov / (sa * sb), -1.0, 1.0)


def percentile_rank(series: Sequence[float], value: float) -> float:
    """رتبة القيمة المئوية داخل السلسلة (0-100)."""
    if not series:
        return 50.0
    below = sum(1 for x in series if x <= value)
    return 100.0 * below / len(series)


# ==========================================================================
# 2. المتوسطات والاتجاه
# ==========================================================================

def sma(series: Sequence[float], period: int) -> float:
    if len(series) < period or period <= 0:
        return mean(series) if series else 0.0
    return mean(series[-period:])


def ema_series(series: Sequence[float], period: int) -> list[float]:
    """سلسلة EMA كاملة."""
    if not series:
        return []
    k = 2.0 / (period + 1.0)
    out = [series[0]]
    for price in series[1:]:
        out.append(price * k + out[-1] * (1 - k))
    return out


def ema(series: Sequence[float], period: int) -> float:
    s = ema_series(series, period)
    return s[-1] if s else 0.0


def wma(series: Sequence[float], period: int) -> float:
    if len(series) < period or period <= 0:
        return mean(series) if series else 0.0
    window = series[-period:]
    weights = list(range(1, period + 1))
    return sum(w * x for w, x in zip(weights, window)) / sum(weights)


def slope(series: Sequence[float], period: int = 20) -> float:
    """ميل الانحدار الخطي (OLS) على آخر `period` نقطة — مقسوم على المتوسط للتطبيع."""
    if len(series) < 3:
        return 0.0
    window = series[-period:] if len(series) >= period else list(series)
    n = len(window)
    xs = list(range(n))
    mx, my = mean(xs), mean(window)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    beta = sum((xs[i] - mx) * (window[i] - my) for i in range(n)) / denom
    return safe_div(beta, my) * 100.0  # نسبة مئوية لكل خطوة


def rsi(series: Sequence[float], period: int = 14) -> float:
    """مؤشر القوة النسبية — Wilder."""
    if len(series) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(series)):
        d = series[i] - series[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = mean(gains[:period]), mean(losses[:period])
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - (100.0 / (1.0 + rs))


def macd(series: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float]:
    if len(series) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    ef = ema_series(series, fast)
    es = ema_series(series, slow)
    line = [ef[i] - es[i] for i in range(len(series))]
    sig = ema_series(line, signal)
    return {
        "macd": line[-1],
        "signal": sig[-1],
        "hist": line[-1] - sig[-1],
    }


def bollinger(series: Sequence[float], period: int = 20, mult: float = 2.0) -> dict[str, float]:
    if len(series) < period:
        return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "pct_b": 50.0, "width": 0.0}
    window = series[-period:]
    m = mean(window)
    sd = stdev(window)
    upper, lower = m + mult * sd, m - mult * sd
    price = series[-1]
    pct_b = safe_div(price - lower, upper - lower, 0.5) * 100.0
    return {
        "upper": upper, "middle": m, "lower": lower,
        "pct_b": pct_b,
        "width": safe_div(upper - lower, m) * 100.0,
    }


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
    """متوسط المدى الحقيقي — Wilder."""
    n = min(len(highs), len(lows), len(closes))
    if n < 2:
        return 0.0
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return mean(trs)
    a = mean(trs[:period])
    for i in range(period, len(trs)):
        a = (a * (period - 1) + trs[i]) / period
    return a


def adx(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
    """مؤشر متوسط الاتجاه — نسخة مبسطة."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 2:
        return 0.0
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr_v = mean(trs[-period:]) or 1e-9
    pdi = 100.0 * safe_div(mean(plus_dm[-period:]), atr_v)
    mdi = 100.0 * safe_div(mean(minus_dm[-period:]), atr_v)
    denom = pdi + mdi
    return 100.0 * safe_div(abs(pdi - mdi), denom) if denom else 0.0


def vwap(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
         volumes: Sequence[float], period: int = 20) -> float:
    n = min(len(highs), len(lows), len(closes), len(volumes), period)
    if n == 0:
        return 0.0
    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(-n, 0)]
    vv = list(volumes[-n:])
    tv = sum(vv)
    return safe_div(sum(tp[i] * vv[i] for i in range(n)), tv) if tv else mean(tp)


def support_resistance(highs: Sequence[float], lows: Sequence[float], lookback: int = 60) -> dict[str, float]:
    """مستويات دعم ومقاومة بسيطة (Swing Highs/Lows) على نافذة."""
    h = list(highs[-lookback:]) if len(highs) >= lookback else list(highs)
    l = list(lows[-lookback:]) if len(lows) >= lookback else list(lows)
    if not h or not l:
        return {"resistance": 0.0, "support": 0.0}
    return {"resistance": max(h), "support": min(l)}


# ==========================================================================
# 3. التقلب
# ==========================================================================

def realized_vol(closes: Sequence[float], window: int = 30, annualize: bool = True) -> float:
    """التقلب المتحقق (انحراف معياري للعوائد اللوغاريتمية)."""
    rets = log_returns(closes)
    if len(rets) < 2:
        return 0.0
    window = min(window, len(rets))
    sd = stdev(rets[-window:])
    return sd * math.sqrt(365) * 100.0 if annualize else sd * 100.0


def ewma_vol(closes: Sequence[float], lam: float = 0.94, annualize: bool = True) -> float:
    """تقلب EWMA — الأساس البسيط لنموذج RiskMetrics/GARCH(1,1)."""
    rets = log_returns(closes)
    if len(rets) < 2:
        return 0.0
    var = rets[0] ** 2
    for r in rets[1:]:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var) * math.sqrt(365) * 100.0 if annualize else math.sqrt(var) * 100.0


def garch_11(closes: Sequence[float], omega: float = 1e-6,
             alpha: float = 0.09, beta: float = 0.88) -> dict[str, float]:
    """
    GARCH(1,1) بمعاملات مقيَّدة جاهزة (بديل عن التقدير الأمثل بلا مكتبات).
    sigma2_t = omega + alpha * eps_{t-1}^2 + beta * sigma2_{t-1}
    """
    rets = log_returns(closes)
    if len(rets) < 3:
        return {"sigma_daily": 0.0, "sigma_annual_pct": 0.0, "persistence": alpha + beta}
    var = mean([r * r for r in rets[:20]]) or 1e-8
    for r in rets:
        var = omega + alpha * (r * r) + beta * var
    return {
        "sigma_daily": math.sqrt(var),
        "sigma_annual_pct": math.sqrt(var) * math.sqrt(365) * 100.0,
        "persistence": alpha + beta,
    }


def volatility_regime(current_vol: float, vol_history: Sequence[float]) -> str:
    """تصنيف نظام التقلب مقارنةً بتاريخه."""
    if not vol_history:
        return "unknown"
    p = percentile_rank(vol_history, current_vol)
    if p >= 85:
        return "extreme"
    if p >= 65:
        return "high"
    if p >= 35:
        return "normal"
    return "low"


# ==========================================================================
# 4. الأساليب الكمية — Mean Reversion / Momentum / Hurst
# ==========================================================================

def zscore(series: Sequence[float], window: int = 30) -> float:
    """انحراف السعر عن متوسطه بوحدات الانحراف المعياري — أساس تداول العودة للمتوسط."""
    if len(series) < 5:
        return 0.0
    w = list(series[-window:]) if len(series) >= window else list(series)
    sd = stdev(w)
    return safe_div(w[-1] - mean(w), sd, 0.0)


def half_life_ou(series: Sequence[float]) -> float:
    """
    نصف عمر العودة للمتوسط وفق Ornstein-Uhlenbeck:
        dX_t = theta * (mu - X_t) dt + sigma dW_t
    يُقدَّر theta بانحدار تغيّر السعر على السعر المتأخر:
        delta_X_t = a + b * X_{t-1}
        half_life = -ln(2) / b
    """
    if len(series) < 20:
        return float("inf")
    xs = list(series[:-1])
    ys = [series[i + 1] - series[i] for i in range(len(series) - 1)]
    n = len(xs)
    mx, my = mean(xs), mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return float("inf")
    b = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom
    if b >= 0:
        return float("inf")  # لا عودة للمتوسط
    return -math.log(2) / b


def hurst_exponent(series: Sequence[float], max_lag: int = 40) -> float:
    """
    أُس هيرست بطريقة **تباين الزيادات المجمّعة** (Aggregated Variance):

        Var(X_{t+τ} − X_t) ∝ τ^(2H)   ⇒   H = ½ · slope( log Var , log τ )

    التفسير:
        H > 0.5 ⇒ سلسلة متجهة/مستمرة (Persistent / Trending)
        H ≈ 0.5 ⇒ سير عشوائي (Random Walk)
        H < 0.5 ⇒ عائدة للمتوسط (Mean-Reverting)

    ⚠️ **تصحيح موثّق (تدقيق):** التنفيذ السابق كان يستخدم تشتت **القيم المطلقة**
    للفروق، فأعطى نتائج مقلوبة: خط مستقيم تام ⇒ H = 0.5 (سير عشوائي!)، وموجة
    جيبية بحتة ⇒ H ≈ 0.76 (اتجاهي!). والسبب أن انحراف |Δ| يساوي صفراً لخط
    مستقيم (فيمرّ الفرع الافتراضي)، ويتشبّع في التذبذب. الطريقة الصحيحة
    (تباين الزيادات) تعطي: خط مستقيم ⇒ H = 1، سير عشوائي ⇒ H ≈ 0.5،
    وعملية OU ⇒ H < 0.5. وهذا مفتاح اختيار المدرسة في الوكيل الكمي (03).
    """
    n = len(series)
    if n < 60:
        return 0.5

    xs: list[float] = []
    ys: list[float] = []
    for lag in range(2, min(max_lag, n // 2)):
        diffs = [series[i] - series[i - lag] for i in range(lag, n)]
        var = mean([d * d for d in diffs])
        if var > 0:
            xs.append(math.log(lag))
            ys.append(math.log(var))

    if len(xs) < 3:
        return 0.5      # سلسلة ثابتة تماماً ⇒ الأُس غير معرّف

    mx, my = mean(xs), mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.5
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs))) / denom
    return clamp(slope / 2.0, 0.0, 1.0)


def momentum_score(closes: Sequence[float], lookbacks: Sequence[int] = (7, 30, 90)) -> dict[str, float]:
    """زخم متعدد الآجال مع درجات معيارية."""
    out: dict[str, float] = {}
    for lb in lookbacks:
        if len(closes) > lb:
            out[f"ret_{lb}d_pct"] = safe_div(closes[-1] - closes[-1 - lb], closes[-1 - lb]) * 100.0
        else:
            out[f"ret_{lb}d_pct"] = 0.0
    out["composite"] = mean([v for k, v in out.items() if k.startswith("ret_")])
    return out


def annualized_sharpe(returns_daily: Sequence[float], rf: float = 0.04) -> float:
    if len(returns_daily) < 5:
        return 0.0
    sd = stdev(returns_daily)
    if sd == 0:
        return 0.0
    excess = mean(returns_daily) - rf / 365.0
    return (excess / sd) * math.sqrt(365)


def sortino_ratio(returns_daily: Sequence[float], rf: float = 0.04) -> float:
    if len(returns_daily) < 5:
        return 0.0
    downside = [r for r in returns_daily if r < 0]
    dd = stdev(downside) if len(downside) > 1 else 0.0
    if dd == 0:
        return 0.0
    excess = mean(returns_daily) - rf / 365.0
    return (excess / dd) * math.sqrt(365)


def max_drawdown(equity: Sequence[float]) -> dict[str, float]:
    """أقصى تراجع من القمة."""
    if not equity:
        return {"max_dd_pct": 0.0, "peak": 0.0, "trough": 0.0}
    peak = equity[0]
    worst = 0.0
    peak_v = trough_v = equity[0]
    for v in equity:
        peak = max(peak, v)
        dd = safe_div(v - peak, peak) * 100.0
        if dd < worst:
            worst, peak_v, trough_v = dd, peak, v
    return {"max_dd_pct": worst, "peak": peak_v, "trough": trough_v}


def ulcer_index(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    dds = []
    for v in equity:
        peak = max(peak, v)
        dds.append((safe_div(v - peak, peak) * 100.0) ** 2)
    return math.sqrt(mean(dds))


def deflated_sharpe_ratio(sharpe_obs: float, n_trials: int, n_obs: int,
                          skew: float = 0.0, kurtosis: float = 3.0) -> float:
    """
    Deflated Sharpe Ratio — López de Prado (2014).

    ⚠️ **متطلبات الوحدات (إلزامية):** `sharpe_obs` يجب أن يكون **شارب لكل فترة**
    (غير مُسنَّن)، و`n_obs` عدد الفترات، و`skew`/`kurtosis` للعوائد لكل فترة.
    تمرير شارب مُسنَّن سنوياً مع عدد فترات يومية يُنتج رقماً غير قابل للمقارنة
    (كان يخرج DSR=1.0 في آنٍ مع انحلال شارب كامل — تناقض يكشف الخطأ).
    للتحويل: `SR_per_period = SR_annual / sqrt(periods_per_year)`.

    ⚠️ **حدّ معروف:** لا يُدرج عامل `sqrt(V[SR_n])` (تباين شارب عبر المحاولات)
    ⇒ يفترض V=1، وقيمة `exp_max` تعتمد على عدد المحاولات فقط. لذلك الرقم
    **تقديري** ولا يجوز تقديمه كحكم قطعي.

    القيمة المعادة: احتمال أن يكون الأداء حقيقياً لا وليد صدفة.
    """
    if n_obs < 3 or n_trials < 1:
        return 0.0
    e = 0.5772156649  # ثابت أويلر-ماسكيروني
    # القيمة المتوقعة لأقصى شارب تحت الفرض الصفري
    exp_max = ((1 - e) * _norm_ppf(1 - 1.0 / n_trials) +
               e * _norm_ppf(1 - 1.0 / (n_trials * math.e))) if n_trials > 1 else 0.0
    denom = math.sqrt(max(1e-9, 1 - skew * sharpe_obs + ((kurtosis - 1) / 4.0) * sharpe_obs ** 2))
    z = ((sharpe_obs - exp_max) * math.sqrt(n_obs - 1)) / denom
    return _norm_cdf(z)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """معكوس التوزيع الطبيعي المعياري — تقريب Acklam."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def sharpe_decay_ratio(sharpe_is: float, sharpe_oos: float) -> float:
    """
    نسبة انحلال شارب بين داخل العينة وخارجها:
        Decay = (SR_is − SR_oos) / |SR_is|

    ⚠️ **هذا ليس PBO** (Probability of Backtest Overfitting). كان مُسمّى
    `probability_backtest_overfitting` ومُنسوباً إلى López de Prado في الأدلة —
    وهو **ليس** مقياسه (PBO الحقيقي يحتاج CSCV على مسارات متعددة)، بل مجرد
    نسبة انحلال بسيطة. التسمية الخاطئة أخطر من غياب المقياس، لأنها تمنح
    ثقة زائفة بمقياس لا وجود له.
    """
    if sharpe_is <= 0:
        return 0.0
    return clamp(safe_div(sharpe_is - sharpe_oos, abs(sharpe_is), 1.0), 0.0, 1.0)


#: اسم قديم — محفوظ للتوافق؛ استخدم `sharpe_decay_ratio` وهو الاسم الصحيح.
probability_backtest_overfitting = sharpe_decay_ratio


# ==========================================================================
# 5. المحاكاة والتوزيعات
# ==========================================================================

def monte_carlo_terminal(prices: Sequence[float], days: int = 30, paths: int = 2000,
                         seed: int = 42) -> dict[str, float]:
    """محاكاة مونت كارلو للحركة الهندسية للأسعار — عوائد النسب المئوية."""
    import random as _random
    rng = _random.Random(seed)
    rets = log_returns(prices)
    if len(rets) < 5:
        return {"p05": 0.0, "p50": 0.0, "p95": 0.0, "prob_up": 0.5, "var95_pct": 0.0}
    mu, sd = mean(rets), stdev(rets)
    start = prices[-1]
    finals = []
    for _ in range(paths):
        p = start
        for _ in range(days):
            p *= math.exp(rng.gauss(mu, sd))
        finals.append(p)
    finals.sort()
    def q(p: float) -> float:
        idx = int(clamp(p, 0.0, 1.0) * (len(finals) - 1))
        return finals[idx]
    p05, p50, p95 = q(0.05), q(0.50), q(0.95)
    return {
        "p05": p05, "p50": p50, "p95": p95,
        "prob_up": sum(1 for f in finals if f > start) / len(finals),
        "var95_pct": safe_div(p05 - start, start) * 100.0,
        "expected_return_pct": safe_div(p50 - start, start) * 100.0,
    }


def value_at_risk(returns_daily: Sequence[float], confidence: float = 0.95) -> dict[str, float]:
    """
    VaR تاريخي + VaR بارامتري + CVaR (Expected Shortfall).
    القيم معادة كنسبة مئوية (سالبة = خسارة).
    """
    if len(returns_daily) < 20:
        return {"var_hist_pct": 0.0, "var_param_pct": 0.0, "cvar_pct": 0.0}
    s = sorted(returns_daily)
    idx = int((1 - confidence) * len(s))
    var_hist = s[max(0, idx)] * 100.0
    tail = s[: max(1, idx + 1)]
    cvar = mean(tail) * 100.0
    z = _norm_ppf(1 - confidence)
    var_param = (mean(returns_daily) + z * stdev(returns_daily)) * 100.0
    return {
        "var_hist_pct": var_hist,
        "var_param_pct": var_param,
        "cvar_pct": cvar,
        "confidence": confidence,
    }


# ==========================================================================
# 6. حجم المركز — Kelly والحدود
# ==========================================================================

def kelly_fraction(win_prob: float, payoff_ratio: float) -> float:
    """
    معيار كيلي:
        f* = p - (1-p)/b   حيث b = نسبة الربح/الخسارة
    الناتج ككسر من رأس المال (قد يكون سالباً ⇒ لا صفقة).
    """
    if payoff_ratio <= 0:
        return 0.0
    return win_prob - (1.0 - win_prob) / payoff_ratio


def fractional_kelly(win_prob: float, payoff_ratio: float, fraction: float = 0.5,
                     cap: float = 0.1) -> float:
    """كيلي مقيد — المادة 5.5: نصف كيلي كحد أقصى."""
    f = kelly_fraction(win_prob, payoff_ratio)
    return clamp(f * fraction, 0.0, cap)


def risk_of_ruin(win_prob: float, payoff_ratio: float, risk_fraction: float,
                 ruin_threshold: float = 0.5) -> float:
    """
    احتمال الوصول إلى حد الإفلاس قبل مضاعفة رأس المال (تقريب).
    ruin_threshold: النسبة من رأس المال التي تُعدّ إفلاساً.
    """
    if win_prob <= 0 or payoff_ratio <= 0 or risk_fraction <= 0:
        return 1.0
    edge = win_prob * payoff_ratio - (1 - win_prob)
    if edge <= 0:
        return 1.0
    r = safe_div(1 - win_prob, win_prob * payoff_ratio, 1.0)
    units = max(1.0, math.log(1.0 - ruin_threshold) / math.log(max(1e-6, 1 - risk_fraction)))
    return clamp(r ** units, 0.0, 1.0)


def position_size_by_risk(capital: float, risk_pct: float, entry: float, stop: float) -> dict[str, float]:
    """
    حجم المركز بطريقة المخاطرة الثابتة (Fixed Fractional):
        الحجم = (رأس المال × نسبة المخاطرة) / |الدخول − الوقف|
    """
    risk_amount = capital * (risk_pct / 100.0)
    per_unit = abs(entry - stop)
    if per_unit <= 0:
        return {"units": 0.0, "notional_usd": 0.0, "risk_amount_usd": risk_amount, "risk_per_unit": 0.0}
    units = risk_amount / per_unit
    return {
        "units": units,
        "notional_usd": units * entry,
        "risk_amount_usd": risk_amount,
        "risk_per_unit": per_unit,
        "notional_pct_of_capital": safe_div(units * entry, capital) * 100.0,
    }


def risk_parity_weights(vols: Sequence[float]) -> list[float]:
    """
    أوزان تكافؤ المخاطر: w_i ∝ 1/σ_i (مطبيع).
    بديل مبسّط عن HRP عند غياب مصفوفة ارتباط كاملة.
    """
    inv = [safe_div(1.0, v, 0.0) for v in vols]
    total = sum(inv)
    if total <= 0:
        n = len(vols) or 1
        return [1.0 / n] * n
    return [v / total for v in inv]


# ==========================================================================
# 7. بنية السوق — Microstructure
# ==========================================================================

def order_book_imbalance(bid_volume: float, ask_volume: float) -> float:
    """
    اختلال دفتر الأوامر (OBI):
        OBI = (V_bid − V_ask) / (V_bid + V_ask)  ∈ [−1, 1]
    """
    total = bid_volume + ask_volume
    return safe_div(bid_volume - ask_volume, total, 0.0)


def relative_spread_bps(best_bid: float, best_ask: float) -> float:
    mid = (best_bid + best_ask) / 2.0
    return safe_div(best_ask - best_bid, mid, 0.0) * 10_000.0


def amihud_illiquidity(returns_daily: Sequence[float], dollar_volumes: Sequence[float]) -> float:
    """
    مقياس أميهود لعدم السيولة:
        ILLIQ = mean( |r_t| / DollarVolume_t ) × 1e6
    الأعلى = أقل سيولة.
    """
    n = min(len(returns_daily), len(dollar_volumes))
    if n == 0:
        return 0.0
    vals = [safe_div(abs(returns_daily[i]), dollar_volumes[i], 0.0) for i in range(n)]
    return mean(vals) * 1e6


def depth_imbalance_pressure(bid_volume: float, ask_volume: float, total_volume: float) -> float:
    """
    ضغط اختلال العمق: |V_bid − V_ask| / V_total.

    ⚠️ **تصحيح موثّق (تدقيق):** كانت هذه الدالة مُسمّاة `vpin_proxy` وموصوفة
    بأنها «بديل مبسّط لمؤشر VPIN (تسمّم تدفق الأوامر)». وهي **ليست VPIN**:
    عند تمرير عمقي الدفتر تساوي حرفياً `abs(order_book_imbalance(...))` —
    أي مقياس عمق لحظي، لا تدفق أوامر منفّذ. VPIN الحقيقي يحتاج **تدفق صفقات
    مصنّفاً بالحجم** (Bulk Volume Classification) لا عمق دفتر.
    الاسم الآن يصف ما تحسبه فعلاً.
    """
    return safe_div(abs(bid_volume - ask_volume), total_volume, 0.0)


def kyle_lambda(price_changes: Sequence[float], signed_volumes: Sequence[float]) -> float:
    """
    لامبدا كايل — أثر السعر لكل وحدة حجم:
        ΔP = λ · SignedVolume
    تُقدَّر بانحدار بسيط. الأعلى = سوق أضعف عمقاً.
    """
    n = min(len(price_changes), len(signed_volumes))
    if n < 3:
        return 0.0
    x = list(signed_volumes[:n])
    y = list(price_changes[:n])
    mx, my = mean(x), mean(y)
    denom = sum((v - mx) ** 2 for v in x)
    if denom == 0:
        return 0.0
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / denom


def market_impact_sqrt(order_size: float, daily_volume: float, daily_vol: float,
                       y: float = 0.5) -> float:
    """
    قانون الجذر التربيعي لأثر السوق:
        Impact ≈ Y · σ_daily · sqrt(Q / V)
    يعيد الأثر ككسر (اضربه بـ100 للنسبة المئوية).
    """
    if daily_volume <= 0:
        return 0.0
    return y * daily_vol * math.sqrt(max(0.0, order_size) / daily_volume)


# ==========================================================================
# 8. أدوات التقييم والمعايرة
# ==========================================================================

def brier_score(forecasts: Sequence[tuple[float, int]]) -> float:
    """
    مؤشر برير لمعايرة الثقة:
        BS = (1/N) Σ (p_i − o_i)^2
    حيث p احتمال مُعلن (0-1) و o النتيجة الفعلية (1 نجاح، 0 فشل).
    الأقل أفضل. 0.25 = تخمين عشوائي.
    """
    if not forecasts:
        return 0.25
    return mean([(p - o) ** 2 for p, o in forecasts])


def weighted_evidence_score(
    opinions: Sequence["object"], weights: dict[str, float] | None = None
) -> dict[str, float]:
    """
    تجميع مرجّح لآراء الوكلاء — يستخدمه المنسّق.
    الترجيح: الثقة الصافية × معامل قوة الطبقة × وزن الوكيل التاريخي.
    """
    weights = weights or {}
    num = den = 0.0
    detail = []
    for op in opinions:
        if getattr(op, "abstain", False):
            continue
        tier = getattr(op, "best_tier", 4)
        tier_w = {1: 1.00, 2: 0.95, 3: 0.90, 4: 0.80, 5: 0.65, 6: 0.50, 7: 0.30}.get(tier, 0.5)
        agent_w = weights.get(getattr(op, "agent_id", ""), 1.0)
        conf = getattr(op, "net_confidence", getattr(op, "confidence", 0.0))
        sign = getattr(op, "directional_sign", 0)
        w = (conf / 100.0) * tier_w * agent_w
        num += sign * w
        den += w
        detail.append({
            "agent_id": getattr(op, "agent_id", "?"),
            "tier": tier, "tier_weight": tier_w, "agent_weight": agent_w,
            "confidence": round(conf, 1), "weight": round(w, 4), "sign": sign,
        })
    score = safe_div(num, den, 0.0)
    detail.sort(key=lambda d: -d["weight"])
    return {"score": round(score, 4), "total_weight": round(den, 4), "detail": detail}
