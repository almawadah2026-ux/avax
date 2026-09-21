/**
 * سكربت تنسيق DSH — تشغيل ديسك أفالانش بوكلاء لغويين حقيقيين.
 * ============================================================
 *
 * الفرق بين هذا الملف وكود Python:
 *   • Python  = العمود الفقري: البيانات، الرياضيات، محرك القوانين، محرك المخاطر، السجل.
 *   • هذا الملف = يشغّل **الوكلاء الحقيقيين** (نماذج لغوية) بملفات تعريفهم في agents/،
 *     كل وكيل يقرأ ملفه ويحلّل ويُعيد رأياً مهيكلاً، ثم يُطبَّق الدستور على المخرجات.
 *
 * الاستخدام من أداة workflow:
 *   args = {
 *     "symbol": "AVAX",
 *     "snapshot": { ... }        // اختياري: لقطة سوقية من `python -m avax_desk.cli --json`
 *     "quick": false,            // true = 3 وكلاء معرفة فقط (تشغيل سريع للتحقق)
 *     "capitalUsd": 1000000
 *   }
 *
 * ⚠️ تحذير مهم عن الطابع الزمني:
 *   حقل `snapshot.as_of` يجب أن يكون **حديثاً (≤ 24 ساعة)**. وكيل الأونشين (05)
 *   يوسم أي دليل أقدم من 24 ساعة بـ STALE ويخصم 30% من ثقته (المادة 3.4)،
 *   والمنسّق (14) سيمتنع إلزاماً إن كانت كل الأدلة قديمة — وهو سلوك صحيح
 *   لكنه مُربك إن لم تكن تتوقعه. مرّر لقطة طازجة أو استخدم وضع البيانات الحيّة.
 *
 * القاعدة الدستورية الحاكمة: النظام تحليل فقط — لا تنفيذ حقيقي (المادة 0.2).
 */

const ROOT = "C:\\Users\\seens\\OneDrive\\Desktop\\deep\\avax";

// ── عقد الرأي (المادة 2) ────────────────────────────────────────────────
const OPINION_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["agent_id", "thesis", "direction", "confidence", "horizon",
             "invalidation", "dissent", "abstain", "evidence"],
  properties: {
    agent_id: { type: "string" },
    thesis: { type: "string" },
    direction: { type: "string", enum: ["bullish", "bearish", "neutral"] },
    confidence: { type: "number" },
    horizon: { type: "string" },
    invalidation: { type: "string" },
    dissent: { type: "string" },
    abstain: { type: "boolean" },
    abstain_reason: { type: "string" },
    evidence: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["claim", "source", "timestamp", "kind", "strength"],
        properties: {
          claim: { type: "string" },
          source: { type: "string" },
          timestamp: { type: "string" },
          kind: { type: "string", enum: ["onchain", "market", "derived", "technical", "sentiment", "expert", "inference"] },
          strength: { type: "string", enum: ["high", "medium", "low"] }
        }
      }
    }
  }
};

const DECISION_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["action", "confidence", "horizon", "rationale", "invalidation",
             "strongest_dissent", "supporting_agents", "opposing_agents"],
  properties: {
    action: { type: "string", enum: ["LONG", "SHORT", "FLAT", "ABSTAIN"] },
    confidence: { type: "number" },
    horizon: { type: "string" },
    rationale: { type: "string" },
    invalidation: { type: "string" },
    strongest_dissent: { type: "string" },
    supporting_agents: { type: "array", items: { type: "string" } },
    opposing_agents: { type: "array", items: { type: "string" } },
    blocks: { type: "array", items: { type: "string" } },
    entry_zone: { type: "array", items: { type: "number" } },
    stop: { type: "number" },
    targets: { type: "array", items: { type: "number" } },
    size_usd: { type: "number" }
  }
};

const RISK_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["approved", "veto", "risk_level", "veto_reasons", "position_size_usd", "stop_loss_pct"],
  properties: {
    approved: { type: "boolean" },
    veto: { type: "boolean" },
    risk_level: { type: "string", enum: ["green", "yellow", "orange", "red"] },
    veto_reasons: { type: "array", items: { type: "string" } },
    position_size_usd: { type: "number" },
    computed_size_usd: { type: "number" },
    stop_loss_pct: { type: "number" },
    risk_per_trade_pct: { type: "number" },
    binding_constraint: { type: "string" },
    notes: { type: "array", items: { type: "string" } }
  }
};

