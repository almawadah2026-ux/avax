-- ═══════════════════════════════════════════════════════════════════════
--  ديسك أفالانش — مخطط قاعدة البيانات (Supabase / Postgres)
--  يخزّن كل دورة قرار بكل مكوناتها، مع سلسلة هاش للسجل (المادة 7.2).
--
--  قواعد التصميم:
--   1. لا يُخزَّن سرّ هنا مطلقاً.
--   2. كل جدول مرتبط بدورة (`run_id`) — لا صفوف يتيمة.
--   3. القراءة العامة مسموحة (لوحة المعاينة)، والكتابة لـ service_role فقط.
--   4. السجل **يُلحق فقط** ولا يُعدَّل (trigger يمنع UPDATE/DELETE).
-- ═══════════════════════════════════════════════════════════════════════

create extension if not exists "pgcrypto";

-- ── التصنيفات ──────────────────────────────────────────────────────────
do $$ begin
  create type desk_direction as enum ('bullish','bearish','neutral');
exception when duplicate_object then null; end $$;

do $$ begin
  create type desk_action as enum ('LONG','SHORT','FLAT','ABSTAIN');
exception when duplicate_object then null; end $$;

do $$ begin
  create type desk_risk_level as enum ('green','yellow','orange','red');
exception when duplicate_object then null; end $$;

-- ── 1) اللقطات السوقية ─────────────────────────────────────────────────
create table if not exists snapshots (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  asset         text not null,
  as_of         timestamptz not null,
  source        text not null,                    -- live | synthetic | manual
  price         numeric,
  missing_fields text[] not null default '{}',
  payload       jsonb not null,                   -- اللقطة الكاملة
  consistency   jsonb                             -- فحص الاتساق الذاتي
);
create index if not exists snapshots_asset_asof_idx on snapshots (asset, as_of desc);

-- ── 2) دورات التشغيل ───────────────────────────────────────────────────
create table if not exists desk_runs (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  run_label     text,                             -- معرّف بشري للدورة
  snapshot_id   uuid references snapshots(id) on delete set null,
  asset         text not null,
  capital_usd   numeric not null,
  data_source   text not null,
  live_verified boolean not null default false,
  constitution_sha256 text,
  law_audit     jsonb,
  abstention_rate numeric,
  meta          jsonb not null default '{}'::jsonb
);
create index if not exists desk_runs_created_idx on desk_runs (created_at desc);

-- ── 3) آراء الوكلاء ────────────────────────────────────────────────────
create table if not exists agent_opinions (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null references desk_runs(id) on delete cascade,
  agent_id      text not null,
  agent_name    text not null,
  layer         text not null,
  authority     text not null,
  direction     desk_direction not null,
  confidence    numeric not null check (confidence >= 0 and confidence <= 100),
  net_confidence numeric,
  best_tier     int check (best_tier between 1 and 7),
  horizon       text,
  thesis        text,
  invalidation  text,
  dissent       text,
  abstain       boolean not null default false,
  abstain_reason text,
  metrics       jsonb not null default '{}'::jsonb,
  notes         text[] not null default '{}',
  created_at    timestamptz not null default now(),
  unique (run_id, agent_id)
);
create index if not exists agent_opinions_run_idx on agent_opinions (run_id);

-- ── 4) الأدلة ──────────────────────────────────────────────────────────
create table if not exists evidence_items (
  id            uuid primary key default gen_random_uuid(),
  opinion_id    uuid not null references agent_opinions(id) on delete cascade,
  run_id        uuid not null references desk_runs(id) on delete cascade,
  claim         text not null,
  source        text not null,
  timestamp     timestamptz not null,
  kind          text not null,
  tier          int not null check (tier between 1 and 7),
  strength      text not null,
  value         numeric
);
create index if not exists evidence_items_run_idx on evidence_items (run_id);
create index if not exists evidence_items_tier_idx on evidence_items (run_id, tier);

-- ── 5) أحكام المخاطر ───────────────────────────────────────────────────
create table if not exists risk_verdicts (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null unique references desk_runs(id) on delete cascade,
  approved      boolean not null,
  veto          boolean not null,
  risk_level    desk_risk_level not null,
  position_size_usd numeric not null default 0,
  computed_size_usd numeric not null default 0,
  stop_loss_pct numeric,
  risk_per_trade_pct numeric,
  veto_reasons  text[] not null default '{}',
  limits_checked jsonb not null default '{}'::jsonb,
  notes         text[] not null default '{}',
  created_at    timestamptz not null default now(),
  constraint risk_consistency check (
    not (approved and veto)
    and not (approved and position_size_usd <= 0)
    and not (veto and position_size_usd > 0)
  )
);

-- ── 6) القرارات ────────────────────────────────────────────────────────
create table if not exists decisions (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null unique references desk_runs(id) on delete cascade,
  decision_code text not null,                    -- DEC-XXXXXXXX
  asset         text not null,
  action        desk_action not null,
  confidence    numeric not null check (confidence >= 0 and confidence <= 100),
  horizon       text,
  rationale     text,
  invalidation  text,
  strongest_dissent text,
  dissent_source text,                            -- agent | fallback | none
  abstention_kind text,                           -- no_edge | risk_veto | compliance_block | halted
  blocks        text[] not null default '{}',
  groupthink_flag boolean not null default false,
  supporting_agents text[] not null default '{}',
  opposing_agents   text[] not null default '{}',
  abstaining_agents text[] not null default '{}',
  entry_zone    numeric[],
  stop_price    numeric,
  targets       numeric[],
  size_usd      numeric not null default 0,
  evidence_summary jsonb,
  created_at    timestamptz not null default now()
);
create index if not exists decisions_action_idx on decisions (action, created_at desc);

