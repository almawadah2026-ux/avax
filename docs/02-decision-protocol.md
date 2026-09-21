# 02 — بروتوكول القرار (Decision Protocol)

> **الجمهور المستهدف:** المدقّق (Auditor) الذي يجب أن يستطيع إعادة حساب كل رقم في القرار، ثم مطوّر يعدّل معايير الترجيح.

كل خطوة أدناه مقروءة من الكود، ومثال الأرقام في القسم 8 مأخوذ من **تشغيل فعلي** للأمر:
`python -m avax_desk.cli --scenario bull --seed 11` (بيانات اصطناعية حتمية).

---

## 1. الخطوات المرقّمة: من اللقطة إلى القرار

| # | الخطوة | الدالة | المخرج |
|---|---|---|---|
| 0 | تحميل اللقطة وحساب الميزات | `cli.py::_load_snapshot` + `base.py::compute_features` | `MarketSnapshot` + `ctx.features` |
| 1 | 8 وكلاء معرفة يصدرون آراءهم | `desks/knowledge.py` | `ctx.opinions["01".."08"]` |
| 2 | وكيل 09 يبني `mini_backtest` وخصومات الوكلاء | `desks/validation.py::ValidationAgent` | `metrics.agent_discounts`, `metrics.validated` |
| 3 | وكيل 10 يبني أقوى حجة مضادة | `desks/validation.py::RedTeamAgent` | `metrics.counter_thesis`, `metrics.weaknesses` |
| 4 | المنسّق يجمّع ويحسب الدرجة والثقة | `orchestrator.py::propose` | `ctx.shared["proposal"]` |
| 5 | المخاطر تحسب الحجم وتنقض أو توافق | `risk/engine.py::evaluate` | `RiskVerdict` |
| 6 | التنفيذ يبني خطة ورقية | `control.py::ExecutionAgent` | `ExecutionPlan` |
| 7 | الالتزام يفحص كل الآراء | `control.py::ComplianceAgent` | `ComplianceReport` |
| 8 | المنسّق يطبّق البوابتين ويصدر القرار | `orchestrator.py::finalize` | `DeskDecision` (+ `blocks`, `abstention_kind`) |
| 8ب | **تدقيق بعدي للقرار** — الوكيل 13 يدقّق قرار الوكيل 14 بعد إصداره | `control.py::ComplianceAgent.audit_decision` | `ctx.shared["post_decision_audit"]` (18 فحصاً في هذا الإصدار) |
| 9 | الذاكرة تسجّل القرار | `desks/memory.py::MemoryAgent` | `JournalRecord` |

---

## 2. الدرجة المرجّحة (Weighted Score) — بالتفصيل

المصدر: `indicators.py::weighted_evidence_score` (يُستدعى من `orchestrator.propose`).

```
        Σ ( sign_i × w_i )
score = ────────────────────          ∈ [−1, +1]
             Σ w_i

w_i  =  (net_confidence_i / 100) × tier_weight(best_tier_i) × agent_weight_i
sign =  +1 (bullish) | −1 (bearish) | 0 (neutral)
```

**أوزان الطبقة (`tier_weight`)** — الأدقّ طبقةً يرجّح أكثر (المادة 3.1):

| أفضل طبقة عند الوكيل | 1 | 2 | 3 | 4 | 5 | 6 | 7 | غير معروفة |
|---|---|---|---|---|---|---|---|---|
| الوزن | 1.00 | 0.95 | 0.90 | 0.80 | 0.65 | 0.50 | 0.30 | 0.50 |

**وزن الوكيل (`agent_weight`)** = خصم التحقق × الوزن التاريخي، ويُبنى هكذا:

```
merged = { }                                 # orchestrator.propose
for aid in set(discounts) | set(history_weights):
    merged[aid] = discounts.get(aid, 1.0) * history_weights.get(aid, 1.0)
```