const SNAPSHOT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["asset", "price", "as_of", "source"],
  properties: {
    asset: { type: "string" },
    price: { type: "number" },
    as_of: { type: "string" },
    source: { type: "string" },
    ret_7d_pct: { type: "number" },
    ret_30d_pct: { type: "number" },
    realized_vol_30d_pct: { type: "number" },
    avg_daily_volume_usd: { type: "number" },
    spread_bps: { type: "number" },
    funding_rate_8h: { type: "number" },
    open_interest_usd: { type: "number" },
    tvl_usd: { type: "number" },
    tvl_change_7d_pct: { type: "number" },
    active_addresses: { type: "number" },
    staking_ratio_pct: { type: "number" },
    exchange_netflow_usd: { type: "number" },
    fear_greed: { type: "number" },
    btc_dominance: { type: "number" },
    btc_corr_30d: { type: "number" },
    notes_for_agents: { type: "string" }
  }
};

// ── كشف الوكلاء (مطابق لـ law.py::AGENT_ROSTER) ──────────────────────────
const KNOWLEDGE_AGENTS = [
  { id: "01", name: "وكيل بنية السوق", file: "agents/01-market-structure.md" },
  { id: "02", name: "وكيل التحليل الفني", file: "agents/02-technical-analysis.md" },
  { id: "03", name: "الوكيل الكمي", file: "agents/03-quantitative.md" },
  { id: "04", name: "وكيل الماكرو والأساسيات", file: "agents/04-macro-fundamental.md" },
  { id: "05", name: "وكيل الأونشين", file: "agents/05-onchain-avax.md" },
  { id: "06", name: "وكيل المشتقات والتقلب", file: "agents/06-derivatives-volatility.md" },
  { id: "07", name: "وكيل المعنويات والأخبار", file: "agents/07-sentiment-news.md" },
  { id: "08", name: "وكيل نظرية المحافظ", file: "agents/08-portfolio-theory.md" }
];

const QUICK_AGENTS = ["01", "03", "05"];

const AGENT_BY_ID = {};
for (const a of KNOWLEDGE_AGENTS) AGENT_BY_ID[a.id] = a;

// ── قوالب البرومبت ──────────────────────────────────────────────────────
function constitutionHeader(agentFile) {
  return [
    `أنت وكيل متخصص داخل «ديسك أفالانش» — فريق تحليل لمنظومة Avalanche/AVAX.`,
    ``,
    `اقرأ أولاً وبالترتيب:`,
    `1. ${ROOT}\\CONSTITUTION.md  — الدستور الملزم (10 مواد).`,
    `2. ${ROOT}\\${agentFile}  — ملف تعريفك: هويتك، مدارسك، منهجك، معايير جودتك، حدودك.`,
    ``,
    `قواعد إلزامية:`,
    `• أنت في طبقة «معرفة» — دورك **advisory** فقط. يُحرَّم عليك إصدار أوامر شراء/بيع (المادة 1.2).`,
    `• كل دليل يجب أن يحمل مصدراً وطابعاً زمنياً. رقم بلا مصدر = رقم مُختلق (المادة 2.5).`,
    `• حقل invalidation إلزامي: الشرط الذي يجعل فرضيتك خاطئة (المادة 2.2).`,
    `• حقل dissent إلزامي: أقوى ما يخالف رأيك (المادة 6).`,
    `• ممنوع لغة اليقين المطلق: «مضمون»، «بلا مخاطر»، «مؤكد» (المادة 8.8).`,
    `• إن كانت بياناتك ناقصة، لك حق **الامتناع** (abstain=true) وهو مشروع ولا يُعاقب (المادة 9).`,
    `• سقف الثقة 88 — لا تعلن ثقة شبه مطلقة.`,
    `• هرمية الأدلة: onchain(1) > market(2) > derived(3) > technical(4) > sentiment(5) > expert(6) > inference(7).`
  ].join("\n");
}

