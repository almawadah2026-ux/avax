/* ديسك أفالانش — لوحة المعاينة
   لا تعتمد على أي مكتبة خارجية. تقرأ من Supabase REST بمفتاح publishable محميّ بـRLS. */

const CFG = window.AVAX_DESK_CONFIG || {};
const API = (CFG.SUPABASE_URL || "").replace(/\/$/, "");
const KEY = CFG.SUPABASE_PUBLISHABLE_KEY || "";

const $ = (id) => document.getElementById(id);

async function sb(path, params = "") {
  const url = `${API}/rest/v1/${path}${params ? "?" + params : ""}`;
  const res = await fetch(url, {
    headers: { apikey: KEY, Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status} — ${(await res.text()).slice(0, 160)}`);
  return res.json();
}

/* ── أدوات عرض ─────────────────────────────────────────────────────── */
const ACTION_AR = {
  LONG: "🟢 شراء", SHORT: "🔴 بيع", FLAT: "⚪ خارج السوق", ABSTAIN: "⏸️ امتناع",
};
const KIND_AR = {
  no_edge: "لا حافة مرجّحة", risk_veto: "نقض من المخاطر",
  compliance_block: "حجب من الالتزام", halted: "الديسك موقوف",
};
const DIR_AR = { bullish: "🟢 صاعد", bearish: "🔴 هابط", neutral: "⚪ محايد" };
const TIER_AR = {
  1: "أونشين مباشر", 2: "سوق متعدد", 3: "إحصاء مشتق", 4: "مؤشر فني",
  5: "معنويات", 6: "رأي خبير", 7: "استنتاج",
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = (v, d = 2) => (v === null || v === undefined || v === "") ? "—" : Number(v).toFixed(d);
const money = (v) => (v === null || v === undefined) ? "—" : "$" + Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
const when = (s) => s ? new Date(s).toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "short" }) : "—";

/* ── الحالة ────────────────────────────────────────────────────────── */
let RUNS = [];
let CURRENT = null;

/* ── الاتصال ───────────────────────────────────────────────────────── */
async function boot() {
  if (!API || !KEY) {
    $("conn").textContent = "⚠️ ملف config.js مفقود";
    $("conn").className = "conn bad";
    $("detail").innerHTML =
      `<div class="empty"><h3>لا إعدادات</h3>
       <p>انسخ <code>web/config.example.js</code> إلى <code>web/config.js</code> واملأ القيم.</p>
       <pre>SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...</pre></div>`;
    return;
  }
  try {
    await loadRuns();
    $("conn").textContent = "✅ متصل";
    $("conn").className = "conn ok";
  } catch (e) {
    $("conn").textContent = "⛔ تعذّر الاتصال";
    $("conn").className = "conn bad";
    $("run-list").innerHTML = `<li class="muted">${esc(e.message)}</li>`;
  }
}

async function loadRuns() {
  RUNS = await sb("v_run_summary", "select=*&order=created_at.desc&limit=100");
  renderStats();
  renderRunList();
  $("foot-meta").textContent = `${RUNS.length} دورة · آخر تحديث ${when(new Date().toISOString())}`;
}

/* ── الإحصاءات ─────────────────────────────────────────────────────── */
function renderStats() {
  const total = RUNS.length;
  const directional = RUNS.filter((r) => r.action === "LONG" || r.action === "SHORT").length;
  const abstained = RUNS.filter((r) => r.action === "ABSTAIN").length;
  const vetoed = RUNS.filter((r) => r.risk_veto).length;
  const live = RUNS.filter((r) => r.data_source === "live").length;
  const avgConf = total
    ? (RUNS.reduce((s, r) => s + Number(r.confidence || 0), 0) / total).toFixed(1) : "—";
  const opinions = RUNS.reduce((s, r) => s + Number(r.opinions || 0), 0);

  $("stats").innerHTML = [
    ["إجمالي الدورات", total],
    ["قرارات اتجاهية", `${directional} (${total ? Math.round(directional / total * 100) : 0}%)`],
    ["امتناع", `${abstained} (${total ? Math.round(abstained / total * 100) : 0}%)`],
    ["نقض مخاطر", vetoed],
    ["متوسط الثقة", avgConf],
    ["آراء مسجّلة", opinions],
    ["دورات ببيانات حيّة", live],
  ].map(([k, v]) => `<div class="stat"><div class="v">${esc(v)}</div><div class="k">${esc(k)}</div></div>`).join("");
}

/* ── قائمة الدورات ─────────────────────────────────────────────────── */
function renderRunList() {
  if (!RUNS.length) {
    $("run-list").innerHTML = `<li class="muted">لا دورات مسجّلة بعد. شغّل:
      <code>python -m avax_desk.cli --live --push</code></li>`;
    return;
  }
  $("run-list").innerHTML = RUNS.map((r) => `
    <li class="run ${r.run_id === CURRENT ? "active" : ""}" data-id="${esc(r.run_id)}">
      <div class="run-top">
        <span class="act act-${esc(r.action || "ABSTAIN")}">${esc(ACTION_AR[r.action] || r.action || "—")}</span>
        <span class="conf">${num(r.confidence, 1)}</span>
      </div>
      <div class="run-meta">
        <span>${esc(r.asset || "—")}</span>
        <span class="dot">·</span>
        <span class="src src-${esc(r.data_source || "")}">${r.data_source === "live" ? "حيّ" : "اصطناعي"}</span>
        <span class="dot">·</span>
        <span>${when(r.created_at)}</span>
      </div>
      <div class="run-meta2">
        ${r.abstention_kind ? `<span class="tag">${esc(KIND_AR[r.abstention_kind] || r.abstention_kind)}</span>` : ""}
        ${r.risk_veto ? `<span class="tag bad">نقض</span>` : ""}
        ${r.compliant === false ? `<span class="tag bad">حجب</span>` : ""}
        ${r.decision_valid === false ? `<span class="tag bad">قرار غير صالح</span>` : ""}
      </div>
    </li>`).join("");

  document.querySelectorAll(".run").forEach((el) =>
    el.addEventListener("click", () => openRun(el.dataset.id)));
}

/* ── تفاصيل دورة ───────────────────────────────────────────────────── */
async function openRun(runId) {
  CURRENT = runId;
  renderRunList();
  $("detail").innerHTML = `<p class="muted">جارٍ التحميل…</p>`;
  try {
    const [dec, risk, comp, audit, ops, evs] = await Promise.all([
      sb("decisions", `select=*&run_id=eq.${runId}`),
      sb("risk_verdicts", `select=*&run_id=eq.${runId}`),
      sb("compliance_reports", `select=*&run_id=eq.${runId}`),
      sb("post_decision_audits", `select=*&run_id=eq.${runId}`),
      sb("agent_opinions", `select=*&run_id=eq.${runId}&order=agent_id.asc`),
      sb("evidence_items", `select=*&run_id=eq.${runId}&order=tier.asc&limit=400`),
    ]);
    renderDetail({ dec: dec[0], risk: risk[0], comp: comp[0], audit: audit[0], ops, evs });
  } catch (e) {
    $("detail").innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function renderDetail({ dec, risk, comp, audit, ops, evs }) {
  const evByAgent = {};
  evs.forEach((e) => { (evByAgent[e.agent_id] = evByAgent[e.agent_id] || []).push(e); });

  const blocks = (dec?.blocks || []).map((b) => `<li>⛔ ${esc(b)}</li>`).join("");
  const veto = (risk?.veto_reasons || []).map((b) => `<li>⛔ ${esc(b)}</li>`).join("");
  const viol = (comp?.violations || []);
  const auditViol = (audit?.violations || []);

  const opinionsHtml = ops.map((o) => {
    const evs2 = (evByAgent[o.agent_id] || []).map((e) => `
      <li class="ev ev-t${e.tier}">
        <span class="tier">طبقة ${e.tier} · ${esc(TIER_AR[e.tier] || "")}</span>
        <span class="claim">${esc(e.claim)}</span>
        <span class="evsrc">${esc(e.source)} · ${when(e.timestamp)}</span>
      </li>`).join("");
    return `
    <details class="op ${o.abstain ? "op-abstain" : "op-" + o.direction}">
      <summary>
        <span class="op-id">${esc(o.agent_id)}</span>
        <span class="op-name">${esc(o.agent_name)}</span>
        <span class="op-dir">${o.abstain ? "⏸️ امتناع" : esc(DIR_AR[o.direction] || o.direction)}</span>
        <span class="op-conf">${num(o.net_confidence ?? o.confidence, 1)}</span>
        <span class="op-tier">طبقة ${o.best_tier ?? "—"}</span>
      </summary>
      <div class="op-body">
        ${o.abstain
          ? `<p><strong>سبب الامتناع:</strong> ${esc(o.abstain_reason || "—")}</p>`
          : `<p><strong>الفرضية:</strong> ${esc(o.thesis)}</p>`}
        ${o.invalidation ? `<p><strong>شرط الإبطال:</strong> ${esc(o.invalidation)}</p>` : ""}
        ${o.dissent ? `<p><strong>المخالف:</strong> ${esc(o.dissent)}</p>` : ""}
        <p class="small">الأفق: ${esc(o.horizon || "—")} · الصلاحية: ${esc(o.authority)} · الطبقة: ${esc(o.layer)}</p>
        ${evs2 ? `<ul class="evs">${evs2}</ul>` : `<p class="muted small">لا أدلة مسجّلة.</p>`}
      </div>
    </details>`;
  }).join("");

  $("detail").innerHTML = `
    <div class="card">
      <h2 class="card-title">${esc(ACTION_AR[dec?.action] || dec?.action || "لا قرار")}
        <span class="badge">ثقة ${num(dec?.confidence, 2)}</span>
        ${dec?.groupthink_flag ? `<span class="badge bad">🚨 Groupthink</span>` : ""}
      </h2>
      ${dec?.abstention_kind ? `<p class="muted">نوع الامتناع: <strong>${esc(KIND_AR[dec.abstention_kind] || dec.abstention_kind)}</strong></p>` : ""}
      <div class="grid">
        <div><span class="k">المعرّف</span><span class="v">${esc(dec?.decision_code || "—")}</span></div>
        <div><span class="k">حجم المركز</span><span class="v">${money(dec?.size_usd)}</span></div>
        <div><span class="k">الوقف</span><span class="v">${num(dec?.stop_price, 4)}</span></div>
        <div><span class="k">الأفق</span><span class="v">${esc(dec?.horizon || "—")}</span></div>
        <div><span class="k">نطاق الدخول</span><span class="v">${(dec?.entry_zone || []).map((x) => num(x, 4)).join(" – ") || "—"}</span></div>
        <div><span class="k">الأهداف</span><span class="v">${(dec?.targets || []).map((x) => num(x, 4)).join(" / ") || "—"}</span></div>
      </div>
      ${blocks ? `<h3>أسباب المنع</h3><ul class="blocks">${blocks}</ul>` : ""}
      <h3>المبرر</h3><p class="rationale">${esc(dec?.rationale || "—")}</p>
      <h3>شرط الإبطال</h3><p>${esc(dec?.invalidation || "—")}</p>
      <h3>الرأي المخالف <span class="tag">مصدره: ${esc(dec?.dissent_source || "—")}</span></h3>
      <p class="dissent">${esc(dec?.strongest_dissent || "—")}</p>
    </div>

    <div class="card">
      <h2 class="card-title">المخاطر <span class="badge ${risk?.veto ? "bad" : "ok"}">${risk?.veto ? "نقض" : "موافقة"}</span>
        <span class="badge">${esc(risk?.risk_level || "—")}</span></h2>
      <div class="grid">
        <div><span class="k">الحجم المعتمد</span><span class="v">${money(risk?.position_size_usd)}</span></div>
        <div><span class="k">الحجم المحسوب</span><span class="v">${money(risk?.computed_size_usd)}</span></div>
        <div><span class="k">الوقف</span><span class="v">${num(risk?.stop_loss_pct, 2)}%</span></div>
        <div><span class="k">مخاطرة/صفقة</span><span class="v">${num(risk?.risk_per_trade_pct, 3)}%</span></div>
        <div><span class="k">القيد الملزم</span><span class="v">${esc(risk?.limits_checked?.binding_constraint || "—")}</span></div>
        <div><span class="k">كيلي مُلزِم</span><span class="v">${risk?.limits_checked?.kelly_binding ? "نعم" : "لا (مُعلن)"}</span></div>
      </div>
      ${veto ? `<h3>أسباب النقض</h3><ul class="blocks">${veto}</ul>` : ""}
    </div>

    <div class="card">
      <h2 class="card-title">الالتزام والتدقيق</h2>
      <p>الالتزام: <strong class="${comp?.compliant ? "ok-t" : "bad-t"}">${comp?.compliant ? "✅ متوافق" : "⛔ غير متوافق"}</strong>
         · ${comp?.checked_agents ?? "—"} رأياً مفحوصاً · ${viol.length} مخالفة</p>
      <p>التدقيق البعدي للقرار: <strong class="${audit?.valid ? "ok-t" : "bad-t"}">${audit ? (audit.valid ? "✅ صالح" : "⛔ غير صالح") : "—"}</strong>
         · ${audit?.checks_run ?? "—"} فحصاً · ${audit?.critical ?? 0} حرجة</p>
      ${viol.length ? `<ul class="blocks">${viol.slice(0, 10).map((v) =>
        `<li>${v.severity === "error" ? "⛔" : "⚠️"} [م${esc(v.article)}] ${esc(v.message)}</li>`).join("")}</ul>` : ""}
      ${auditViol.length ? `<ul class="blocks">${auditViol.slice(0, 10).map((v) =>
        `<li>${v.severity === "error" ? "⛔" : "⚠️"} [م${esc(v.article)}] ${esc(v.message)}</li>`).join("")}</ul>` : ""}
    </div>

    <div class="card">
      <h2 class="card-title">آراء الوكلاء <span class="badge">${ops.length}</span></h2>
      ${opinionsHtml || `<p class="muted">لا آراء.</p>`}
    </div>`;
}

$("refresh").addEventListener("click", () => boot().catch(() => {}));
document.addEventListener("DOMContentLoaded", boot);