- **خصم التحقق** من `ValidationAgent` (`desks/validation.py`):
  `best_tier ≥ 5` ⇒ 0.55 · `best_tier == 4` ⇒ 0.75 · وإلا 1.0؛ ثم `×0.85` إن كان عدد الأدلة أقل من 3، و`×0.80` إن بدأت ملاحظة الوكيل بعبارة «بيانات لحظية».
- **الوزن التاريخي** من `JournalStore.agent_weights` (المادة 7.4): أقل من 3 ملاحظات ⇒ 1.0؛ نسبة إصابة `< 0.34` ⇒ 0.50؛ `< 0.45` ⇒ 0.75؛ `> 0.65` ⇒ 1.25؛ وإلا 1.0.
- وكيل غير مذكور في أي منهما ⇒ وزنه 1.0 (الافتراضي في `weights.get(aid, 1.0)`).
- **الوكلاء الممتنعون يُستبعدون كلياً** من البسط والمقام (`continue` عند `abstain`).

**الاتجاه النهائي للمقترح** بمنطقة ميتة **0.10** (لا 0.08):

```
direction = bullish  if score >  DECISION_DEAD_ZONE (0.10)
            bearish  if score < -DECISION_DEAD_ZONE
            neutral  otherwise
```

---

## 3. الثقة المجمّعة (Aggregated Confidence) — الصيغة الفعلية

المصدر: `orchestrator.py::propose`، السطور التي تبني `confidence`:

```
base_conf       = mean(net_confidence لكل المؤيدين)          # 0.0 إن لا مؤيدين
active          = الآراء غير الممتنعة وغير المحايدة
agreement       = supporters / active
signal_strength = clamp(|score| / 0.50, 0.0, 1.0)

confidence = 0.45×base_conf
           + 0.30×(100 × agreement)
           + 0.25×(100 × signal_strength)
```

ثلاثة مكوّنات مستقلة عن قصد: **جودة الآراء المؤيدة** (45%)، **اتساع الاتفاق** (30%)، **وضوح الحافة** (25%). ثم تُطبَّق **خصومات جمعية** (لا ضربية) — والسبب مذكور في الكود: «الخصم بالنقاط قابل للتدقيق والتفسير، أما الضرب فيُسقط الثقة تحت الحد الأدنى دائماً ويمنع أي قرار».

| الخصم | الشرط الدقيق | المادة |
|---|---|---|
| −4 | `red.metrics["consensus_direction"] == direction` و`direction != neutral` | 4.4 |
| −6 | `validated == False` (لم تجتز معايير قانون التحقق) | 4.1 |
| −5 | `direction != neutral` وعدد المؤيدين `< 3` | 6.2 (اتساع التأييد) |
| **−15** | **تعارض مع دليل أولي (طبقة 1 أو 2) يعارض الاتجاه المجمّع** (`law.primary_evidence_conflict`) | **3.2** |
| صفر المطلق | لا آراء نشطة إطلاقاً ⇒ `confidence = 0.0` | 9.1 |

ختاماً: `confidence = round(clamp(confidence, 0.0, 88.0), 2)` — **السقف 88 مقصود**، لأن المادة 8.8 تمنع لغة اليقين.

---

## 4. المنطقة الميتة للقرار (0.10) مقابل منطقة الوكلاء (0.08)

| المستوى | المنطقة الميتة | مصدرها | لماذا |
|---|---|---|---|
| الوكيل الواحد | **0.08** | `desks/base.py::direction_from_score` (الافتراضي في `make`) | إشارة وكيل واحد قد تكون هامشية؛ 0.08 يكفي لتفادي الضجيج |
| القرار المجمّع | **0.10** | `orchestrator.py::DECISION_DEAD_ZONE` | القرار الأعلى يجب أن يكون **أوضح** من أي وكيل منفرد، لا أقل |
| الوكلاء غير الاتجاهيين | 1.00 | `dead_zone=1.0` في وكلاء 11–14 | يضمن ألا يُنسب لهم اتجاه سوقي (المادة 1.3) |
| محامي الشيطان | 0.01 | `desks/validation.py::RedTeamAgent` | دوره الشك؛ يُلزمه الكود بإعلان اتجاه مضاد |

