"""Merchant Commerce Metrics and Dashboard Funnel Projections.

Derives live operational KPIs strictly from authoritative events and database records:
- Separates Issued GMV from Settled GMV (issuing a link NEVER increases settled GMV);
- Tracks in-envelope stock recoveries vs drift refusals;
- Surfaces UNKNOWN timeouts in Needs Attention;
- Attaches explicit evidence mode to every metric;
- Provides stable seeded demo history when database is uninitialized.
"""
from __future__ import annotations

import time
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from .config import get_settings
from .merchant import DEFAULT_MERCHANT_ID
from . import store


class FunnelStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    count: int
    conversion_rate: float


class NeedsAttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    item_type: str  # "unknown_outcome" | "policy_delta_blocked" | "stale_attempt"
    attempt_id: str
    severity: str  # "high" | "medium" | "low"
    title: str
    detail: str
    action_required: str
    created_at: float


class AgentOrderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    purchase_attempt_id: str
    envelope_id: str | None
    merchant_id: str
    buyer_agent_id: str
    shopper_session_id: str
    status: str
    outcome: str
    amount_paise: int
    recovery_applied: bool
    payment_link: str | None
    grant_id: str | None
    receipt_id: str | None
    code: str | None
    created_at: float
    updated_at: float


class ComprehensiveMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    evidence_mode: str
    store_readiness: str

    # Core 4 KPIs
    agent_gmv_issued_paise: int
    settled_agent_gmv_paise: int
    agent_orders_count: int
    orders_recovered_count: int
    unsafe_attempts_blocked_count: int
    unknown_attempts_count: int
    unknown_exposure_paise: int

    # Funnel
    funnel: list[FunnelStep]

    # Attention & Recent Orders
    needs_attention: list[NeedsAttentionItem]
    recent_orders: list[AgentOrderSummary]
    generated_at: float


def record_agent_order(
    purchase_attempt_id: str,
    merchant_id: str,
    buyer_agent_id: str,
    shopper_session_id: str,
    status: str,
    outcome: str,
    amount_paise: int,
    envelope_id: str | None = None,
    recovery_applied: bool = False,
    payment_link: str | None = None,
    grant_id: str | None = None,
    receipt_id: str | None = None,
    code: str | None = None,
    order_id: str | None = None,
) -> str:
    """Record or update an agent order in the authoritative agent_orders table."""
    oid = order_id or f"ord_{uuid.uuid4().hex[:12]}"
    now = time.time()

    with store._conn() as cx:
        cx.execute(
            """INSERT INTO agent_orders (
                   order_id, purchase_attempt_id, envelope_id, merchant_id,
                   buyer_agent_id, shopper_session_id, status, outcome,
                   amount_paise, recovery_applied, payment_link, grant_id,
                   receipt_id, code, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(purchase_attempt_id) DO UPDATE SET
                   status=excluded.status,
                   outcome=excluded.outcome,
                   amount_paise=excluded.amount_paise,
                   recovery_applied=excluded.recovery_applied,
                   payment_link=excluded.payment_link,
                   grant_id=excluded.grant_id,
                   receipt_id=excluded.receipt_id,
                   code=excluded.code,
                   updated_at=excluded.updated_at""",
            (
                oid,
                purchase_attempt_id,
                envelope_id,
                merchant_id,
                buyer_agent_id,
                shopper_session_id,
                status,
                outcome,
                amount_paise,
                1 if recovery_applied else 0,
                payment_link,
                grant_id,
                receipt_id,
                code,
                now,
                now,
            ),
        )
    return oid