function snapshotBlock(snapshot) {
  const dataFile = args.dataFile;
  return [
    `## اللقطة السوقية (الملخص التنفيذي)`,
    "```json",
    JSON.stringify(snapshot, null, 2),
    "```",
    ``,
    dataFile
      ? [
          `## ⚠️ البيانات الكاملة — اقرأها قبل التحليل`,
          `الملخص أعلاه **ناقص**. البيانات الكاملة في: \`${dataFile}\``,
          `اقرأ الملف بأداة القراءة (read) واستخدم منه:`,
          `• \`ohlcv_daily\` — 120 شمعة (o/h/l/c/v/dv) مع طوابع زمنية`,
          `• \`orderbook\` — أفضل عرض/طلب + 10 مستويات عمق لكل جهة + OBI`,
          `• \`derivatives\` — التمويل، الأساس، الفائدة المفتوحة، L/S، IV، VRP`,
          `• \`onchain\` — التدفقات، العناوين، الاستيكينج، TVL، الجسور، الرسوم`,
          `• \`macro\` و \`fundamentals\` و \`sentiment\``,
          `• \`computed_indicators\` — EMA/RSI/MACD/BB/ATR/ADX/VWAP/Hurst/VaR…`,
          ``,
          `**مهم:** الملف يعلن في \`_meta\` أن مصدره اصطناعي حتمي، فطبقتا الأدلة 1–2`,
          `**غير مستحقتين** له (المادتان 3.1 و3.3). صنّف أدلتك على هذا الأساس.`,
        ].join("\n")
      : `استخدم الأرقام أعلاه فقط. إن احتجت رقماً غير موجود، اذكر أنه غير متاح بدل اختلاقه (المادة 3.3).`,
  ].join("\n");
}

// ── التشغيل ─────────────────────────────────────────────────────────────
phase("0 — بناء اللقطة السوقية");
log(`الرمز: ${args.symbol || "AVAX"} | الوضع السريع: ${args.quick ? "نعم" : "لا"}`);

let snapshot = args.snapshot;
if (!snapshot) {
  log("لا توجد لقطة مُمرَّرة — يستنتجها وكيل البيانات من معلوماته المتاحة");
  snapshot = await agent(
    [
      `أنت «أمين بيانات» في ديسك أفالانش.`,
      `مهمتك: إنتاج لقطة سوقية لـ ${args.symbol || "AVAX"} بصيغة JSON.`,
      `شروط صارمة:`,
      `• إن لم تكن متأكداً من رقم، ضع تقديراً محافظاً واذكره في notes_for_agents مع وسم أنه تقديري.`,
      `• as_of يجب أن يكون طابعاً زمنياً ISO-8601.`,
      `• لا تختلق دقة وهمية — الأرقام التقريبية مقبولة، الأرقام المزيفة مرفوضة (المادة 3.3).`,
      `• املأ كل الحقول المطلوبة في المخطط.`
    ].join("\n"),
    { label: "أمين البيانات", phase: "0 — بناء اللقطة السوقية", schema: SNAPSHOT_SCHEMA }
  );
}

if (!snapshot) {
  return { ok: false, error: "تعذّر بناء اللقطة السوقية — الديسك يمتنع (المادة 9.1)" };
}
log(`اللقطة جاهزة: ${snapshot.asset} @ ${snapshot.price} (${snapshot.as_of})`);

// ── المرحلة 1: طبقة المعرفة ─────────────────────────────────────────────
phase("1 — طبقة المعرفة");

const activeIds = args.quick ? QUICK_AGENTS : KNOWLEDGE_AGENTS.map((a) => a.id);
log(`تشغيل ${activeIds.length} وكيل معرفة بالتوازي`);

const opinions = await parallel(
  activeIds.map((id) => async () => {
    const spec = AGENT_BY_ID[id];
    const prompt = [
      constitutionHeader(spec.file),
      ``,
      `## مهمتك`,
      `أنت الوكيل رقم ${spec.id} — ${spec.name}.`,
      `حلّل اللقطة السوقية من زاويتك التخصصية فقط، وأصدر رأياً مهيكلاً.`,
      ``,
      snapshotBlock(snapshot),
      ``,
      `أعد JSON مطابقاً للمخطط المطلوب حرفياً.`
    ].join("\n");

    const res = await agent(prompt, {
      label: `[${spec.id}] ${spec.name}`,
      phase: "1 — طبقة المعرفة",
      schema: OPINION_SCHEMA
    });
    return res ? { ...res, agent_id: spec.id, agent_name: spec.name } : null;
  })
);

const validOpinions = opinions.filter(Boolean);
const abstained = validOpinions.filter((o) => o.abstain);
const directional = validOpinions.filter((o) => !o.abstain && o.direction !== "neutral");

