"""
الواجهة الخلفية — دفع دورات الديسك إلى Supabase.

التصميم:
    • تعتمد على `urllib` فقط (لا مكتبات خارجية) — اتساقاً مع بقية المشروع.
    • تستخدم `service_role` **للكتابة فقط**، ولا تُصدَّر إلى أي واجهة عامة.
    • أي فشل شبكي **يُعلن** ولا يُسقط الدورة: الدفع عملية لاحقة للتحليل لا جزء منه.
    • السجل يُلحق مرة واحدة؛ قاعدة البيانات تمنع تعديله (trigger في `schema.sql`).

⚠️ أمان: `service_role` يتجاوز RLS. لا يجوز أن يصل إلى متصفح أبداً.
    الواجهة الأمامية تستخدم `SUPABASE_PUBLISHABLE_KEY` للقراءة فقط.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TIER_BY_KIND = {"onchain": 1, "market": 2, "derived": 3, "technical": 4,
                "sentiment": 5, "expert": 6, "inference": 7}


def load_dotenv(path: str | Path = ".env") -> dict[str, str]:
    """يقرأ `.env` بلا مكتبات خارجية، ولا يطبع أي قيمة."""
    p = Path(path)
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


class SupabaseBackend:
    """جالب/دافع دورات الديسك إلى Supabase عبر PostgREST."""

    def __init__(self, url: str | None = None, service_key: str | None = None,
                 timeout: float = 30.0, verbose: bool = True) -> None:
        dotenv = load_dotenv()
        self.url = (url or os.environ.get("SUPABASE_URL") or dotenv.get("SUPABASE_URL", "")).rstrip("/")
        self.key = (service_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                    or dotenv.get("SUPABASE_SERVICE_ROLE_KEY", ""))
        self.timeout = timeout
        self.verbose = verbose
        self.errors: list[str] = []
        if not self.url or not self.key:
            raise RuntimeError(
                "إعداد Supabase ناقص: اضبط SUPABASE_URL و SUPABASE_SERVICE_ROLE_KEY في .env"
            )

    # ------------------------------------------------------------------ #
    def _request(self, table: str, method: str, payload: Any = None,
                 params: str = "", prefer: str = "return=representation") -> Any:
        url = f"{self.url}/rest/v1/{table}" + (f"?{params}" if params else "")
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": prefer,
            "User-Agent": "avax-desk/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            self.errors.append(f"{table} {method}: HTTP {e.code} — {body}")
            raise RuntimeError(f"{table}: HTTP {e.code} — {body}") from e
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"{table} {method}: {type(e).__name__}: {e}")
            raise

    def insert_one(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        res = self._request(table, "POST", [row])
        return (res or [{}])[0]

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        return self._request(table, "POST", rows) or []

    def _safe(self, label: str, fn) -> Any:
        """
        تنفيذ خطوة دفع بمعزل: فشل خطوة **لا يُسقط بقية الدفع**.

        ثغرة مُصلَحة: كان تكرار تسلسل السجل يُسقط كل الدفع بعد أن تكون معظم
        الجداول قد أُدرجت — فيبقى الدفع جزئياً بلا إعلان واضح.
        """
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"{label}: {type(exc).__name__}: {str(exc)[:200]}")
            return None

    def _next_journal_sequence(self) -> int:
        """التسلسل التالي في سلسلة السجل العامة (لا يبدأ من 1 كل مرة)."""
        rows = self._request("journal_records", "GET",
                             params="select=sequence&order=sequence.desc&limit=1")
        if rows:
            return int(rows[0]["sequence"]) + 1
        return 1

    # ------------------------------------------------------------------ #
    def health(self) -> dict[str, Any]:
        """فحص اتصال + عدّاد كل جدول."""
        out: dict[str, Any] = {"url": self.url, "tables": {}, "ok": True}
        for t in ("desk_runs", "agent_opinions", "evidence_items", "decisions",
                  "journal_records", "risk_verdicts"):
            try:
                rows = self._request(t, "GET", params="select=id&limit=1000")
                out["tables"][t] = len(rows or [])
            except Exception as exc:  # noqa: BLE001
                out["tables"][t] = f"خطأ: {type(exc).__name__}"
                out["ok"] = False
        return out

    # ------------------------------------------------------------------ #
    def push_run(self, result: dict[str, Any]) -> dict[str, Any]:
        """
        يدفع دورة كاملة: اللقطة ← الدورة ← الآراء ← الأدلة ← المخاطر ←
        القرار ← التنفيذ ← الالتزام ← التدقيق البعدي ← السجل.

        يعيد معرّفات الصفوف المُدرَجة. أي فشل يُعلن في `errors` ولا يُسقط شيئاً.
        """
        ids: dict[str, Any] = {}

        # ── 1) اللقطة ───────────────────────────────────────────────────
        market = result.get("market") or {}
        run_meta = {
            "run_label": result.get("decision", {}).get("id"),
            "asset": result.get("asset", "AVAX"),
            "capital_usd": (result.get("proposal") or {}).get("capital_usd")
            or (result.get("risk") or {}).get("limits_checked", {}).get("capital_usd")
            or 1_000_000,
            "data_source": result.get("data_source", "unknown"),
            "live_verified": result.get("data_source") == "live",
            "constitution_sha256": (result.get("constitution") or {}).get("sha256"),
            "law_audit": result.get("law_audit"),
            "abstention_rate": (result.get("journal_summary") or {}).get("abstention_rate"),
            "meta": {"mode": result.get("mode"), "constitution": result.get("constitution")},
        }
        if market:
            snap_row = self.insert_one("snapshots", {
                "asset": market.get("asset", "AVAX"),
                "as_of": market.get("timestamp"),
                "source": market.get("source", "unknown"),
                "price": market.get("price") or market.get("closes", {}).get("last"),
                "missing_fields": market.get("missing_fields") or [],
                "payload": market,
                "consistency": market.get("meta"),
            })
            ids["snapshot_id"] = snap_row.get("id")
            run_meta["snapshot_id"] = ids["snapshot_id"]

        run = self.insert_one("desk_runs", run_meta)
        run_id = run["id"]
        ids["run_id"] = run_id

        # ── 2) آراء الوكلاء + الأدلة ────────────────────────────────────
        opinions = result.get("opinions") or {}
        op_rows: list[dict[str, Any]] = []
        ev_by_agent: dict[str, list[dict[str, Any]]] = {}
        for aid, op in opinions.items():
            op_rows.append({
                "run_id": run_id,
                "agent_id": str(op.get("agent_id", aid)),
                "agent_name": op.get("agent_name", ""),
                "layer": op.get("layer", "knowledge"),
                "authority": op.get("authority", "advisory"),
                "direction": op.get("direction", "neutral"),
                "confidence": float(op.get("confidence", 0.0)),
                "net_confidence": op.get("net_confidence"),
                "best_tier": op.get("best_tier"),
                "horizon": op.get("horizon"),
                "thesis": op.get("thesis"),
                "invalidation": op.get("invalidation"),
                "dissent": op.get("dissent"),
                "abstain": bool(op.get("abstain", False)),
                "abstain_reason": op.get("abstain_reason"),
                "metrics": op.get("metrics") or {},
                "notes": op.get("notes") or [],
            })
            for e in (op.get("evidence") or []):
                kind = e.get("kind", "inference")
                ev_by_agent.setdefault(str(op.get("agent_id", aid)), []).append({
                    "run_id": run_id,
                    "claim": e.get("claim", ""),
                    "source": e.get("source", ""),
                    "timestamp": e.get("timestamp"),
                    "kind": kind,
                    "tier": TIER_BY_KIND.get(kind, 7),
                    "strength": e.get("strength", "medium"),
                    "value": e.get("value"),
                })

        inserted_ops = self.insert_many("agent_opinions", op_rows)
        id_by_agent = {row["agent_id"]: row["id"] for row in inserted_ops}
        ids["opinions"] = len(inserted_ops)

        ev_rows: list[dict[str, Any]] = []
        for agent_id, items in ev_by_agent.items():
            oid = id_by_agent.get(agent_id)
            if not oid:
                continue
            for it in items:
                it["opinion_id"] = oid
                ev_rows.append(it)
        inserted_ev = self.insert_many("evidence_items", ev_rows)
        ids["evidence"] = len(inserted_ev)

        # ── 3) المخاطر ──────────────────────────────────────────────────
        risk = result.get("risk")
        if risk:
            row = {k: risk.get(k) for k in (
                "approved", "veto", "risk_level", "position_size_usd",
                "computed_size_usd", "stop_loss_pct", "risk_per_trade_pct",
                "veto_reasons", "limits_checked", "notes")}
            row["run_id"] = run_id
            self._safe("risk_verdicts", lambda: self.insert_one("risk_verdicts", row))

        # ── 4) القرار ───────────────────────────────────────────────────
        dec = result.get("decision") or {}
        if dec:
            self._safe("decisions", lambda: self.insert_one("decisions", {
                "run_id": run_id,
                "decision_code": dec.get("id", "DEC-UNKNOWN"),
                "asset": result.get("asset", "AVAX"),
                "action": dec.get("action", "ABSTAIN"),
                "confidence": float(dec.get("confidence", 0.0)),
                "horizon": dec.get("horizon"),
                "rationale": dec.get("rationale"),
                "invalidation": dec.get("invalidation"),
                "strongest_dissent": dec.get("strongest_dissent"),
                "dissent_source": dec.get("dissent_source"),
                "abstention_kind": dec.get("abstention_kind"),
                "blocks": dec.get("blocks") or [],
                "groupthink_flag": bool(dec.get("groupthink_flag", False)),
                "supporting_agents": dec.get("supporting_agents") or [],
                "opposing_agents": dec.get("opposing_agents") or [],
                "abstaining_agents": dec.get("abstaining_agents") or [],
                "entry_zone": dec.get("entry_zone"),
                "stop_price": dec.get("stop"),
                "targets": dec.get("targets"),
                "size_usd": float(dec.get("size_usd", 0.0)),
                "evidence_summary": result.get("evidence_summary"),
            }))

        # ── 5) التنفيذ ──────────────────────────────────────────────────
        plan = result.get("execution_plan")
        if plan:
            self.insert_one("execution_plans", {
                "run_id": run_id,
                "method": plan.get("method"),
                "slices": plan.get("slices"),
                "participation_pct": plan.get("participation_pct"),
                "expected_slippage_bps": plan.get("expected_slippage_bps"),
                "expected_cost_usd": plan.get("expected_cost_usd"),
                "schedule": plan.get("schedule"),
                "venue_notes": plan.get("venue_notes") or [],
                "disclaimer": plan.get("disclaimer"),
            })

        # ── 6) الالتزام ─────────────────────────────────────────────────
        comp = result.get("compliance")
        if comp:
            self.insert_one("compliance_reports", {
                "run_id": run_id,
                "compliant": bool(comp.get("compliant", False)),
                "blocked": bool(comp.get("blocked", False)),
                "checked_agents": comp.get("checked_agents"),
                "violations": comp.get("violations") or [],
                "notes": comp.get("notes") or [],
            })

        # ── 7) التدقيق البعدي ───────────────────────────────────────────
        post = result.get("post_decision_audit")
        if post:
            self.insert_one("post_decision_audits", {
                "run_id": run_id,
                "valid": bool(post.get("valid", False)),
                "checks_run": post.get("checked"),
                "violations_found": post.get("violations_found"),
                "critical": post.get("critical"),
                "violations": post.get("violations") or [],
                "note": post.get("note"),
            })

        # ── 8) السجل (يُلحق مرة واحدة) ──────────────────────────────────
        law = result.get("law_audit") or {}
        seq = self._safe("journal_sequence", self._next_journal_sequence) or 1
        self._safe("journal_records", lambda: self.insert_one("journal_records", {
            "run_id": run_id,
            "sequence": seq,
            "record_code": dec.get("id", "JRN-UNKNOWN"),
            "record_hash": (result.get("constitution") or {}).get("sha256", "0" * 64),
            "previous_hash": "GENESIS",
            "payload": {"law_audit": law, "decision": dec, "risk": risk},
        }))
        ids["journal_sequence"] = seq

        ids["errors"] = self.errors
        if self.verbose:
            print(f"  ☁️  Supabase: دورة {ids['run_id'][:8]}… | "
                  f"{ids['opinions']} رأياً | {ids['evidence']} دليلاً | "
                  f"{len(self.errors)} خطأ")
        return ids
