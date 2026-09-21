"""
طبقة المعرفة — الوكلاء 01 إلى 08.

هؤلاء **لا يقررون**. مهمتهم تحويل البيانات الخام إلى أدلة مصنّفة (المادة 3.1)
ورأي مُعلَّل بشرط إبطال (المادة 2.2). أي وكيل هنا يصدر أمر تنفيذ = خرق المادة 1.2.
"""

from __future__ import annotations

from .. import indicators as ind
from ..contracts import AgentOpinion, Authority, Layer, Strength
from .base import AgentContext, BaseAgent


# ==========================================================================
# 01 — بنية السوق
# ==========================================================================

class MarketStructureAgent(BaseAgent):
    """يقرأ السيولة والعمق واختلال دفتر الأوامر — لا يقرأ الاتجاه."""

    id, name_ar, name_en = "01", "وكيل بنية السوق", "Market Structure Agent"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "microstructure"
    horizon = "ساعات إلى 3 أيام"
    file = "agents/01-market-structure.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        s = ctx.snapshot
        src = self.source_tag(ctx)

        spread = f["spread_bps"]
        obi = f["obi"]
        depth = f["depth_usd"]
        dvp = f["depth_vs_volume_pct"]
        amihud = f["amihud"]
        kyle = f["kyle_lambda"]
        venues = s.venues
        # إن كان العمق **مُقدَّراً** لا مقيساً، فدليله مشتق لا سوقي (المادة 3.1)
        depth_kind = "derived" if s.meta.get("depth_estimated") else "market"
        depth_strength = (Strength.MEDIUM.value if depth_kind == "market"
                          else Strength.LOW.value)
        depth_note = (" — **تقدير من الحجم لا قياس L2**"
                      if s.meta.get("depth_estimated") else "")

        # جودة السيولة: سبريد ضيق + عمق كافٍ + تعدد منصات
        spread_quality = ind.clamp(8.0 / max(spread, 0.5), 0.25, 1.0)
        depth_quality = ind.clamp(dvp / 0.30, 0.25, 1.0)
        venue_quality = ind.clamp(venues / 8.0, 0.3, 1.0)
        liquidity_quality = (spread_quality + depth_quality + venue_quality) / 3.0

        trend_confirm = ind.clamp(f["slope20"] / 2.0, -1.0, 1.0)
        raw = 0.70 * obi + 0.30 * trend_confirm
        score = raw * liquidity_quality

        # تكلفة أثر سوقي لطلب افتراضي بحجم 1% من الحجم اليومي
        impact = ind.market_impact_sqrt(
            order_size=0.01 * s.volume_24h_usd,
            daily_volume=max(1.0, s.volume_24h_usd),
            daily_vol=max(0.005, f["vol_30d_ann_pct"] / 100.0 / (365 ** 0.5)),
        )

        evidence = [
            self.ev(ctx, f"نسبة السبريد النسبي {spread:.2f} نقطة أساس عند أفضل عرض/طلب",
                    f"{src}/orderbook", "market", Strength.HIGH.value, spread),
            self.ev(ctx, f"اختلال دفتر الأوامر OBI = {obi:+.3f} (موجب = ضغط شراء)",
                    f"{src}/orderbook-depth", "market", Strength.HIGH.value, obi),
            self.ev(ctx, f"عمق إجمالي {depth/1e6:.2f}M$ = {dvp:.3f}% من الحجم اليومي{depth_note}",
                    f"{src}/orderbook-depth", depth_kind, depth_strength, dvp),
            self.ev(ctx, f"عدد المنصات المتاحة {venues} — درجة تجزؤ السيولة",
                    f"{src}/venues", "market", Strength.LOW.value, float(venues)),
            self.ev(ctx, f"مقياس أميهود لعدم السيولة = {amihud:.4f}",
                    "derived/amihud-90d", "derived", Strength.MEDIUM.value, amihud),
            self.ev(ctx, f"لامبدا كايل (أثر السعر لكل وحدة حجم) = {kyle:.3e}",
                    "derived/kyle-lambda-60d", "derived", Strength.MEDIUM.value, kyle),
        ]

        thesis = (
            f"بنية السوق {'مؤيدة للصعود' if score > 0.08 else ('مؤيدة للهبوط' if score < -0.08 else 'محايدة')} "
            f"بدرجة {score:+.3f}؛ جودة السيولة {liquidity_quality:.2f}، وأثر سوقي مقدّر "
            f"{impact*100:.3f}% لطلب بحجم 1% من الحجم اليومي."
        )
        invalidation = (
            f"يُبطل هذا الرأي إذا انقلب OBI إلى ما دون {-obi:+.3f}، أو اتسع السبريد فوق "
            f"{max(12.0, spread*2):.2f} نقطة أساس، أو هبط العمق تحت {depth*0.6/1e6:.2f}M$."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: دفتر الأوامر بيانات لحظية سريعة التغير (High Frequency)، "
            "وقد يكون الاختلال المرصود ناتجاً عن Spoofing أو Layering لا عن طلب حقيقي. "
            "كما أن OBI لا يعطي معلومة عن الاتجاه على أفق يتجاوز ساعات."
        )
        return self.make(ctx, score, thesis, evidence, invalidation, dissent,
                         metrics={"liquidity_quality": round(liquidity_quality, 4),
                                  "obi": round(obi, 4), "spread_bps": round(spread, 3),
                                  "depth_usd": depth, "impact_1pct": round(impact, 6),
                                  "venues": venues,
                                  "note": "بيانات لحظية — تسقط قيمتها خلال ساعات"})


# ==========================================================================
# 02 — التحليل الفني
# ==========================================================================