log(`آراء صالحة: ${validOpinions.length} | امتناع: ${abstained.length} | اتجاهية: ${directional.length}`);
for (const o of validOpinions) {
  log(`  [${o.agent_id}] ${o.direction} ثقة=${o.confidence}`);
}

if (validOpinions.length === 0) {
  return { ok: false, error: "لم يُنتج أي وكيل رأياً صالحاً — امتناع (المادة 9.1)" };
}

// ── المرحلة 2: طبقة التحقق ──────────────────────────────────────────────
phase("2 — طبقة التحقق والشك المنظم");

// حارس المنشأ (المادة 3.1/3.3): البيانات غير الحيّة لا تُصنَّف طبقة 1 أو 2.
// كان الـdigest يثق بتصريح الوكيل عن `kind`، فيرفع بيانات تقديرية إلى «أونشين مباشر» —
// وهي الثغرة نفسها التي أُغلقت في `desks/base.py::BaseAgent.ev`.
const LIVE_SOURCES = ["live", "rpc", "provider-verified"];
const snapshotIsLive = LIVE_SOURCES.includes(String(snapshot.source || "").toLowerCase());

const tierOf = (e) => {
  const base = { onchain: 1, market: 2, derived: 3, technical: 4, sentiment: 5, expert: 6, inference: 7 }[e.kind] || 7;
  if (!snapshotIsLive && base <= 2) return 3;   // تخفيض قسري لبيانات غير موثّقة المنشأ
  return base;
};

const opinionsDigest = validOpinions.map((o) => ({
  agent_id: o.agent_id,
  agent_name: o.agent_name,
  direction: o.direction,
  confidence: o.confidence,
  abstain: o.abstain,
  best_tier: Math.min(...(o.evidence || []).map(tierOf), 7),
  // ⚠️ الطابع الزمني و«القوة» كانا يُحذفان هنا، فلا يستطيع وكيل التحقق (09)
  // تدقيق المادة 2.5 إطلاقاً — وهو ما رصده الوكلاء أنفسهم في تشغيل حقيقي.
  evidence: (o.evidence || []).map((e) => ({
    claim: e.claim, source: e.source, kind: e.kind,
    tier: tierOf(e), timestamp: e.timestamp, strength: e.strength,
  })),
  invalidation: o.invalidation
}));

log(`منشأ اللقطة: ${snapshot.source} ⇒ ${snapshotIsLive ? "مؤهّل لطبقات 1–2" : "طبقات 1–2 مُخفَّضة قسرياً إلى 3 (حارس المنشأ)"}`);

const validation = await parallel([
  async () => agent(
    [
      constitutionHeader("agents/09-validation-backtest.md"),
      ``,
      `## مهمتك`,
      `أنت وكيل التحقق (09). لا تُصدر رأياً اتجاهاً — بل حكماً على **جودة** آراء الآخرين.`,
      `افحص:`,
      `• هل كل دليل يحمل مصدراً وطابعاً زمنياً؟ (المادة 2.5)`,
      `• ما أقوى طبقة دليل يعتمد عليها كل وكيل؟ (المادة 3.1)`,
      `• هل توجد ادّعاءات إحصائية بلا اختبار خارج العينة أو نموذج تكاليف؟ (المادة 4.1)`,
      `• أي نتيجة تبدو استثنائية وتستحق الشك؟ (المادة 4.2)`,
      ``,
      `## آراء الوكلاء`,
      "```json",
      JSON.stringify(opinionsDigest, null, 2),
      "```",
      ``,
      `أعد رأياً مهيكلاً مع حقل evidence يوضح أحكامك، واذكر في metrics أي وكيل يحتاج خصماً.`
    ].join("\n"),
    { label: "[09] وكيل التحقق", phase: "2 — طبقة التحقق", schema: OPINION_SCHEMA }
  ),
  async () => agent(
    [
      constitutionHeader("agents/10-red-team.md"),
      ``,
      `## مهمتك`,
      `أنت محامي الشيطان (10). مهمتك الوحيدة: بناء **أقوى حجة مضادة** للإجماع.`,
      `يُحرَّم عليك تقديم فرضية سوقية خاصة بك (المادة 1.3).`,
      `إن لم تجد ما يخالف الإجماع، صرّح بذلك كتابةً مع التبرير (المادة 4.3).`,
      `ابحث خصوصاً عن: تناقض بين دليل قوي ودليل ضعيف، إشارات طبقة 4/5 تُستخدم كأنها قوية،`,
      `سيناريوهات فشل بنيوية على أفالانش (فك استيكينج، اختراق جسر، خروج سيولة، شوكة شبكة).`,
      ``,
      `## آراء الوكلاء`,
      "```json",
      JSON.stringify(opinionsDigest, null, 2),
      "```",
      ``,
      `اجعل direction معاكساً للإجماع، وضع الحجة المضادة في thesis و dissent.`
    ].join("\n"),
    { label: "[10] محامي الشيطان", phase: "2 — طبقة التحقق", schema: OPINION_SCHEMA }
  )
]);