الفارق 0.10−0.08 = 0.02 يعني أن درجة بين 0.08 و0.10 قد تجعل 6 وكلاء صاعدين بينما القرار المجمّع يبقى `neutral` ⇒ امتناع إلزامي (المادة 0.4). هذا سلوك مقصود.

---

## 5. شروط الامتناع الإلزامي

المصدر: `orchestrator.py::finalize` — قائمة `blocks`. وجود أي عنصر يحوّل `action` إلى `ABSTAIN`:

| # | الشرط في الكود | النص المُسجَّل | المادة |
|---|---|---|---|
| 1 | `verdict is None` | «لا حكم مخاطرة — يُحظر إصدار أي قرار» | 5.2 |
| 2 | `compliance is not None and not compliance.compliant` | «حجب من وكيل الالتزام» | 8 |
| 3 | `verdict.veto` | «نقض من وكيل المخاطر» | 5.1 |
| 4 | `not verdict.approved` | «وكيل المخاطر لم يعتمد أي حجم» | 5.2 |
| 5 | `direction == "neutral"` | «لا اتجاه محدد — الامتناع هو القرار الصحيح» | 0.4 |
| 6 | `confidence < limits.min_confidence` (65) | «الثقة المجمّعة … دون الحد الأدنى» | 5.3 |
| 7 | `config.halted` | «الديسك موقوف» | 9.3 |
| 8 | `validation_metrics["lookahead_clean"] is False` | «رُصد تسرّب بيانات مستقبلية — يُحظر القرار» | 8.3 |
| 9 | `verdict.position_size_usd > capital × max_position_pct` | «حجم المعتمد … يتجاوز سقف المركز» | 5.3 |
| 10 | `proposal["primary_evidence_conflict"]["conflict"]` | «تعارض مع دليل من الطبقة 1 أو 2 — الدليل الأولي يرجّح» | 3.2 |
| 11 | مخالفات `aggregate_exposure_violations` بخطورة `error` | «تجاوز التعرّض الكلي أو القطاعي بتقسيم المراكز» | 8.7 |

ويُسجَّل مع القرار تصنيف الامتناع في `abstention_kind` (`halted` / `risk_veto` / `compliance_block` / `no_edge`) وقائمة `blocks` كاملة — فلا يُمحى الفرق بين «نقض ملزم» و«امتناع» في السجل.

وإضافةً إلى ذلك، تنقض المخاطر من داخل المحرك قبل وصول الأمر للمنسّق (16 موضع نقض مفصّلة في `03-risk-framework.md` §7): إيقاف كامل، مستوى أحمر، مستوى برتقالي/أحمر بمضاعف صفري، اتجاه محايد، ثقة دون الحد، سبريد > 25 نقطة أساس (bps)، تقلب سنوي > 150%، سيولة مشاركة ≤ 1$، استنفاد الحد القطاعي، حجم نهائي دون 100$، مخاطرة فعلية > الحد، وفحوص تحقق ناقصة.

**ملاحظتان على الصدق مع الكود:**

- `Action.FLAT` معرّفة ومترجمة في `render_report`، لكن **لا مسار في `finalize` يولّدها**؛ المخرج الفعلي إما `LONG`/`SHORT` أو `ABSTAIN`.
- الشرط 4 يقارن الثقة المجمّعة بالحد 65، وهو نفس عتبة المنطقة الرابعة في `CONFIDENCE_BANDS` (65–80 «قوي — مؤهل للدخول»). لكن دالة `confidence_band` نفسها **غير مستدعاة** في الدورة.

---

## 6. حفظ الرأي المخالف وكشف Groupthink

**حفظ المخالف (المادة 6):**