class TechnicalAgent(BaseAgent):
    """مدرسة الشارت: الاتجاه، الزخم، التطرف، البنية السعرية."""

    id, name_ar, name_en = "02", "وكيل التحليل الفني", "Technical Analysis Agent"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "technical"
    horizon = "أيام إلى أسابيع"
    file = "agents/02-technical-analysis.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        src = self.source_tag(ctx)
        price, e20, e50, e200 = f["price"], f["ema20"], f["ema50"], f["ema200"]
        rsi_v, macd_v, bb, adx_v = f["rsi14"], f["macd"], f["bb"], f["adx14"]
        atr_v, vwap_v, slope_v = f["atr14"], f["vwap20"], f["slope20"]

        # -- البنية الاتجاهية (Dow: قمم وقيعان متصاعدة) --------------------
        align = 0.0
        align += 0.25 if price > e20 else -0.25
        align += 0.25 if e20 > e50 else -0.25
        align += 0.25 if price > e200 else -0.25
        align += 0.25 if macd_v["hist"] > 0 else -0.25
        trend_score = align  # -1 .. +1

        # -- قوة الاتجاه (ADX يبوّب الثقة لا الاتجاه) -----------------------
        adx_gate = ind.clamp(adx_v / 40.0, 0.0, 1.0)

        # -- الزخم ----------------------------------------------------------
        momentum_score = ind.clamp(ind.safe_div(macd_v["hist"], max(1e-9, atr_v * 0.5)), -1.0, 1.0)

        # -- التطرف (RSI و Bollinger) — نزعة عكسية ---------------------------
        rsi_score = ind.clamp((50.0 - rsi_v) / 45.0, -1.0, 1.0)
        bb_score = ind.clamp((50.0 - bb["pct_b"]) / 50.0, -1.0, 1.0)

        # -- موقع السعر من VWAP ---------------------------------------------
        vwap_score = 1.0 if price > vwap_v else -1.0

        score = (
            0.45 * trend_score * adx_gate
            + 0.20 * momentum_score
            + 0.15 * rsi_score
            + 0.12 * bb_score
            + 0.08 * vwap_score
        )
        score = ind.clamp(score, -1.0, 1.0)

        sr = f["sr"]
        dist_res = ind.safe_div(sr["resistance"] - price, price) * 100.0
        dist_sup = ind.safe_div(price - sr["support"], price) * 100.0

        evidence = [
            self.ev(ctx, f"محاذاة المتوسطات: السعر {price:.3f} / EMA20 {e20:.3f} / EMA50 {e50:.3f} "
                         f"/ EMA200 {e200:.3f}", f"{src}/ohlcv", "technical", Strength.MEDIUM.value, trend_score),
            self.ev(ctx, f"RSI(14) = {rsi_v:.1f}", f"{src}/ohlcv", "technical", Strength.MEDIUM.value, rsi_v),
            self.ev(ctx, f"MACD histogram = {macd_v['hist']:+.4f} (خط {macd_v['macd']:+.4f} / إشارة {macd_v['signal']:+.4f})",
                    f"{src}/ohlcv", "technical", Strength.MEDIUM.value, macd_v["hist"]),
            self.ev(ctx, f"ADX(14) = {adx_v:.1f} — قوة الاتجاه", f"{src}/ohlcv", "technical", Strength.MEDIUM.value, adx_v),
            self.ev(ctx, f"موقع Bollinger %B = {bb['pct_b']:.1f}% بعرض نطاق {bb['width']:.2f}%",
                    f"{src}/ohlcv", "technical", Strength.LOW.value, bb["pct_b"]),
            self.ev(ctx, f"المسافة إلى المقاومة {dist_res:.2f}% وإلى الدعم {dist_sup:.2f}%",
                    "derived/swing-levels-60d", "derived", Strength.LOW.value, dist_res),
        ]

        thesis = (
            f"البنية الفنية {('صاعدة' if score > 0.08 else 'هابطة' if score < -0.08 else 'عرضية')} "
            f"بدرجة {score:+.3f}؛ محاذاة المتوسطات {trend_score:+.2f} مع ADX {adx_v:.1f} "
            f"(بوابة اتجاه {adx_gate:.2f})، والزخم {momentum_score:+.2f}."
        )
        invalidation = (
            f"يُبطل هذا الرأي عند إغلاق يومي دون EMA50 ({e50:.3f}) إن كان الرأي صاعداً، "
            f"أو فوق EMA50 إن كان هابطاً، مع تحوّل MACD histogram إلى الإشارة المعاكسة."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: كل مؤشرات هذه الطبقة مشتقة من السعر نفسه (طبقة 4 في هرمية "
            "الأدلة)، فهي **وصف لما حدث لا تنبؤ بما سيحدث**، وتتحول إلى ضجيج في الأسواق العرضية. "
            "درجة ADX المنخفضة تعني أن أي إشارة اتجاهية هنا غير موثوقة."
        )
        notes = []
        if adx_v < 20:
            notes.append("⚠️ ADX < 20 — سوق بلا اتجاه؛ إشارات المتوسطات ضعيفة القيمة هنا")
        if rsi_v > 75:
            notes.append("⚠️ RSI في منطقة تشبع شرائي — خطر تصحيح قصير")
        if rsi_v < 25:
            notes.append("⚠️ RSI في منطقة تشبع بيعي — احتمال ارتداد")

        return self.make(ctx, score, thesis, evidence, invalidation, dissent,
                         metrics={"trend_score": round(trend_score, 3), "adx": round(adx_v, 2),
                                  "rsi": round(rsi_v, 2), "macd_hist": macd_v["hist"],
                                  "atr_pct": round(f["atr_pct"], 3),
                                  "dist_resistance_pct": round(dist_res, 3),
                                  "dist_support_pct": round(dist_sup, 3)},
                         notes=notes)


# ==========================================================================
# 03 — الوكيل الكمي
# ==========================================================================

class QuantitativeAgent(BaseAgent):
    """النظام الإحصائي: نظام السوق، الزخم، العودة للمتوسط، نصف العمر."""

    id, name_ar, name_en = "03", "الوكيل الكمي", "Quantitative Agent"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "stats"
    horizon = "أيام إلى أسابيع"
    file = "agents/03-quantitative.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        src = self.source_tag(ctx)

        hurst = f["hurst"]
        z30, z90 = f["zscore30"], f["zscore90"]
        hl = f["half_life_days"]
        mom = f["momentum"]
        vol_reg = f["vol_regime"]

        mom_score = ind.clamp(mom["composite"] / 20.0, -1.0, 1.0)
        mr_score = ind.clamp(-z30 / 2.0, -1.0, 1.0)

        # النظام الإحصائي يحدد أي مدرسة تُرجَّح
        if hurst >= 0.55:
            regime = "اتجاهي (Trending)"
            score = 0.80 * mom_score + 0.20 * mr_score
        elif hurst <= 0.45:
            regime = "عائد للمتوسط (Mean-Reverting)"
            score = 0.80 * mr_score + 0.20 * mom_score
        else:
            regime = "عشوائي (Random Walk)"
            score = 0.50 * mom_score + 0.50 * mr_score

        # عقوبة عدم اليقين: نظام عشوائي + تقلب متطرف ⇒ خفض حجم الإشارة
        if regime.startswith("عشوائي"):
            score *= 0.55
        if vol_reg in ("high", "extreme"):
            score *= 0.80

        score = ind.clamp(score, -1.0, 1.0)
        hl_text = "لا عودة للمتوسط" if hl == float("inf") else f"{hl:.1f} يوم"

        evidence = [
            self.ev(ctx, f"أُس هيرست H = {hurst:.3f} ⇒ نظام {regime}",
                    "derived/hurst-40lag", "derived", Strength.HIGH.value, hurst),
            self.ev(ctx, f"Z-Score(30) = {z30:+.2f} و Z-Score(90) = {z90:+.2f}",
                    "derived/zscore", "derived", Strength.HIGH.value, z30),
            self.ev(ctx, f"نصف عمر العودة للمتوسط (Ornstein-Uhlenbeck) = {hl_text}",
                    "derived/ou-half-life", "derived", Strength.MEDIUM.value,
                    None if hl == float("inf") else hl),
            self.ev(ctx, f"الزخم المركّب (7/30/90 يوم) = {mom['composite']:+.2f}%",
                    "derived/momentum-composite", "derived", Strength.MEDIUM.value, mom["composite"]),
            self.ev(ctx, f"التقلب المتحقق 30 يوم {f['vol_30d_ann_pct']:.1f}% — نظام {vol_reg}",
                    "derived/realized-vol", "derived", Strength.HIGH.value, f["vol_30d_ann_pct"]),
            self.ev(ctx, f"GARCH(1,1): تقلب سنوي {f['garch']['sigma_annual_pct']:.1f}% "
                         f"باستمرارية {f['garch']['persistence']:.3f}",
                    "derived/garch11", "derived", Strength.MEDIUM.value, f["garch"]["sigma_annual_pct"]),
        ]

        thesis = (
            f"النظام الإحصائي الحالي **{regime}** (H={hurst:.3f})، والدرجة المركّبة {score:+.3f}؛ "
            f"نصف عمر العودة للمتوسط {hl_text}، والتقلب السنوي {f['vol_30d_ann_pct']:.1f}%."
        )
        invalidation = (
            f"يُبطل هذا الرأي إذا خرج H خارج [{max(0.0,hurst-0.08):.2f}, {min(1.0,hurst+0.08):.2f}] "
            f"مما يغيّر النظام المُرجَّح، أو إذا تجاوز Z-Score(30) ±3 (حدث نادر ⇒ انكسار النموذج)."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: أُس هيرست المُقدَّر على نافذة واحدة غير مستقر، وتقدير OU "
            "يفترض ثبات المتوسط وهو افتراض مكسور في الأصول الرقمية. كما أن GARCH بمعاملات "
            "جاهزة (لا مُقدَّرة) يعطي تقلباً تقريبياً لا تنبؤاً."
        )
        notes = []
        if hl == float("inf"):
            notes.append("ℹ️ لا عودة للمتوسط — استراتيجيات Mean Reversion غير مناسبة حالياً")
        if vol_reg == "extreme":
            notes.append("⚠️ نظام تقلب متطرف — خفض حجم المركز إلزامي (المادة 9.3 أصفر)")
        if abs(z30) > 2.5:
            notes.append("⚠️ انحراف معياري > 2.5 — احتمال ارتداد أو انكسار بنيوي")

        return self.make(ctx, score, thesis, evidence, invalidation, dissent,
                         metrics={"hurst": round(hurst, 4), "regime": regime,
                                  "zscore30": round(z30, 3), "zscore90": round(z90, 3),
                                  "half_life_days": None if hl == float("inf") else round(hl, 2),
                                  "momentum_composite_pct": round(mom["composite"], 3),
                                  "sharpe_90d": round(f["sharpe_90d"], 3),
                                  "vol_regime": vol_reg},
                         notes=notes)


# ==========================================================================
# 04 — الماكرو والأساسيات
# ==========================================================================

class MacroFundamentalAgent(BaseAgent):
    """السياق الكلي + اقتصاد الرمز + تقييم الشبكة."""

    id, name_ar, name_en = "04", "وكيل الماكرو والأساسيات", "Macro & Fundamentals Agent"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "macro"
    horizon = "أسابيع إلى أشهر"
    file = "agents/04-macro-fundamental.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        s = ctx.snapshot
        src = self.source_tag(ctx)

        # -- غياب المدخلات الماكروية = امتناع لا اتجاه (المادتان 3.3 و9.1) --
        macro_core = ("dxy_change_7d_pct", "real_yield_10y", "unlock_pct_next_30d")
        missing_macro = [c for c in macro_core if c in (s.missing_fields or [])]
        if len(missing_macro) >= 2:
            return AgentOpinion.abstain_opinion(
                self.id, self.name_ar,
                "مدخلات ماكروية أساسية غائبة: " + "، ".join(missing_macro)
                + " — والصفر الافتراضي ليس قياساً (المادتان 3.3 و9.1)"
            )

        dxy = s.dxy_change_7d_pct
        ry = s.real_yield_10y
        btc_dom = s.btc_dominance
        tvl_chg = s.tvl_change_7d_pct
        unlock = s.unlock_pct_next_30d
        mc = s.market_cap_usd

        # تقييم: مضاعف السعر إلى الرسوم السنوية (P/F)
        annual_rev = max(1.0, s.revenue_30d_usd * 12.0)
        pf = ind.safe_div(mc, annual_rev, 999.0)

        score = 0.0
        score += ind.clamp(-dxy / 3.0, -1.0, 1.0) * 0.18          # دولار أقوى = عائق
        score += ind.clamp((2.0 - ry) / 1.0, -1.0, 1.0) * 0.16    # عائد حقيقي أعلى = عائق
        score += ind.clamp((55.0 - btc_dom) / 10.0, -1.0, 1.0) * 0.16  # هيمنة BTC أقل = دعم للبديل
        score += ind.clamp(tvl_chg / 15.0, -1.0, 1.0) * 0.18
        score += ind.clamp(-unlock / 3.0, -1.0, 1.0) * 0.12       # فك قفل = ضغط بيعي
        score += ind.clamp((300.0 - pf) / 300.0, -1.0, 1.0) * 0.10  # تقييم أرخص = دعم
        score += ind.clamp(f["ret_90d_pct"] / 40.0, -1.0, 1.0) * 0.10
        score = ind.clamp(score, -1.0, 1.0)

        evidence = [
            self.ev(ctx, f"DXY تغيّر 7 أيام {dxy:+.2f}% (دولار أقوى = ضغط على الأصول الرقمية)",
                    f"{src}/macro-dxy", "market", Strength.MEDIUM.value, dxy),
            self.ev(ctx, f"العائد الحقيقي للسندات الأمريكية 10 سنوات {ry:.2f}%",
                    "macro/us10y-real", "market", Strength.MEDIUM.value, ry),
            self.ev(ctx, f"هيمنة BTC {btc_dom:.1f}% (انخفاضها يوجّه السيولة نحو البدائل)",
                    f"{src}/btc-dominance", "market", Strength.MEDIUM.value, btc_dom),
            self.ev(ctx, f"TVL أفالانش {s.tvl_usd/1e6:.1f}M$ بتغيّر 7 أيام {tvl_chg:+.2f}%",
                    "defillama/avalanche-tvl", "onchain", Strength.HIGH.value, tvl_chg),
            self.ev(ctx, f"فك قفل متوقع خلال 30 يوماً {unlock:.2f}% من المعروض",
                    "tokenomics/vesting-schedule", "derived", Strength.MEDIUM.value, unlock),
            self.ev(ctx, f"مضاعف السعر/الرسوم السنوية P/F = {pf:.1f} (رسوم 30 يوم {s.revenue_30d_usd/1e3:.1f}K$)",
                    "derived/pf-ratio", "derived", Strength.MEDIUM.value, pf),
            self.ev(ctx, f"ارتباط 30 يوم بـ NASDAQ {s.nasdaq_corr_30d:+.2f} وبـ BTC {s.btc_corr_30d:+.2f}",
                    f"{src}/correlation", "derived", Strength.LOW.value, s.nasdaq_corr_30d),
        ]

        thesis = (
            f"السياق الكلي والأساسي {'داعم' if score > 0.08 else 'ضاغط' if score < -0.08 else 'محايد'} "
            f"بدرجة {score:+.3f}؛ TVL يتغير {tvl_chg:+.1f}% أسبوعياً، ومضاعف P/F = {pf:.0f}، "
            f"مع {unlock:.2f}% فك قفل قادم."
        )
        invalidation = (
            f"يُبطل هذا الرأي إذا انعكس اتجاه TVL إلى ما دون {tvl_chg - 5:+.1f}% أسبوعياً، "
            f"أو إذا ارتفع العائد الحقيقي فوق {ry + 0.35:.2f}%، أو تجاوزت هيمنة BTC {btc_dom + 3:.1f}%."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: العلاقة بين الماكرو والأصول الرقمية غير مستقرة، وقد تنفصل "
            "تماماً في فترات السيولة الذاتية للقطاع. كذلك مضاعف P/F يفترض أن الرسوم مستدامة، "
            "وهي في الواقع شديدة التقلب ومتأثرة بالحوافز المؤقتة."
        )
        notes = []
        if unlock > 3.0:
            notes.append(f"⚠️ فك قفل {unlock:.2f}% — ضغط بيعي محتمل خلال 30 يوماً")
        if pf > 400:
            notes.append(f"⚠️ مضاعف P/F مرتفع ({pf:.0f}) — تقييم غني نسبةً للرسوم")

        return self.make(ctx, score, thesis, evidence, invalidation, dissent,
                         metrics={"pf_ratio": round(pf, 1), "tvl_change_7d_pct": round(tvl_chg, 3),
                                  "unlock_pct": round(unlock, 3), "dxy_change_7d_pct": dxy,
                                  "btc_dominance": btc_dom, "nasdaq_corr": s.nasdaq_corr_30d},
                         notes=notes)


# ==========================================================================
# 05 — الأونشين
# ==========================================================================

class OnchainAgent(BaseAgent):
    """تدفقات الشبكة والمحافظ — الطبقة الأولى في هرمية الأدلة (المادة 3.1)."""

    id, name_ar, name_en = "05", "وكيل الأونشين", "On-chain Agent (AVAX)"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "onchain"
    horizon = "أيام إلى أسابيع"
    file = "agents/05-onchain-avax.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        s = ctx.snapshot
        src = self.source_tag(ctx)
        # ملاحظة: `src` كان مثبّتاً نصاً بـ"avalanche-c-chain" فيُصنّف دليل
        # المحاكاة كطبقة 1. الآن يُشتق من منشأ اللقطة، ويُفرَض التصنيف في `ev()`.
        src = f"{src}/c-chain"

        # -- الامتناع الإلزامي عند غياب المدخلات (المادة 9.1) --------------
        # ثغرة مُصلَحة: في الوضع الحيّ كانت حقول الأونشين تبقى على الصفر
        # الافتراضي، فيُصدر الوكيل دليلاً يقول «العناوين النشطة 0» و«نسبة
        # الاستيكينج 0.00%» بوصفه **طبقة 1** — وهذا اختلاق رقم (المادة 3.3)
        # لأن الصفر هنا يعني «لا بيانات» لا «قياس صفري».
        core = ("active_addresses", "exchange_netflow_usd", "staking_ratio_pct", "tvl_usd")
        missing = [c for c in core if c in (s.missing_fields or [])]
        if missing:
            return AgentOpinion.abstain_opinion(
                self.id, self.name_ar,
                "مدخلات أونشين أساسية غائبة من المصدر: " + "، ".join(missing)
                + " — والصفر الافتراضي ليس قياساً (المادتان 3.3 و9.1)"
            )

        netflow = s.exchange_netflow_usd                      # موجب = ضغط بيعي
        addr_chg = s.active_addresses_change_7d_pct
        tvl_chg = s.tvl_change_7d_pct
        bridge = s.bridge_netflow_7d_usd
        whale = s.whale_accumulation
        stake = s.staking_ratio_pct
        vol_ref = max(1.0, s.volume_24h_usd)

        score = 0.0
        score += ind.clamp(-netflow / (vol_ref * 0.10), -1.0, 1.0) * 0.28   # خروج من المنصات = تراكم
        score += ind.clamp(addr_chg / 12.0, -1.0, 1.0) * 0.16
        score += ind.clamp(tvl_chg / 12.0, -1.0, 1.0) * 0.18
        score += ind.clamp(bridge / 25e6, -1.0, 1.0) * 0.16
        score += ind.clamp(whale, -1.0, 1.0) * 0.14
        score += ind.clamp((stake - 60.0) / 8.0, -1.0, 1.0) * 0.08
        score = ind.clamp(score, -1.0, 1.0)

        direction_txt = ("تراكم" if netflow < 0 else "توزيع")
        evidence = [
            self.ev(ctx, f"صافي تدفق المنصات {netflow/1e6:+.2f}M$ (سالب = {direction_txt} وخروج من المنصات)",
                    f"{src}/exchange-flows", "onchain", Strength.HIGH.value, netflow),
            self.ev(ctx, f"العناوين النشطة {s.active_addresses:,} بتغيّر 7 أيام {addr_chg:+.2f}%",
                    f"{src}/active-addresses", "onchain", Strength.HIGH.value, addr_chg),
            self.ev(ctx, f"TVL على C-Chain {s.tvl_usd/1e6:.1f}M$ بتغيّر {tvl_chg:+.2f}%",
                    "defillama/avalanche", "onchain", Strength.HIGH.value, tvl_chg),
            self.ev(ctx, f"صافي تدفق الجسور 7 أيام {bridge/1e6:+.2f}M$ (موجب = دخول للمنظومة)",
                    "bridges/avalanche-bridge+core", "onchain", Strength.MEDIUM.value, bridge),
            self.ev(ctx, f"مؤشر تراكم الحيتان {whale:+.3f} على مقياس [−1 توزيع .. +1 تجميع]",
                    f"{src}/whale-wallets", "onchain", Strength.MEDIUM.value, whale),
            self.ev(ctx, f"نسبة الاستيكينج {stake:.2f}% مع {s.validators:,} مُدقّق على P-Chain",
                    "avalanche-p-chain/validators", "onchain", Strength.HIGH.value, stake),
            self.ev(ctx, f"رسوم الشبكة 24 ساعة {s.fees_24h_usd/1e3:.1f}K$",
                    f"{src}/fees", "onchain", Strength.MEDIUM.value, s.fees_24h_usd),
        ]

        thesis = (
            f"الصورة الأونشين {'تراكمية' if score > 0.08 else 'توزيعية' if score < -0.08 else 'محايدة'} "
            f"بدرجة {score:+.3f}؛ صافي تدفق المنصات {netflow/1e6:+.2f}M$، "
            f"وتغيّر العناوين النشطة {addr_chg:+.2f}%، وصافي دخول الجسور {bridge/1e6:+.2f}M$."
        )
        invalidation = (
            f"يُبطل هذا الرأي إذا انقلب صافي التدفق إلى المنصات فوق {abs(netflow)*1.5/1e6:+.2f}M$ "
            f"(تدفق بيعي واضح)، أو إذا هبط TVL تحت {s.tvl_usd*0.9/1e6:.1f}M$، "
            f"أو انقلب صافي الجسور إلى {bridge*-1/1e6:+.1f}M$."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: تصنيف العناوين قابل للخطأ الجوهري — محفظة واحدة قد تُصنَّف "
            "كعشرات العناوين، والمنصات تستخدم محافظ وسيطة تُشوّه صافي التدفق. كما أن نشاط "
            "العناوين قد يكون زراعة حوافز (Airdrop Farming) لا طلباً حقيقياً."
        )
        notes = []
        if netflow > vol_ref * 0.05:
            notes.append("⚠️ تدفق بيعي مرتفع إلى المنصات")
        if s.validators < 1100:
            notes.append("⚠️ عدد المُدقّقين منخفض — مخاطرة لامركزية على P-Chain")
        if stake > 70:
            notes.append("ℹ️ نسبة استيكينج مرتفعة — معروض مقفل لكن خطر فك استيكينج جماعي عند التوتر")

        return self.make(ctx, score, thesis, evidence, invalidation, dissent,
                         metrics={"exchange_netflow_usd": netflow,
                                  "active_addresses": s.active_addresses,
                                  "tvl_usd": s.tvl_usd, "staking_ratio_pct": stake,
                                  "bridge_netflow_7d_usd": bridge,
                                  "whale_accumulation": whale},
                         notes=notes)


# ==========================================================================
# 06 — المشتقات والتقلب
# ==========================================================================

class DerivativesAgent(BaseAgent):
    """التمويل، الأساس، الفائدة المفتوحة، التقلب الضمني، التمركز."""

    id, name_ar, name_en = "06", "وكيل المشتقات والتقلب", "Derivatives & Volatility Agent"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "derivatives"
    horizon = "أيام"
    file = "agents/06-derivatives-volatility.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        s = ctx.snapshot
        src = self.source_tag(ctx)

        funding = s.funding_rate_8h
        basis = s.basis_pct
        oi_chg = s.oi_change_24h_pct
        ls = s.long_short_ratio
        iv = s.iv_pct
        rv = f["vol_30d_ann_pct"]
        liq = s.liquidations_24h_usd
        price_chg = f["ret_1d_pct"]

        funding_ann = funding * 3 * 365 * 100.0        # نسبة سنوية تقريبية
        vrp = iv - rv                                   # علاوة مخاطرة التقلب
        crowd = ind.clamp(funding / 0.0005, -1.0, 1.0)  # +1 = ازدحام شراء مفرط

        score = 0.0
        score += -crowd * 0.34                          # تمويل موجب مفرط = إشارة عكسية هبوطية
        # `basis_pct` أساس **سنوي مكافئ** بالنسبة المئوية ⇒ التطبيع على 15% كحد تطرف.
        # (كان يقسم على 0.30 بينما الوحدة الانية متضاربة، فكان الحدّ ميتاً عملياً.)
        score += ind.clamp(basis / 15.0, -1.0, 1.0) * 0.10
        score += ind.clamp((ls - 1.0) / 0.5, -1.0, 1.0) * -0.18  # ازدحام لونج = خطر
        # OI يرتفع مع السعر = اتجاه صحي؛ يرتفع مع هبوط = بناء شورت
        oi_signal = ind.clamp(oi_chg / 25.0, -1.0, 1.0) * (1.0 if price_chg > 0 else -1.0)
        score += oi_signal * 0.20
        liq_ratio = (liq / max(1.0, s.volume_24h_usd)) * 8.0
        score += ind.clamp(liq_ratio, 0.0, 1.0) * 0.10 * (1.0 if price_chg < 0 else -1.0)
        score = ind.clamp(score, -1.0, 1.0)

        evidence = [
            self.ev(ctx, f"معدل التمويل 8 ساعات {funding*100:+.4f}% (سنوي مكافئ ≈ {funding_ann:+.1f}%)",
                    f"{src}/futures-funding", "market", Strength.HIGH.value, funding),
            self.ev(ctx, f"الأساس (Basis) {basis:+.4f}% — {'كونتانجو (تفاؤل)' if basis > 0 else 'باكورديشن (تشاؤم)'}",
                    f"{src}/futures-basis", "market", Strength.MEDIUM.value, basis),
            self.ev(ctx, f"الفائدة المفتوحة {s.open_interest_usd/1e6:.1f}M$ بتغيّر 24 ساعة {oi_chg:+.2f}%",
                    f"{src}/open-interest", "market", Strength.HIGH.value, oi_chg),
            self.ev(ctx, f"نسبة الشراء/البيع {ls:.2f} (أعلى = ازدحام مراكز شراء)",
                    f"{src}/long-short-ratio", "market", Strength.MEDIUM.value, ls),
            self.ev(ctx, f"التقلب الضمني {iv:.1f}% مقابل المتحقق {rv:.1f}% ⇒ علاوة VRP {vrp:+.1f} نقطة",
                    f"{src}/options-iv", "market", Strength.MEDIUM.value, vrp),
            self.ev(ctx, f"تصفيات 24 ساعة {liq/1e6:.2f}M$ = {liq/max(1.0,s.volume_24h_usd)*100:.2f}% من الحجم",
                    f"{src}/liquidations", "market", Strength.MEDIUM.value, liq),
        ]

        thesis = (
            f"تمركز المشتقات {'مزدحم بالشراء — خطر تصحيح' if crowd > 0.35 else ('مزدحم بالبيع — احتمال ضغط شورت' if crowd < -0.35 else 'متوازن')}؛ "
            f"التمويل السنوي المكافئ {funding_ann:+.1f}%، وعلاوة التقلب VRP {vrp:+.1f} نقطة، والدرجة {score:+.3f}."
        )
        invalidation = (
            f"يُبطل هذا الرأي إذا عاد معدل التمويل إلى ما دون {min(0.0, funding-0.0002)*100:+.4f}% "
            f"أو انقلب الأساس إلى الإشارة المعاكسة، أو إذا انخفضت الفائدة المفتوحة بأكثر من 20% "
            f"(تفكيك مراكز لا بناء اتجاه)."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: التمويل الموجب قد يستمر طويلاً في سوق صاعد قوي، والتفسير "
            "العكسي (Contrarian) يخسر في الاتجاهات الممتدة. كذلك التقلب الضمني المُقدَّر تقريبياً "
            "لا يأتي من سطح أوبشن حقيقي على AVAX (سيولته محدودة)، فهو أكثر ضجيجاً من BTC/ETH."
        )
        notes = ["ℹ️ سوق أوبشن AVAX أقل سيولة بكثير من BTC/ETH — دقة IV محدودة"]
        if abs(funding_ann) > 40:
            notes.append(f"⚠️ تمويل سنوي متطرف ({funding_ann:+.1f}%) — اختلال تمركز حاد")
        if abs(vrp) > 25:
            notes.append(f"{'⚠️ التقلب الضمني أغلى من المتحقق' if vrp > 0 else 'ℹ️ التقلب الضمني أرخص من المتحقق'}")

        return self.make(ctx, score, thesis, evidence, invalidation, dissent,
                         metrics={"funding_rate_8h": funding, "funding_annual_pct": round(funding_ann, 2),
                                  "basis_pct": basis, "oi_change_24h_pct": oi_chg,
                                  "long_short_ratio": ls, "iv_pct": iv, "rv_pct": round(rv, 2),
                                  "vrp": round(vrp, 2), "crowding": round(crowd, 3)},
                         notes=notes)


# ==========================================================================
# 07 — المعنويات والأخبار
# ==========================================================================

class SentimentAgent(BaseAgent):
    """
    الطبقة الأضعف في هرمية الأدلة (المستوى 5 — المادة 3.1).
    الثقة هنا محدودة بنيوياً بسقف أقل من بقية الوكلاء.
    """

    id, name_ar, name_en = "07", "وكيل المعنويات والأخبار", "Sentiment & News Agent"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "sentiment"
    horizon = "أيام"
    file = "agents/07-sentiment-news.md"

    CONFIDENCE_CAP = 72.0   # سقف أقل: طبقة أدلة أضعف

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        s = ctx.snapshot
        src = "sentiment/aggregated"

        fg = s.fear_greed
        social = s.social_volume_change_pct
        news = s.news_sentiment

        # مؤشر الخوف والطمع: إشارة عكسية عند التطرف
        if fg >= 75:
            fg_score = -ind.clamp((fg - 75) / 25.0, 0.0, 1.0)
        elif fg <= 25:
            fg_score = ind.clamp((25 - fg) / 25.0, 0.0, 1.0)
        else:
            fg_score = ind.clamp((50 - fg) / 50.0, -0.5, 0.5) * 0.5

        # انفجار الحجم الاجتماعي = إرهاق/ذروة عاطفية
        social_score = -ind.clamp(social / 120.0, -1.0, 1.0) * 0.5

        news_score = ind.clamp(news, -1.0, 1.0)

        score = ind.clamp(0.45 * fg_score + 0.30 * news_score + 0.25 * social_score, -1.0, 1.0)

        evidence = [
            self.ev(ctx, f"مؤشر الخوف والطمع {fg}/100 ({'طمع' if fg > 60 else 'خوف' if fg < 40 else 'محايد'})",
                    "alternative.me/fear-greed", "sentiment", Strength.MEDIUM.value, float(fg)),
            self.ev(ctx, f"تغيّر الحجم الاجتماعي {social:+.1f}% — مقياس الاهتمام الجماهيري",
                    f"{src}/social-volume", "sentiment", Strength.LOW.value, social),
            self.ev(ctx, f"درجة معنويات الأخبار {news:+.3f} على مقياس [−1, +1]",
                    f"{src}/news-nlp", "sentiment", Strength.LOW.value, news),
            self.ev(ctx, f"أحداث مرصودة: {'؛ '.join(s.news_events) if s.news_events else 'لا أحداث جوهرية'}",
                    f"{src}/event-feed", "sentiment", Strength.LOW.value, None),
        ]

        thesis = (
            f"المعنويات في منطقة {'طمع يحتاج حذراً' if fg > 70 else 'خوف قد يوفّر فرصة' if fg < 30 else 'توازن'} "
            f"(مؤشر {fg})، والحجم الاجتماعي {social:+.0f}%، ودرجة الأخبار {news:+.2f}؛ "
            f"الدرجة المركّبة {score:+.3f}."
        )
        invalidation = (
            f"يُبطل هذا الرأي إذا انتقل مؤشر الخوف والطمع إلى النطاق 40–60 (فقدان التطرف الذي "
            f"تقوم عليه الإشارة العكسية)، أو إذا انعكست معنويات الأخبار إلى ما دون {-abs(news):+.2f}."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: **المعنويات أضعف طبقة أدلة في هذا الديسك (المستوى 5)**. "
            "البيانات الاجتماعية قابلة للتلاعب بسهولة (Bots)، ومؤشر الخوف والطمع مؤشر تابع "
            "للسعر لا قائد له — فهو يصف ما حدث ولا يتوقع. كما أن الحدث الإخباري يُسعَّر عادةً "
            "قبل أن يُنشر."
        )
        notes = ["ℹ️ ثقة مقيّدة بسقف 72 — طبقة أدلة من المستوى 5 (المادة 3.1)",
                 "⚠️ هذه الطبقة لا يجوز أن تكون الدليل الوحيد لأي قرار (المادة 3.2)"]

        op = self.make(ctx, score, thesis, evidence, invalidation, dissent,
                       metrics={"fear_greed": fg, "social_change_pct": social,
                                "news_sentiment": news, "evidence_tier": 5},
                       notes=notes)
        op.confidence = min(op.confidence, self.CONFIDENCE_CAP)
        return op


# ==========================================================================
# 08 — نظرية المحافظ
# ==========================================================================

class PortfolioAgent(BaseAgent):
    """لا يقرر الاتجاه — يحدد ميزانية المخاطرة والأوزان."""

    id, name_ar, name_en = "08", "وكيل نظرية المحافظ", "Portfolio Theory Agent"
    layer, authority, domain = Layer.KNOWLEDGE, Authority.ADVISORY, "portfolio"
    horizon = "أسابيع إلى أشهر"
    file = "agents/08-portfolio-theory.md"

    def analyze(self, ctx: AgentContext) -> AgentOpinion:
        f = ctx.features
        s = ctx.snapshot
        cap = ctx.config.capital_usd

        vol = f["vol_30d_ann_pct"]
        sharpe = f["sharpe_90d"]
        sortino = f["sortino_90d"]
        mdd = f["max_dd"]["max_dd_pct"]
        ulcer = f["ulcer"]
        corr_btc = s.btc_corr_30d

        # مخاطرة فعلية عالية ⇒ حصة أصغر من ميزانية المخاطرة
        vol_budget_weight = ind.risk_parity_weights([max(1.0, vol), 55.0])[0]
        sharpe_score = ind.clamp(sharpe / 3.0, -1.0, 1.0)
        drawdown_penalty = ind.clamp(mdd / 60.0, 0.0, 1.0)
        score = ind.clamp(sharpe_score * (1.0 - drawdown_penalty) * 0.55, -1.0, 1.0)

        # توصية حجم قصوى من منظور المحفظة
        suggested_pct = ind.clamp(vol_budget_weight * 100.0 * 0.5, 1.0, 10.0)

        evidence = [
            self.ev(ctx, f"نسبة شارب 90 يوم = {sharpe:.2f}، سورتينو = {sortino:.2f}",
                    "derived/risk-adjusted-returns", "derived", Strength.HIGH.value, sharpe),
            self.ev(ctx, f"أقصى تراجع تاريخي {mdd:.2f}% ومؤشر القرحة {ulcer:.2f}",
                    "derived/drawdown", "derived", Strength.HIGH.value, mdd),
            self.ev(ctx, f"تقلب سنوي {vol:.1f}% ⇒ وزن تكافؤ المخاطر {vol_budget_weight*100:.1f}%",
                    "derived/risk-parity", "derived", Strength.MEDIUM.value, vol_budget_weight),
            self.ev(ctx, f"ارتباط 30 يوم مع BTC {corr_btc:+.2f} — تنويع فعلي محدود",
                    f"{self.source_tag(ctx)}/correlation", "derived", Strength.MEDIUM.value, corr_btc),
        ]

        thesis = (
            f"من منظور المحفظة، الوزن المقترح لـ AVAX لا يتجاوز {suggested_pct:.1f}% من رأس المال "
            f"({cap:,.0f}$) على أساس تكافؤ المخاطر، مع شارب {sharpe:.2f} وأقصى تراجع {mdd:.1f}%."
        )
        invalidation = (
            f"يُبطل هذا التقدير إذا تجاوز التقلب المتحقق {vol*1.5:.0f}% سنوياً (وزن أقل إلزاماً)، "
            f"أو إذا ارتفع الارتباط مع BTC فوق 0.90 (فقدان التنويع ⇒ خفض الوزن)."
        )
        dissent = (
            "أقوى ما يخالف هذا الرأي: الارتباط مع BTC مرتفع ({:.2f})، أي أن AVAX يوفر تنويعاً "
            "وهمياً أكثر منه حقيقياً، والارتباط يقفز نحو 1 في الأزمات تماماً حين نحتاج التنويع. "
            "كما أن تقديرات العائد المتوقع مبنية على تاريخ قصير.".format(corr_btc)
        )
        notes = []
        if corr_btc > 0.85:
            notes.append("⚠️ ارتباط مرتفع مع BTC — تنويع محدود")
        if vol > 90:
            notes.append("⚠️ تقلب سنوي > 90% — الوزن يجب أن يكون في الحد الأدنى")

        return self.make(ctx, score, thesis, evidence, invalidation, dissent,
                         metrics={"suggested_weight_pct": round(suggested_pct, 2),
                                  "vol_ann_pct": round(vol, 2), "sharpe_90d": round(sharpe, 3),
                                  "sortino_90d": round(sortino, 3), "max_dd_pct": round(mdd, 3),
                                  "ulcer": round(ulcer, 3), "btc_corr": corr_btc},
                         notes=notes, dead_zone=0.15)


# ==========================================================================
# السجل
# ==========================================================================

KNOWLEDGE_AGENTS: tuple[type[BaseAgent], ...] = (
    MarketStructureAgent,
    TechnicalAgent,
    QuantitativeAgent,
    MacroFundamentalAgent,
    OnchainAgent,
    DerivativesAgent,
    SentimentAgent,
    PortfolioAgent,
)