const validationOp = validation[0];
const redTeamOp = validation[1];
log(`التحقق: ${validationOp ? "تم" : "فشل"} | محامي الشيطان: ${redTeamOp ? redTeamOp.direction : "فشل"}`);

// ── المرحلة 3: طبقة الضبط — المخاطر أولاً ───────────────────────────────
phase("3 — طبقة الضبط (المخاطر)");

const bulls = directional.filter((o) => o.direction === "bullish");
const bears = directional.filter((o) => o.direction === "bearish");
const proposedDirection = bulls.length > bears.length ? "bullish"
  : bears.length > bulls.length ? "bearish" : "neutral";
const agreement = directional.length
  ? Math.max(bulls.length, bears.length) / directional.length : 0;

const avgConf = (list) => list.length
  ? list.reduce((s, o) => s + (o.confidence || 0), 0) / list.length : 0;
const supporting = proposedDirection === "bullish" ? bulls : bears;

const riskVerdict = await agent(
  [
    constitutionHeader("agents/11-risk-manager.md"),
    ``,
    `## مهمتك`,
    `أنت وكيل المخاطر (11). لك **حق النقض** (المادة 5.1). لا تُصدر فرضية سوقية (المادة 1.3).`,
    ``,
    `## المقترح المعروض عليك`,
    `- الاتجاه المقترح: ${proposedDirection}`,
    `- عدد المؤيدين: ${supporting.length} | المعارضين: ${directional.length - supporting.length}`,
    `- نسبة الاتفاق: ${(agreement * 100).toFixed(0)}%`,
    `- متوسط ثقة المؤيدين: ${avgConf(supporting).toFixed(1)}`,
    `- رأس المال: $${(args.capitalUsd || 1000000).toLocaleString()}`,
    ``,
    `## الحدود الملزمة (المادة 5.3)`,
    `- أقصى خسارة يومية: 2% | أقصى تراجع: 15% | أقصى مركز: 10% من رأس المال`,
    `- الحد الأدنى للثقة للدخول: 65 | أقصى مشاركة من حجم السوق: 5%`,
    `- كيلي مقيد: نصف كيلي كحد أقصى (المادة 5.5)`,
    `- المادة 8.7: لا التفاف على الحدود بتقسيم المراكز — التعرّض الكلي يشمل ما هو مفتوح`,
    ``,
    `## المراكز المفتوحة حالياً (لمنع تقسيم المراكز — المادة 8.7)`,
    "```json",
    JSON.stringify(args.openPositions || [], null, 2),
    "```",
    args.openPositions && args.openPositions.length
      ? `⚠️ مجموع التعرّض المفتوح = ${(args.openPositions.reduce((s, p) => s + (p.notional_usd || 0), 0)).toLocaleString()}$`
      : `لا مراكز مفتوحة مُمرَّرة.`,
    ``,
    `## اللقطة السوقية`,
    snapshotBlock(snapshot),
    ``,
    `احسب حجم المركز بالمخاطرة الثابتة: (رأس المال × نسبة المخاطرة) ÷ مسافة الوقف.`,
    `واقنض أي مخالفة. أعد JSON مطابقاً للمخطط.`
  ].join("\n"),
  { label: "[11] وكيل المخاطر", phase: "3 — طبقة الضبط", schema: RISK_SCHEMA }
);

log(`المخاطر: ${riskVerdict ? (riskVerdict.veto ? "🚫 نقض" : "✅ موافقة") : "فشل"}`);
if (riskVerdict && riskVerdict.veto) {
  for (const r of riskVerdict.veto_reasons || []) log(`   ⛔ ${r}`);
}

