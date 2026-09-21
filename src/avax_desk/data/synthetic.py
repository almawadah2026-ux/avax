"""
مولّد بيانات اصطناعي حتمي — للتدريب والاختبار بلا شبكة.

لماذا اصطناعي؟
    1. الاختبار يجب أن يكون **قابلاً للتكرار** (نفس البذرة ⇒ نفس النتيجة).
    2. لا يمكن تدريب وكيل على بيانات مستقبلية لم تحدث بعد.
    3. نستطيع توليد سيناريوهات نادرة (أزمة سيولة، تصفية جماعية) لا تتوفر في التاريخ.

تحذير دستوري: البيانات هنا **ليست سوقاً حقيقياً**. أي وكيل يستشهد بها في قرار
حقيقي يجب أن يوسمها `synthetic` — المادة 3.1 (هرمية الأدلة).
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from .models import MarketSnapshot


SCENARIOS = ("bull", "bear", "chop", "crisis", "recovery")


class SyntheticFeed:
    """مولّد لقطات سوقية حتمية لمنظومة أفالانش."""

    def __init__(
        self,
        seed: int = 42,
        days: int = 365,
        start_price: float = 24.0,
        scenario: str = "auto",
    ) -> None:
        self.seed = seed
        self.days = days
        self.start_price = start_price
        self.scenario = scenario
        self.rng = random.Random(seed)

    # ------------------------------------------------------------------ #
    def generate(self) -> MarketSnapshot:
        scenario = self.scenario
        if scenario == "auto":
            scenario = SCENARIOS[self.seed % len(SCENARIOS)]

        drift, vol, jump_prob = self._regime_params(scenario)
        closes, highs, lows, volumes, dollar_vols = self._price_path(
            drift, vol, jump_prob
        )

        snap = MarketSnapshot(asset="AVAX", source="synthetic")
        snap.closes = closes
        snap.highs = highs
        snap.lows = lows
        snap.volumes = volumes
        snap.dollar_volumes = dollar_vols

        price = closes[-1]
        # -- دفتر الأوامر: سيولة مرتبطة بعمق السوق -------------------------
        spread_bps = max(1.5, 40.0 / math.sqrt(max(1.0, dollar_vols[-1] / 1e6)))
        snap.best_bid = price * (1 - spread_bps / 20_000.0)
        snap.best_ask = price * (1 + spread_bps / 20_000.0)
        depth_base = dollar_vols[-1] * 0.0025
        skew = self.rng.uniform(-0.35, 0.35)
        snap.bid_depth_usd = depth_base * (1 + skew)
        snap.ask_depth_usd = depth_base * (1 - skew)
        snap.venues = self.rng.choice([6, 7, 8, 9, 10, 11])
        snap.maker_fee_bps = 1.0
        snap.taker_fee_bps = self.rng.choice([4.0, 5.0, 6.0])

        # -- المشتقات: التمويل يتبع الاتجاه، لكن مع انحراف متعمّد -----------
        ret_30 = (closes[-1] / closes[-31] - 1) if len(closes) > 31 else 0.0
        snap.funding_rate_8h = 0.0001 * (ret_30 * 8) + self.rng.gauss(0, 0.00008)
        snap.open_interest_usd = dollar_vols[-1] * self.rng.uniform(0.8, 1.6)
        snap.oi_change_24h_pct = self.rng.gauss(ret_30 * 20, 4.0)
        snap.basis_pct = snap.funding_rate_8h * 3 * 365 * 100.0   # أساس سنوي مكافئ %
        snap.iv_pct = 55.0 + abs(ret_30) * 120 + self.rng.gauss(0, 6)
        snap.long_short_ratio = max(0.4, 1.0 + ret_30 * 1.5 + self.rng.gauss(0, 0.15))
        snap.liquidations_24h_usd = dollar_vols[-1] * self.rng.uniform(0.002, 0.05)

        # -- الأونشين ------------------------------------------------------
        base_addr = 42_000
        snap.active_addresses = int(base_addr * (1 + ret_30 * 1.2) + self.rng.gauss(0, 2500))
        snap.active_addresses_change_7d_pct = self.rng.gauss(ret_30 * 30, 5.0)
        snap.exchange_netflow_usd = -ret_30 * dollar_vols[-1] * 0.12 + self.rng.gauss(0, dollar_vols[-1] * 0.01)
        snap.staking_ratio_pct = 62.0 + self.rng.gauss(0, 2.5)
        snap.validators = int(1_250 + self.rng.gauss(0, 60))
        snap.tvl_usd = 780e6 * (1 + ret_30 * 0.9) + self.rng.gauss(0, 15e6)
        snap.tvl_change_7d_pct = self.rng.gauss(ret_30 * 25, 4.0)
        snap.dex_volume_24h_usd = dollar_vols[-1] * self.rng.uniform(0.15, 0.5)
        snap.bridge_netflow_7d_usd = ret_30 * 40e6 + self.rng.gauss(0, 6e6)
        snap.whale_accumulation = max(-1.0, min(1.0, ret_30 * 2.5 + self.rng.gauss(0, 0.25)))
        snap.fees_24h_usd = 180_000 * (1 + ret_30 * 1.5) + self.rng.gauss(0, 12_000)

        # -- المعنويات: تتبع السعر لكن بتأخير وبمبالغة ---------------------
        snap.fear_greed = int(max(5, min(95, 50 + ret_30 * 220 + self.rng.gauss(0, 8))))
        snap.social_volume_change_pct = self.rng.gauss(ret_30 * 90, 22.0)
        snap.news_sentiment = max(-1.0, min(1.0, ret_30 * 1.8 + self.rng.gauss(0, 0.22)))
        snap.news_events = self._news_events(scenario)

        # -- الماكرو -------------------------------------------------------
        snap.dxy_change_7d_pct = self.rng.gauss(-ret_30 * 4, 0.7)
        snap.real_yield_10y = 1.9 + self.rng.gauss(0, 0.12)
        snap.btc_dominance = 54.0 + self.rng.gauss(-ret_30 * 12, 1.2)
        snap.nasdaq_corr_30d = max(-0.2, min(0.9, 0.45 + self.rng.gauss(0, 0.1)))
        snap.btc_corr_30d = max(0.2, min(0.98, 0.72 + self.rng.gauss(0, 0.07)))

        # -- الأساسيات -----------------------------------------------------
        supply = 415_000_000.0
        snap.circulating_supply = supply
        snap.market_cap_usd = price * supply
        snap.unlock_pct_next_30d = abs(self.rng.gauss(1.4, 0.5))
        snap.revenue_30d_usd = snap.fees_24h_usd * 30 * self.rng.uniform(0.85, 1.15)

        snap.meta = {
            "scenario": scenario,
            "seed": self.seed,
            "days": self.days,
            "warning": "بيانات اصطناعية — ليست سوقاً حقيقياً (المادة 3.1)",
        }
        return snap

    # ------------------------------------------------------------------ #
    def _regime_params(self, scenario: str) -> tuple[float, float, float]:
        table = {
            "bull":     (0.0022, 0.038, 0.010),
            "bear":     (-0.0020, 0.045, 0.020),
            "chop":     (0.0000, 0.030, 0.008),
            "crisis":   (-0.0060, 0.075, 0.060),
            "recovery": (0.0015, 0.042, 0.015),
        }
        return table.get(scenario, table["chop"])

    def _price_path(
        self, drift: float, vol: float, jump_prob: float
    ) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
        closes: list[float] = [self.start_price]
        highs: list[float] = [self.start_price * 1.012]
        lows: list[float] = [self.start_price * 0.988]
        volumes: list[float] = []
        dollar_vols: list[float] = []

        base_vol_units = 3_500_000.0
        # الحجم الأول يقابل الشمعة الابتدائية: بدونه يصبح len(volumes)=days
        # مقابل len(closes)=days+1 ⇒ إزاحة شمعة واحدة في كل ميزات الحجم.
        volumes.append(base_vol_units * self.rng.uniform(0.8, 1.2))
        dollar_vols.append(volumes[-1] * self.start_price)

        for _ in range(self.days):
            r = self.rng.gauss(drift, vol)
            # ذيول سمينة: قفزات نادرة
            if self.rng.random() < jump_prob:
                r += self.rng.choice([-1, 1]) * self.rng.uniform(0.06, 0.18)
            new_price = max(0.5, closes[-1] * math.exp(r))
            closes.append(new_price)

            # فتيلان **غير متماثلين**: كانا متماثلين بالبناء
            # (h − c = c − l) في 120/120 شمعة، فصار أي تحليل «فتيل أعلى/أسفل»
            # تحصيل حاصل — وهو ما كشفه الوكلاء بأنفسهم في تشغيل حقيقي.
            up_wick = abs(r) * self.rng.uniform(0.15, 1.35) + vol * self.rng.uniform(0.05, 0.65)
            dn_wick = abs(r) * self.rng.uniform(0.15, 1.35) + vol * self.rng.uniform(0.05, 0.65)
            highs.append(new_price * (1 + up_wick))
            lows.append(new_price * (1 - dn_wick))

            vol_units = base_vol_units * (1 + abs(r) * 14) * self.rng.uniform(0.7, 1.35)
            volumes.append(vol_units)
            dollar_vols.append(vol_units * new_price)

        return closes, highs, lows, volumes, dollar_vols

    def _news_events(self, scenario: str) -> list[str]:
        pool = {
            "bull": ["ترقية شبكة أفالانش ترفع كفاءة الرسوم",
                     "نمو TVL على C-Chain للشهر الثالث",
                     "إطلاق Subnet مؤسسي جديد"],
            "bear": ["فك استيكينج كبير يضغط على السعر",
                     "منافس يستحوذ على حصة من نشاط DeFi",
                     "مخاوف تنظيمية على الأصول البديلة"],
            "chop": ["نشاط جانبي مع تراجع أحجام التداول",
                     "لا أحداث جوهرية — سوق ينتظر محفزاً"],
            "crisis": ["تصفية جماعية في سوق المشتقات",
                       "خروج سيولة من الجسور نحو شبكات بديلة",
                       "ارتفاع حاد في التقلب الضمني"],
            "recovery": ["عودة التدفقات إلى المنظومة",
                         "تحسّن في عدد العناوين النشطة",
                         "انخفاض حاد في التمويل السلبي"],
        }
        return pool.get(scenario, pool["chop"])

    # ------------------------------------------------------------------ #
    @staticmethod
    def timeline(days: int, end: datetime | None = None) -> list[str]:
        """طوابع زمنية يومية بصيغة ISO — تُستخدم لتوسيم الأدلة."""
        end = end or datetime.now(timezone.utc)
        return [
            (end - timedelta(days=days - i)).isoformat(timespec="seconds")
            for i in range(days + 1)
        ]