1. `proposers` ينتج `opposers` = الآراء النشطة التي خالفت الاتجاه.
2. `_strongest_dissent` يبني النص من: `red.metrics["counter_thesis"]`، ثم أول نقطة ضعف من `weaknesses`، ثم thesis لأول معارضَين (بحد أقصى)، ويُقصّ إلى 1200 حرف.
3. إن كانت قائمة المعارضين فارغة والنص غير فارغ ⇒ تُضاف `"10"` قسراً (`opposing_ids = ["10"]`) لأن محامي الشيطان «دائماً مخالف مسجّل».
4. إن لم يتوفر أي نصّ من وكيل ⇒ يُستخدم نص عام مكتوب داخل الكود (`_strongest_dissent`) **مع وسم مصدره**: تُعيد الدالة `(النص، dissent_source)` وتُخزَّن القيمة في `DeskDecision.dissent_source`، ويمرّرها التدقيق البعدي إلى `validate_decision_completeness` فيرفع `DISSENT_IS_FALLBACK` (تحذير) بدل أن يمرّ الفحص شكلياً.
5. `DeskDecision` يحمل: `supporting_agents`, `opposing_agents`, `abstaining_agents`, `strongest_dissent` — وكلها تُكتب في السجل.

`LawEngine.validate_decision_completeness` يمنح مخالفة `NO_DISSENT_RECORDED` (المادة 6.3) عند غياب المعارضين **و** غياب نص المخالفة، و`DISSENT_IS_FALLBACK` عند كون النص احتياطياً، و`NO_SUPPORTING_EVIDENCE` عند غياب المؤيدين — وتُستدعى فعلاً من `ComplianceAgent.audit_decision` في المرحلة 【5ب】.

**كشف الإجماع المريب (المادة 4.4):** `law.py::flag_groupthink`

```
active    = الآراء غير الممتنعة وغير المحايدة
agreement = max(bulls, bears) / len(active)
flag      = (agreement >= 0.95) and (len(active) >= 5)
```

العتبة الفعلية **0.95** (لا 100% كما في نص المادة)، مع شرط حد أدنى 5 آراء نشطة. النتيجة تُخزَّن في `ctx.shared["groupthink"]` وتظهر كـ `groupthink_flag` في القرار، ويُطبع التقرير عندها: «🚨 إجماع شبه تام — مراجعة إلزامية ضد Groupthink».

---

## 7. جدول: أي شرط يمنع القرار ومن أي مادة

| الشرط | القرار الناتج | الطبقة التي فرضته | المادة |
|---|---|---|---|
| رأي بلا `invalidation` | مخالفة حرجة؛ الالتزام يصبح غير متوافق ⇒ حجب | 13 / `LawEngine` | 2.2 |
| ثقة بلا أدلة | مخالفة `CONFIDENCE_WITHOUT_EVIDENCE` ⇒ حجب | 13 / `LawEngine` | 2.3 |
| نمط لغة يقين في أي نص | مخالفة `CERTAINTY_LANGUAGE` بخطورة `error` ⇒ حجب | 13 / `LawEngine` | 8.8 |
| نمط أمر تنفيذ | `EXECUTION_INSTRUCTION` ⇒ حجب | 13 / `LawEngine` | 0.2 |
| وكيل معرفي بتوصية تنفيذية | `KNOWLEDGE_AGENT_RECOMMENDS` ⇒ حجب | 13 / `LawEngine` | 1.2 |
| وكيل ذو نقض أعلن اتجاهاً | `VETO_AGENT_DIRECTIONAL` ⇒ حجب | 13 | 1.3 |
| وكيل مفقود من الدورة (09/10/11/12) | `compliant = False` ⇒ حجب | 13 | 1.1 |
| لقطة بلا مصدر | `UNSOURCED_SNAPSHOT` ⇒ حجب | 13 | 2.5 |
| نقض المخاطر (أي سبب) | `ABSTAIN` | 14 | 5.1 |
| مستوى أحمر أو خرق خسارة/تراجع | نقض ⇒ `ABSTAIN` | 11 | 5.4 / 9.3 |
| ثقة مجمّعة < 65 | `ABSTAIN` | 14 (+ 11) | 5.3 |
| اتجاه محايد | `ABSTAIN` | 14 (+ 11) | 0.4 |
| `halted` | `ABSTAIN` | 14 | 9.3 |
| إشارة بلا فحوص التحقق الأربعة | نقض | 11 | 4.1 |
| غياب حكم المخاطر كلياً | `ABSTAIN` | 14 | 5.2 |
| حجم من المخاطر دون اعتماد (`approved=False`) | `ABSTAIN` | 14 | 5.2 |
| تسرّب بيانات مستقبلية (`lookahead_clean=False`) | `ABSTAIN` + مخالفة حرجة في التدقيق البعدي | 14 + 13 | 8.3 |
| تعارض مع دليل من الطبقة 1 أو 2 | `ABSTAIN` | 14 | 3.2 |
| تجاوز التعرّض الكلي/القطاعي بتقسيم المراكز | `ABSTAIN` | 14 | 8.7 |
| قرار الوكيل 14 بعد إصداره (اتساقه مع المخاطر واكتماله) | يُوثَّق في `post_decision_audit` (لا يعدّله) | 13 | 6.3 / 5.1 / 5.2 / 5.3 / 1.4 / 8.4 |
| إجماع ≥ 95% | لا يمنع — يرفع `groupthink_flag` ويفعّل المراجعة | 14 / `LawEngine` | 4.4 |