def seed_stable_demo_orders(merchant_id: str = DEFAULT_MERCHANT_ID) -> None:
    """Seed stable historical agent orders if table is empty."""
    with store._conn() as cx:
        count = cx.execute(
            "SELECT COUNT(*) c FROM agent_orders WHERE merchant_id=?", (merchant_id,)
        ).fetchone()["c"]
        if count > 0:
            return

        now = time.time()
        seeds = [
            (
                "ord_demo_hist_01",
                "att_seed_01",
                "env_seed_01",
                merchant_id,
                "buyer_replay",
                "sess_seed_01",
                "issued",
                "ACTION_ISSUED",
                34800,
                0,
                "https://rzp.io/i/seed01a",
                "act_seed_01",
                "act_seed_01",
                "ALLOW_ENVELOPE",
                now - 7200,
                now - 7200,
            ),
            (
                "ord_demo_hist_02",
                "att_seed_02",
                "env_seed_02",
                merchant_id,
                "buyer_gemini_flash",
                "sess_seed_02",
                "recovered",
                "RECOVERED_INSIDE_ENVELOPE",
                43800,
                1,
                "https://rzp.io/i/seed02b",
                "act_seed_02",
                "act_seed_02",
                "ALLOW_ENVELOPE",
                now - 5400,
                now - 5400,
            ),
            (
                "ord_demo_hist_03",
                "att_seed_03",
                "env_seed_03",
                merchant_id,
                "buyer_replay",
                "sess_seed_03",
                "issued",
                "ACTION_ISSUED",
                89900,
                0,
                "https://rzp.io/i/seed03c",
                "act_seed_03",
                "act_seed_03",
                "ALLOW_ENVELOPE",
                now - 3600,
                now - 3600,
            ),
            (
                "ord_demo_hist_04",
                "att_seed_04",
                "env_seed_04",
                merchant_id,
                "buyer_replay",
                "sess_seed_04",
                "blocked",
                "POLICY_DELTA_REQUIRED",
                50000,
                0,
                None,
                None,
                None,
                "BLOCK_ENVELOPE_MISMATCH",
                now - 1800,
                now - 1800,
            ),
            (
                "ord_demo_hist_05",
                "att_seed_05",
                "env_seed_05",
                merchant_id,
                "buyer_replay",
                "sess_seed_05",
                "unknown",
                "UNKNOWN",
                41700,
                0,
                None,
                "act_seed_05",
                "act_seed_05",
                "ALLOW_BUT_PROVIDER_OUTCOME_UNKNOWN",
                now - 600,
                now - 600,
            ),
        ]
        cx.executemany(
            """INSERT OR IGNORE INTO agent_orders (
                   order_id, purchase_attempt_id, envelope_id, merchant_id,
                   buyer_agent_id, shopper_session_id, status, outcome,
                   amount_paise, recovery_applied, payment_link, grant_id,
                   receipt_id, code, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            seeds,
        )


def get_agent_orders(
    merchant_id: str = DEFAULT_MERCHANT_ID,
    limit: int = 50,
    status_filter: str | None = None,
) -> list[AgentOrderSummary]:
    """Fetch recent agent orders with optional status filtering."""
    seed_stable_demo_orders(merchant_id)

    query = "SELECT * FROM agent_orders WHERE merchant_id = ?"
    params: list[Any] = [merchant_id]

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with store._conn() as cx:
        rows = cx.execute(query, params).fetchall()

    orders: list[AgentOrderSummary] = []
    for r in rows:
        orders.append(
            AgentOrderSummary(
                order_id=r["order_id"],
                purchase_attempt_id=r["purchase_attempt_id"],
                envelope_id=r["envelope_id"],
                merchant_id=r["merchant_id"],
                buyer_agent_id=r["buyer_agent_id"],
                shopper_session_id=r["shopper_session_id"],
                status=r["status"],
                outcome=r["outcome"],
                amount_paise=r["amount_paise"],
                recovery_applied=bool(r["recovery_applied"]),
                payment_link=r["payment_link"],
                grant_id=r["grant_id"],
                receipt_id=r["receipt_id"],
                code=r["code"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
        )
    return orders


def get_comprehensive_metrics(
    merchant_id: str = DEFAULT_MERCHANT_ID,
) -> ComprehensiveMetricsResponse:
    """Calculate full merchant dashboard and funnel metrics from authoritative database rows."""
    seed_stable_demo_orders(merchant_id)
    settings = get_settings()
    ev_mode = "simulated" if settings.demo_mode else "razorpay_test"

    with store._conn() as cx:
        # Sum issued GMV (all orders with links issued or recovered)
        issued_gmv_row = cx.execute(
            """SELECT COALESCE(SUM(amount_paise), 0) s FROM agent_orders
               WHERE merchant_id=? AND status IN ('issued', 'recovered', 'settled')""",
            (merchant_id,),
        ).fetchone()
        issued_gmv = int(issued_gmv_row["s"])

        # Settled GMV (strictly separated from issued links)
        settled_gmv_row = cx.execute(
            """SELECT COALESCE(SUM(amount_paise), 0) s FROM agent_orders
               WHERE merchant_id=? AND status='settled'""",
            (merchant_id,),
        ).fetchone()
        settled_gmv = int(settled_gmv_row["s"])

        # Order counts
        orders_count = cx.execute(
            """SELECT COUNT(*) c FROM agent_orders
               WHERE merchant_id=? AND status IN ('issued', 'recovered', 'settled')""",
            (merchant_id,),
        ).fetchone()["c"]

        recovered_count = cx.execute(
            "SELECT COUNT(*) c FROM agent_orders WHERE merchant_id=? AND recovery_applied=1",
            (merchant_id,),
        ).fetchone()["c"]

        blocked_count = cx.execute(
            "SELECT COUNT(*) c FROM agent_orders WHERE merchant_id=? AND status='blocked'",
            (merchant_id,),
        ).fetchone()["c"]

        unknown_row = cx.execute(
            """SELECT COUNT(*) c, COALESCE(SUM(amount_paise), 0) s FROM agent_orders
               WHERE merchant_id=? AND status='unknown'""",
            (merchant_id,),
        ).fetchone()
        unknown_count = int(unknown_row["c"])
        unknown_exposure = int(unknown_row["s"])

        # Funnel counts
        intents_count = cx.execute(
            "SELECT COUNT(*) c FROM purchase_envelopes WHERE merchant_id=?",
            (merchant_id,),
        ).fetchone()["c"]
        intents_count = max(intents_count, orders_count + blocked_count + unknown_count)

        activated_count = cx.execute(
            "SELECT COUNT(*) c FROM purchase_envelopes WHERE merchant_id=? AND status IN ('active', 'consumed')",
            (merchant_id,),
        ).fetchone()["c"]
        activated_count = max(activated_count, orders_count + unknown_count)

        total_attempts = orders_count + blocked_count + unknown_count

    # Funnel computation
    funnel = [
        FunnelStep(stage="Intent Drafted", count=intents_count, conversion_rate=1.0),
        FunnelStep(
            stage="Envelope Approved",
            count=activated_count,
            conversion_rate=round(activated_count / intents_count, 3) if intents_count else 1.0,
        ),
        FunnelStep(
            stage="Attempt Submitted",
            count=total_attempts,
            conversion_rate=round(total_attempts / activated_count, 3) if activated_count else 1.0,
        ),
        FunnelStep(
            stage="Payment Link Issued",
            count=orders_count,
            conversion_rate=round(orders_count / total_attempts, 3) if total_attempts else 1.0,
        ),
        FunnelStep(
            stage="Settled Payment",
            count=0 if settled_gmv == 0 else 1,
            conversion_rate=round(1.0 if settled_gmv > 0 else 0.0, 3),
        ),
    ]

    # Needs Attention list
    needs_attention: list[NeedsAttentionItem] = []
    recent_orders = get_agent_orders(merchant_id, limit=10)

    for order in recent_orders:
        if order.status == "unknown":
            needs_attention.append(
                NeedsAttentionItem(
                    item_id=f"attn_{order.order_id}",
                    item_type="unknown_outcome",
                    attempt_id=order.purchase_attempt_id,
                    severity="high",
                    title="Provider Timeout (Exposure Held)",
                    detail=f"Order {order.order_id} (Rs {order.amount_paise / 100:.2f}) timed out after dispatch. Funds reserved; blind retry blocked.",
                    action_required="Reconcile with Razorpay test ledger",
                    created_at=order.created_at,
                )
            )
        elif order.status == "blocked":
            needs_attention.append(
                NeedsAttentionItem(
                    item_id=f"attn_{order.order_id}",
                    item_type="policy_delta_blocked",
                    attempt_id=order.purchase_attempt_id,
                    severity="medium",
                    title="Policy Delta Refusal (Drift Blocked)",
                    detail=f"Order {order.order_id} attempted unapproved merchant or address drift. Blocked before actuator.",
                    action_required="Shopper approval required for updated parameters",
                    created_at=order.created_at,
                )
            )

    return ComprehensiveMetricsResponse(
        merchant_id=merchant_id,
        evidence_mode=ev_mode,
        store_readiness="READY_FOR_AI_BUYERS",
        agent_gmv_issued_paise=issued_gmv,
        settled_agent_gmv_paise=settled_gmv,
        agent_orders_count=orders_count,
        orders_recovered_count=recovered_count,
        unsafe_attempts_blocked_count=blocked_count,
        unknown_attempts_count=unknown_count,
        unknown_exposure_paise=unknown_exposure,
        funnel=funnel,
        needs_attention=needs_attention,
        recent_orders=recent_orders,
        generated_at=time.time(),
    )