// ── المرحلة 3ب: الالتزام (المرور الأول — قبل القرار) ──────────────────────
// ثغرة مُصلَحة: السكربت لم يُشغّل وكيل الالتزام (13) إطلاقاً، فرصد الوكلاء أنفسهم
// في تشغيل حقيقي أن «بوابة الالتزام غير مكتملة والترجيح لا يبدأ».
phase("3ب — طبقة الضبط (الالتزام)");

const complianceVerdict = await agent(
  [
    constitutionHeader("agents/13-compliance-audit.md"),
    ``,
    `## مهمتك`,
    `أنت وكيل الالتزام والتدقيق (13). لك **حق النقض** على المخالفات (المادة 8).`,
    `دقّق آراء الوكلاء 01–12 مقابل الدستور:`,
    `• المادة 2.2: هل لكل رأي شرط إبطال؟`,
    `• المادة 2.5: هل لكل دليل مصدر وطابع زمني؟`,
    `• المادة 3.1/3.2: هل توجد أدلة أولية (طبقة 1 أو 2) أم كلها ضعيفة؟`,
    `• المادة 8: هل يوجد نص محرّم (تنفيذ، يقين مطلق، اختلاق، تحيّز استرجاعي)؟`,
    `• المادة 8.7: هل هناك التفاف على الحدود بتقسيم المراكز؟`,
    ``,
    `## آراء الوكلاء (مع الطوابع الزمنية والقوة وطبقة الدليل)`,
    "```json",
    JSON.stringify(opinionsDigest, null, 2),
    "```",
    ``,
    `## حكم المخاطر`,
    "```json",
    JSON.stringify(riskVerdict, null, 2),
    "```",
    ``,
    `أعد رأياً مهيكلاً: direction = neutral، agent_id = "13"، واجعل abstain=false.`,
    `ضع في thesis خلاصة التدقيق (مطابق/حجب)، وفي metrics عدد المخالفات ونوعها.`
  ].join("\n"),
  { label: "[13] وكيل الالتزام", phase: "3ب — طبقة الضبط", schema: OPINION_SCHEMA }
);

const complianceBlocked = !complianceVerdict || complianceVerdict.abstain === true
  ? false
  : /حجب|مخالف|⛔/.test(String(complianceVerdict.thesis || ""));
log(`الالتزام: ${complianceVerdict ? (complianceBlocked ? "⛔ حجب" : "✅ متوافق") : "فشل"}`);

// ── المرحلة 4: القرار النهائي ───────────────────────────────────────────
phase("4 — القرار النهائي");

const riskBlocked = !riskVerdict || riskVerdict.veto;

let decision = await agent(
  [
    constitutionHeader("agents/14-orchestrator.md"),
    ``,
    `## مهمتك`,
    `أنت المنسّق (14). أصدر القرار النهائي.`,
    `يُحرَّم عليك إنتاج دليل جديد — أنت تجمع وترجّح فقط (المادة 1.4).`,
    `يُحرَّم عليك تجاوز نقض المخاطر (المادة 5.1).`,
    `قرار بلا رأي مخالف مسجّل يُرفض (المادة 6.3).`,
    ``,
    `## حكم المخاطر`,
    riskBlocked
      ? `🚫 **نقض نافذ** — لا يجوز فتح مركز. الأسباب: ${JSON.stringify(riskVerdict ? riskVerdict.veto_reasons : ["فشل وكيل المخاطر"])}`
      : `✅ موافقة بحجم $${riskVerdict.position_size_usd} بوقف ${riskVerdict.stop_loss_pct}%`,
    ``,
    `## آراء طبقة المعرفة`,
    "```json",
    JSON.stringify(opinionsDigest, null, 2),
    "```",
    ``,
    `## رأي وكيل التحقق (09)`,
    "```json",
    JSON.stringify(validationOp, null, 2),
    "```",
    ``,
    `## رأي محامي الشيطان (10)`,
    "```json",
    JSON.stringify(redTeamOp, null, 2),
    "```",
    ``,
    `## تقرير الالتزام (13)`,
    "```json",
    JSON.stringify(complianceVerdict, null, 2),
    "```",
    complianceBlocked
      ? `⛔ **حجب من الالتزام** — يُحوّل القرار إلى ABSTAIN (المادة 8).`
      : `✅ الالتزام متوافق.`,
    ``,
    `## قواعد القرار`,
    `- ثقة مجمّعة = 0.45×متوسط ثقة المؤيدين + 0.30×100×نسبة الاتفاق + 0.25×100×قوة الإشارة`,
    `- خصومات: −4 لمحامي الشيطان على نفس الاتجاه، −6 إن لم تجتز الجودة، −5 إن كان المؤيدون أقل من 3`,
    `- الحد الأدنى للدخول 65 وإلا فالامتناع`,
    `- إن كان الإجماع ≥95% مع 5 وكلاء أو أكثر، أشر إلى خطر Groupthink (المادة 4.4)`,
    `- اذكر في blocks كل سبب يمنع القرار، وفي strongest_dissent أقوى حجة مضادة.`
  ].join("\n"),
  { label: "[14] المنسّق / مدير المحفظة", phase: "4 — القرار النهائي", schema: DECISION_SCHEMA }
);