-- ── 7) خطط التنفيذ (نظرية — المادة 0.2) ────────────────────────────────
create table if not exists execution_plans (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null unique references desk_runs(id) on delete cascade,
  method        text,
  slices        int,
  participation_pct numeric,
  expected_slippage_bps numeric,
  expected_cost_usd numeric,
  schedule      jsonb,
  venue_notes   text[] not null default '{}',
  disclaimer    text
);

-- ── 8) تقارير الالتزام ─────────────────────────────────────────────────
create table if not exists compliance_reports (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null unique references desk_runs(id) on delete cascade,
  compliant     boolean not null,
  blocked       boolean not null,
  checked_agents int,
  violations    jsonb not null default '[]'::jsonb,
  notes         text[] not null default '{}',
  created_at    timestamptz not null default now()
);

-- ── 9) التدقيق البعدي للقرار ───────────────────────────────────────────
create table if not exists post_decision_audits (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null unique references desk_runs(id) on delete cascade,
  valid         boolean not null,
  checks_run    int,
  violations_found int,
  critical      int,
  violations    jsonb not null default '[]'::jsonb,
  note          text,
  created_at    timestamptz not null default now()
);

-- ── 10) السجل غير القابل للتعديل (المادة 7.2) ──────────────────────────
create table if not exists journal_records (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid references desk_runs(id) on delete set null,
  sequence      bigint not null,
  record_code   text not null,                    -- JRN-XXXXXXXX
  record_hash   text not null,
  previous_hash text not null,
  payload       jsonb not null,
  created_at    timestamptz not null default now(),
  unique (sequence)
);

-- السجل يُلحق فقط: نمنع التعديل والحذف على مستوى قاعدة البيانات
create or replace function journal_immutable() returns trigger as $$
begin
  raise exception 'السجل غير قابل للتعديل — المادة 7.2 من الدستور';
end $$ language plpgsql;

drop trigger if exists journal_no_update on journal_records;
create trigger journal_no_update before update or delete on journal_records
  for each row execute function journal_immutable();

-- ── 11) المراجعات البعدية (المادة 7.3) ─────────────────────────────────
create table if not exists post_mortems (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  decision_code text not null,
  outcome       text not null check (outcome in ('correct','incorrect','flat','unknown')),
  agent_scores  jsonb not null default '[]'::jsonb,
  lesson        text
);

-- ── 12) أوزان الوكلاء (المادة 7.4) ─────────────────────────────────────
create table if not exists agent_weights (
  agent_id      text primary key,
  weight        numeric not null default 1.0,
  samples       int not null default 0,
  hit_rate      numeric,
  updated_at    timestamptz not null default now()
);

-- ── عروض مساعدة للوحة المعاينة ─────────────────────────────────────────
create or replace view v_run_summary as
select
  r.id                as run_id,
  r.created_at,
  r.asset,
  r.data_source,
  r.capital_usd,
  d.action,
  d.confidence,
  d.size_usd,
  d.abstention_kind,
  rv.risk_level,
  rv.veto             as risk_veto,
  rv.position_size_usd as approved_size,
  c.compliant,
  c.blocked           as compliance_blocked,
  pda.valid           as decision_valid,
  (select count(*) from agent_opinions o where o.run_id = r.id)              as opinions,
  (select count(*) from agent_opinions o where o.run_id = r.id and o.abstain) as abstentions,
  (select count(*) from agent_opinions o where o.run_id = r.id and o.direction <> 'neutral' and not o.abstain) as directional
from desk_runs r
left join decisions d on d.run_id = r.id
left join risk_verdicts rv on rv.run_id = r.id
left join compliance_reports c on c.run_id = r.id
left join post_decision_audits pda on pda.run_id = r.id;

create or replace view v_agent_accuracy as
select
  o.agent_id,
  o.agent_name,
  count(*) filter (where not o.abstain)                        as directional_calls,
  count(*) filter (where o.abstain)                            as abstentions,
  round(avg(o.confidence) filter (where not o.abstain), 2)      as avg_confidence,
  round(avg(o.best_tier), 2)                                   as avg_tier
from agent_opinions o
group by o.agent_id, o.agent_name
order by o.agent_id;

-- ── أمان الصفوف (RLS) ──────────────────────────────────────────────────
-- القراءة العامة مسموحة (لوحة معاينة)، والكتابة لـ service_role فقط
-- (service_role يتجاوز RLS بطبيعته).
do $$
declare t text;
begin
  foreach t in array array[
    'snapshots','desk_runs','agent_opinions','evidence_items','risk_verdicts',
    'decisions','execution_plans','compliance_reports','post_decision_audits',
    'journal_records','post_mortems','agent_weights'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I on %I', t || '_public_read', t);
    execute format(
      'create policy %I on %I for select to anon, authenticated using (true)',
      t || '_public_read', t
    );
  end loop;
end $$;

-- ── تم ────────────────────────────────────────────────────────────────
comment on table journal_records is
  'سجل الديسك — يُلحق فقط. trigger يمنع UPDATE/DELETE (CONSTITUTION.md المادة 7.2).';
comment on table decisions is
  'القرارات النهائية — تحليل فقط، ولا تنفيذ حقيقي (CONSTITUTION.md المادة 0.2).';