---

## 8. مثال سيناريو كامل — أرقام حقيقية من تشغيل فعلي

**الأمر:** `--scenario bull --seed 11 --no-journal` · البيانات: `source="synthetic"`, `meta.seed=11` · التشغيل بتاريخ 2026-09-21.
**الحصيلة:** `LONG` بثقة **69.66** · الدرجة **+0.5835** · الاتفاق **71%** · حجم **$36,426.53**.

### 8.1 آراء طبقة المعرفة كما دخلت الترجيح

| الوكيل | الاتجاه | ثقة صافية | أفضل طبقة | وزن الطبقة | وزن الوكيل | الوزن النهائي | الإشارة |
|---|---|---|---|---|---|---|---|
| 05 أونشين | bullish | 80.5 | 3 | 0.90 | 1.00 | 0.7245 | +1 |
| 03 كمي | bullish | 79.9 | 3 | 0.90 | 1.00 | 0.7191 | +1 |
| 08 محافظ | bullish | 78.4 | 3 | 0.90 | 1.00 | 0.7056 | +1 |
| 04 ماكرو | bullish | 70.5 | 3 | 0.90 | 1.00 | 0.6345 | +1 |
| 06 مشتقات | bearish | 62.1 | 3 | 0.90 | 1.00 | 0.5589 | −1 |
| 02 فني | bullish | 59.9 | 3 | 0.90 | 1.00 | 0.5391 | +1 |
| 01 بنية السوق | neutral | 34.3 | 3 | 0.90 | 0.80 | 0.2470 | 0 |
| 07 معنويات | bearish | 62.7 | 5 | 0.65 | 0.55 | 0.2242 | −1 |

`total_weight = 4.3528` · البسط = 2.5403 ⇒ **score = 2.5403 / 4.3528 = +0.5836 ≈ +0.5835** ✓

**ملاحظتان مهمتان على هذا الجدول:**
- لا يوجد دليل من الطبقة 1 أو 2: **حارس المنشأ** في `BaseAgent.ev` يخفض أي دليل مصدره لقطة اصطناعية (`onchain`/`market`) إلى `derived` (طبقة 3) ويوسمه `[محاكاة …]` — فالوكلاء 01 و05 يظهران بالطبقة 3 لا 1/2. هذا مقصود ويمنع تزوير منشأ الأدلة.
- الوكيل 01 **محايد** (درجته داخل منطقته الميتة)، فهو يساهم في المقام بلا إشارة — لذلك `active = 7` لا 8.