// ── احتياط ثلاثي: إعادة محاولة ← قرار حتمي مشتق ─────────────────────────
// ثغرة مُصلَحة: في تشغيل حقيقي على بيانات سوق أعاد `agent()` قيمة فارغة
// للمنسّق، فأُسقطت الدورة كلها برسالة «فشل المنسّق». وكيل واحد لا يجوز أن
// يُسقط تحليل أربعة عشر وكيلاً.
if (!decision) {
  log("  ⚠️ المنسّق: المحاولة الأولى فشلت — إعادة بنص مختصر");
  decision = await agent(
    [
      "أنت المنسّق (14) في ديسك أفالانش. أعد JSON فقط بلا شرح.",
      `اتجاه مرجّح: ${proposedDirection} | اتفاق: ${(agreement * 100).toFixed(0)}%`,
      `حكم المخاطر: ${riskBlocked ? "نقض نافذ — القرار ABSTAIN" : "موافقة بحجم " + riskVerdict.position_size_usd}`,
      "ملخص الآراء: " + JSON.stringify(opinionsDigest.map((o) => ({
        a: o.agent_id, d: o.direction, c: o.confidence, t: o.best_tier,
      }))),
      "أقوى حجة مضادة: " + String((redTeamOp || {}).thesis || "—").slice(0, 260),
      "الحد الأدنى للثقة 65. املأ كل حقول المخطط."
    ].join("\n"),
    { label: "[14] المنسّق (محاولة 2)", phase: "4 — القرار النهائي", schema: DECISION_SCHEMA }
  );
}

if (!decision) {
  // قرار احتياطي **حتمي** مشتق حسابياً من مخرجات الوكلاء (لا رأي جديد — المادة 1.4)
  const b = !riskVerdict || riskVerdict.veto;
  const sup0 = supporting.length ? supporting.reduce((s, o) => s + (o.confidence || 0), 0) / supporting.length : 0;
  let conf = 0.45 * sup0 + 30 * agreement + 25 * Math.min(1, agreement);
  conf = Math.max(0, Math.min(88, conf - (b ? 10 : 0)));
  const act = (b || proposedDirection === "neutral" || conf < 65)
    ? "ABSTAIN" : (proposedDirection === "bullish" ? "LONG" : "SHORT");
  log("  ⛔ المنسّق فشل مرتين — يُشتق قرار حتمي من الأرقام (الدورة لا تسقط)");
  decision = {
    action: act,
    confidence: Number(conf.toFixed(2)),
    horizon: "أيام إلى أسابيع",
    rationale: "[قرار احتياطي حتمي — فشل وكيل المنسّق فلم يُترك القرار معلّقاً] " +
      `اتجاه مرجّح: ${proposedDirection} باتفاق ${(agreement * 100).toFixed(0)}%، ` +
      `حكم المخاطر: ${b ? "نقض" : "موافقة"}، الثقة المحسوبة ${conf.toFixed(1)}. ` +
      "مشتق حسابياً من مخرجات الوكلاء لا من رأي وكيل جديد (المادة 1.4).",
    invalidation: b
      ? "يبقى الامتناع حتى يزول سبب النقض ويصدر حكم مخاطر جديد غير منقوض."
      : "يُبطل عند تجاوز حد الخسارة اليومية أو انقلاب التدفقات الأونشين.",
    strongest_dissent: String(((redTeamOp || {}).dissent) || ((redTeamOp || {}).thesis) || "لم يُسجَّل مخالف.").slice(0, 600),
    supporting_agents: supporting.map((o) => o.agent_id),
    opposing_agents: directional.filter((o) => supporting.indexOf(o) < 0).map((o) => o.agent_id),
    blocks: b ? ["نقض من وكيل المخاطر (المادة 5.1)"] : [],
    size_usd: b ? 0 : (riskVerdict ? riskVerdict.position_size_usd : 0),
    _fallback: true,
  };
}