### 8.2 حساب الثقة خطوة بخطوة

```
supporters = [02, 03, 04, 05, 08]        →  5 مؤيدين
opposers   = [06, 07]                    →  2 معارضَين
abstainers = []                          →  لا امتناع
active     = 7                           →  01 محايد (مستبعد من الاتفاق)
agreement  = 5/7 = 0.7143

base_conf  = (59.9+79.9+70.5+80.5+78.4)/5 = 369.2/5 = 73.84 ✓

signal_strength = clamp(0.5835/0.50, 0, 1) = clamp(1.167, 0, 1) = 1.000   ← مُقيَّدة بالسقف

confidence = 0.45×73.84  = 33.228
           + 0.30×71.43  = 21.429
           + 0.25×100.00 = 25.000
           ───────────────────────
                            = 79.657
الخصومات:
  −4  محامي الشيطان: consensus_direction = "bullish" = direction
  −6  validated = False (لم تجتز معايير قانون التحقق)
  −0  المؤيدون 5 ≥ 3 ⇒ لا خصم
  −0  لا تعارض مع دليل أولي (لا وجود لطبقة 1/2 في لقطة اصطناعية)
           ───────────────────────
confidence = 69.657  →  round(...,2) = 69.66 ✓
```

### 8.3 المقترح كما ظهر

`direction=bullish` · `score=0.5835` · `confidence=69.66` · `agreement=0.7143` · `base_confidence=73.84` · `validated=false` · `history_weights` كلها 1.0 (لا سجل مراجعات بعدية كافٍ) · `penalties` = [«خصم 4 نقاط…», «خصم 6 نقاط…»] · `primary_evidence_conflict.conflict=false`.

خصومات التحقق المستخدمة: `{01: 0.8, 02: 1.0, 03: 1.0, 04: 1.0, 05: 1.0, 06: 1.0, 07: 0.55, 08: 1.0}` — لاحظ أن 01 خُصم لملاحظته «بيانات لحظية»، و07 لأنه من الطبقة 5.

### 8.4 البوابات والنتيجة

- المخاطر: `approved=true`, `veto=false`, `risk_level=green`, `position_size_usd=36426.53` (3.643% من رأس المال), `stop_loss_pct=13.726`, `risk_per_trade_pct=0.5`, القيد الملزم `fixed_fractional`.
- الالتزام: `compliant=true`, `checked_agents=12`, `violations=[]`, `blocked=false`.
- التدقيق البعدي للقرار (【5ب】): `valid=true`, `checked=18`, `violations_found=0`, `critical=0`.
- `groupthink`: `agreement=0.7143 < 0.95` ⇒ `flag=false`.
- القرار: نطاق الدخول `115.252464 – 115.830170`، الوقف `99.681818`، الأهداف `139.330565 / 163.119813`، الحجم `$36,426.53`، `dissent_source="agent"` (نص المخالفة من محامي الشيطان ووكيلين معارضين لا نص احتياطي)، والحكم في السجل غير مكتوب لأن التشغيل تم بـ `--no-journal`.

### 8.5 إعادة إنتاج المثال

```powershell
$env:PYTHONPATH="src"; python -m avax_desk.cli --scenario bull --seed 11 --no-journal
```

النتيجة **حتمية** للبذرة نفسها: `SyntheticFeed` يستخدم `seed` و`scenario`، وكل الأدوات الإحصائية مكتوبة بـ Python القياسي بلا تبعيات عشوائية خارج البذرة (عدا `monte_carlo_terminal` الذي يستخدم `seed=7` ثابتاً مضمّناً في `compute_features`). الأرقام أعلاه من تشغيل فعلي؛ أي تعديل على مولّد البيانات أو الميزات يُغيّرها، فأعِد التشغيل للتحقق.

---

## 9. تعارضات مرصودة

| # | البند | الحالة | الدليل (الملف:السطر) |
|---|---|---|---|
| D1 | المادة 4.4: «الإجماع الكامل (100%)» مقابل عتبة الكود 0.95 | ✅ **مُصلَح** — نص المادة 4.4 حُدِّث ليطابق الكود (≥ 95% مع ≥ 5 آراء اتجاهية، قابلة للضبط بـ`Limits.groupthink_threshold`)، فلم يبقَ تعارض بين النص والكود | `CONSTITUTION.md` المادة 4.4 (الملاحظة التنفيذية)، `law.py:344-365`؛ تحقق: 5 صاعدين/0 هابط ⇒ `flag=True`، و4/1 ⇒ `flag=False` |
| D2 | المادة 6.3: نص مخالف احتياطي مبرمج | ✅ **مُصلَح** — `_strongest_dissent` تُعيد `(النص، المصدر)`، والمصدر يُخزَّن في `DeskDecision.dissent_source` ويُمرَّر إلى `validate_decision_completeness` الذي يرفع `DISSENT_IS_FALLBACK` (تحذير) عند النص الاحتياطي | `orchestrator.py:215,259`، `contracts.py:394`، `control.py:553-555`، `law.py:507-513`؛ في مثال `bull/seed=11` كان `dissent_source="agent"` |
| D3 | المادة 2.1: `dissent` إلزامي ✅ | 🔴 **مفتوح** — `MISSING_DISSENT` ما زال بخطورة `warning` لا `error`، فرأي بلا حقل مخالف يُسجَّل ولا يحجب | `law.py:243-244`؛ تحقق مباشر: `validate_opinion` مع `dissent=""` ⇒ `('MISSING_DISSENT','warning')` |
| D4 | المادة 4.1 مقابل 5.1: فشل التحقق مقابل غيابه | ❎ **ليس خطأً** — التفسير معلن في الكود: المادة تشترط **إجراء** الفحوص لا نجاحها؛ فغياب فحص ⇒ نقض، وفشل الفحوص (`validated=False`) ⇒ خفض الحجم 50% وخصم 6 نقاط ثقة. وأُضيف أن `capacity_checked`/`overfitting_checked` صارتا محسوبتين فعلاً لا `True` مثبّتة | `risk/engine.py:172-188`، `desks/validation.py:296-306,394-395` |
| D5 | المادة 9.3 برتقالي: «إيقاف المراكز الجديدة» | ✅ **مُصلَح** — البرتقالي (والأحمر) يضيفان سبب نقض صريحاً، فلا يخرج `veto=False, approved=False` ولا قرار اتجاهي بحجم `$0`؛ و`RiskVerdict.__post_init__` يمنع بناء ذلك أصلاً | `risk/engine.py:200-203`، `contracts.py:316-328`؛ تحقق: `--daily-pnl -1.6` ⇒ `ABSTAIN` بسبب نقض |
| D6 | خصم محامي الشيطان (صياغة السبب) | ✅ **مُصلَح** — نص السبب صار يشرح الشرط: «خصم 4 نقاط — حجة مضادة من محامي الشيطان **على نفس الاتجاه**» | `orchestrator.py:88-90` |
| D7 | `Action.FLAT` بلا مُنتِج في `finalize` | 🔴 **مفتوح** — القيمة معرّفة ومترجمة في التقرير ولا يولّدها `finalize` (المخرج LONG/SHORT/ABSTAIN). لكن أُضيف `abstention_kind` (`halted`/`risk_veto`/`compliance_block`/`no_edge`) فصار السجل يميّز سبب الامتناع ولو كان العنوان واحداً | `contracts.py:396`، `orchestrator.py:232-243,260`، `cli.py:333` |
| D8 | جدول الفرض: 4.4 عبر `flag_groupthink` | ❎ **ليس خطأً** — مفروض فعلاً داخل الدورة ويُخزَّن في `ctx.shared["groupthink"]` ويظهر كـ`groupthink_flag` | `orchestrator.py:219`، `law.py:344-365` |