log(`القرار: ${decision.action} بثقة ${decision.confidence}${decision._fallback ? " (احتياطي)" : ""}`);

// ── المرحلة 5: الذاكرة والتسجيل ─────────────────────────────────────────
// ثغرة مُصلَحة: السكربت لم يُشغّل وكيل الذاكرة (15)، فلم يكن للسجل وكيل مسؤول —
// ورصد الوكلاء أنفسهم غيابه في تشغيل حقيقي.
phase("5 — الذاكرة والسجل");

const journalRecord = await agent(
  [
    constitutionHeader("agents/15-memory-journal.md"),
    ``,
    `## مهمتك`,
    `أنت وكيل الذاكرة والسجل (15). سجّل هذه الدورة بصيغة قابلة للكتابة في السجل.`,
    `المادتان 7.1 و7.2: السجل غير قابل للتعديل، والتسجيل إلزامي.`,
    `المادة 7.3: حدّد الأفق الذي تصبح عنده المراجعة البعدية مستحقة.`,
    `المادة 7.4: اذكر أوزان الوكلاء المستخدمة وهل يجب تخفيضها.`,
    ``,
    `## القرار النهائي`,
    "```json",
    JSON.stringify(decision, null, 2),
    "```",
    ``,
    `## حكم المخاطر`,
    "```json",
    JSON.stringify(riskVerdict, null, 2),
    "```",
    ``,
    `أعد رأياً مهيكلاً: direction = neutral، agent_id = "15"، واجعل abstain=false.`,
    `ضع في thesis خلاصة التسجيل ورقم الدورة المتوقع، وفي metrics: ${JSON.stringify({has_decision: true})}.`
  ].join("\n"),
  { label: "[15] وكيل الذاكرة", phase: "5 — الذاكرة والسجل", schema: OPINION_SCHEMA }
);
log(`الذاكرة: ${journalRecord ? "سُجّلت الدورة" : "فشل التسجيل"}`);

// ── النتيجة ─────────────────────────────────────────────────────────────
const longShort = decision.action === "LONG" || decision.action === "SHORT";
const groupthink = directional.length >= 5 && agreement >= 0.95;

return {
  ok: true,
  symbol: snapshot.asset,
  as_of: snapshot.as_of,
  consensus: {
    direction: proposedDirection,
    bulls: bulls.length,
    bears: bears.length,
    neutrals: validOpinions.length - directional.length - abstained.length,
    abstained: abstained.length,
    agreement: Number(agreement.toFixed(4)),
    groupthink_risk: groupthink
  },
  decision,
  risk_verdict: riskVerdict,
  compliance_verdict: complianceVerdict,
  journal_verdict: journalRecord,
  provenance_guard: {
    snapshot_source: snapshot.source,
    live_verified: snapshotIsLive,
    note: snapshotIsLive
      ? "اللقطة مؤهّلة لطبقات 1–2"
      : "طبقات 1–2 مُخفَّضة قسرياً إلى 3 لأن منشأ اللقطة غير موثّق (المادة 3.1/3.3)",
  },
  validation: validationOp ? { direction: validationOp.direction, thesis: validationOp.thesis } : null,
  red_team: redTeamOp ? { direction: redTeamOp.direction, thesis: redTeamOp.thesis, dissent: redTeamOp.dissent } : null,
  opinions: validOpinions.map((o) => ({
    agent_id: o.agent_id,
    agent_name: o.agent_name,
    direction: o.direction,
    confidence: o.confidence,
    thesis: o.thesis,
    invalidation: o.invalidation,
    evidence_count: (o.evidence || []).length
  })),
  constitutional_note: longShort
    ? "قرار اتجاهي صادر — تحليل فقط، ولا تنفيذ حقيقي (المادة 0.2)"
    : "الديسك امتنع — الامتناع قرار مشروع وأفضل من رأي ضعيف (المادة 0.4)"
};
