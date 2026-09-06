"""SQLite persistence for policies, exact action grants, and event evidence."""
from __future__ import annotations
import json, sqlite3, time, uuid
from contextlib import contextmanager
from typing import Optional

from .authorization import (
    action_args_hash,
    canonical_json,
    cart_hash as compute_cart_hash,
    policy_hash,
    policy_payload,
)
from .config import get_settings
from .envelope import compute_envelope_hash
from .models import (
    ActionContext,
    ActionGrant,
    ActionState,
    AuthorizationOutcome,
    AuthorizationRequest,
    DecisionCode,
    Mandate,
    MandateCreate,
    MandateDecision,
    MandateUpdate,
    EnvelopeStatus,
    PurchaseEnvelope,
    EnvelopeSlot,
    Reservation,
    Window,
    AuthorityCeiling,
    AuthorityView,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS mandates (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    label TEXT NOT NULL,
    cap_paise INTEGER NOT NULL,
    window TEXT NOT NULL,
    per_txn_cap_paise INTEGER,
    allowed_categories TEXT NOT NULL DEFAULT '[]',
    blocked_categories TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mandate_agent ON mandates(user_id, agent_id, active);

CREATE TABLE IF NOT EXISTS policy_revisions (
    mandate_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    policy_hash TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (mandate_id, version)
);

CREATE TABLE IF NOT EXISTS purchase_envelopes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    label TEXT NOT NULL,
    goal TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    max_total_paise INTEGER NOT NULL,
    fulfillment_profile_id TEXT NOT NULL,
    delivery_deadline REAL NOT NULL,
    expires_at REAL NOT NULL,
    slots_json TEXT NOT NULL,
    blocked_categories TEXT NOT NULL DEFAULT '[]',
    max_purchases INTEGER NOT NULL DEFAULT 1,
    action_name TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    envelope_hash TEXT NOT NULL,
    mandate_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_envelope_user
    ON purchase_envelopes(user_id, created_at DESC);

-- One row is both the headroom hold and the opaque authorization receipt.
-- Keeping the lifecycle in one record prevents a receipt and reservation from
-- disagreeing after a crash or concurrent retry.
CREATE TABLE IF NOT EXISTS spend_ledger (
    id TEXT PRIMARY KEY,
    mandate_id TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'committed',
    idempotency_key TEXT,
    expires_at REAL,
    razorpay_ref TEXT,
    user_id TEXT,
    agent_id TEXT,
    session_id TEXT,
    merchant_id TEXT,
    mandate_version INTEGER,
    policy_hash TEXT,
    action_name TEXT,
    action_schema_hash TEXT,
    args_json TEXT,
    args_hash TEXT,
    cart_hash TEXT,
    currency TEXT,
    purchase_attempt_id TEXT,
    envelope_id TEXT,
    envelope_version INTEGER,
    envelope_hash TEXT,
    quote_hash TEXT,
    result_json TEXT,
    error TEXT,
    dispatch_token TEXT,
    created_at REAL NOT NULL,
    updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_ledger_mandate ON spend_ledger(mandate_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_idem
    ON spend_ledger(mandate_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL
      AND status NOT IN ('released','cancelled','definitive_failure');
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    mandate_id TEXT,
    mandate_version INTEGER,
    event TEXT NOT NULL,
    code TEXT,
    cart_total_paise INTEGER,
    cap_paise INTEGER,
    payload TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id, created_at);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
-- INSERT OR REPLACE overwrites a row by deleting it and inserting again.
-- Whether that implicit DELETE fires the guard above depends on the
-- recursive_triggers pragma AND on the SQLite build, so relying on it makes
-- the append-only claim environment-dependent. This guard does not: a REPLACE
-- still has to INSERT, and an INSERT onto an existing id is rejected here on
-- every version.
CREATE TRIGGER IF NOT EXISTS audit_log_no_overwrite
BEFORE INSERT ON audit_log
WHEN EXISTS (SELECT 1 FROM audit_log WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TABLE IF NOT EXISTS authority_ceilings (
    user_id TEXT PRIMARY KEY,
    window TEXT NOT NULL,
    ceiling_paise INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON spend_ledger(user_id, created_at);
"""

WINDOW_SECONDS = {
    Window.PER_TXN: 0,
    Window.DAILY: 86_400,
    Window.WEEKLY: 7 * 86_400,
    Window.MONTHLY: 30 * 86_400,
}


def _configure(cx: sqlite3.Connection) -> sqlite3.Connection:
    """Per-connection pragmas.

    recursive_triggers is a CONNECTION-level setting and SQLite leaves it OFF.
    With it off, the implicit DELETE inside an INSERT OR REPLACE conflict does
    not fire the audit table's BEFORE DELETE guard, so an audit row could be
    rewritten in place with the row count unchanged and no error. It therefore
    has to be set on every connection that touches the database, not once at
    startup.
    """
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA recursive_triggers=ON")
    return cx


@contextmanager
def _conn():
    cx = _configure(sqlite3.connect(get_settings().db_path))
    try:
        yield cx
        cx.commit()
    finally:
        cx.close()


RESERVATION_TTL_SECONDS = 180


def init_db() -> None:
    with _conn() as cx:
        # WAL lets readers run while one writer holds the lock, which is what
        # makes BEGIN IMMEDIATE cheap enough to take on every reservation.
        cx.execute("PRAGMA journal_mode=WAL")
        cx.executescript(SCHEMA)
        _migrate(cx)


def _migrate(cx: sqlite3.Connection) -> None:
    """Additive migration for databases created before exact action grants."""
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(spend_ledger)")}
    for col, ddl in (
        ("status", "ALTER TABLE spend_ledger ADD COLUMN status TEXT NOT NULL DEFAULT 'committed'"),
        ("idempotency_key", "ALTER TABLE spend_ledger ADD COLUMN idempotency_key TEXT"),
        ("expires_at", "ALTER TABLE spend_ledger ADD COLUMN expires_at REAL"),
        ("user_id", "ALTER TABLE spend_ledger ADD COLUMN user_id TEXT"),
        ("agent_id", "ALTER TABLE spend_ledger ADD COLUMN agent_id TEXT"),
        ("session_id", "ALTER TABLE spend_ledger ADD COLUMN session_id TEXT"),
        ("merchant_id", "ALTER TABLE spend_ledger ADD COLUMN merchant_id TEXT"),
        ("mandate_version", "ALTER TABLE spend_ledger ADD COLUMN mandate_version INTEGER"),
        ("policy_hash", "ALTER TABLE spend_ledger ADD COLUMN policy_hash TEXT"),
        ("action_name", "ALTER TABLE spend_ledger ADD COLUMN action_name TEXT"),
        ("action_schema_hash", "ALTER TABLE spend_ledger ADD COLUMN action_schema_hash TEXT"),
        ("args_json", "ALTER TABLE spend_ledger ADD COLUMN args_json TEXT"),
        ("args_hash", "ALTER TABLE spend_ledger ADD COLUMN args_hash TEXT"),
        ("cart_hash", "ALTER TABLE spend_ledger ADD COLUMN cart_hash TEXT"),
        ("currency", "ALTER TABLE spend_ledger ADD COLUMN currency TEXT"),
        ("purchase_attempt_id", "ALTER TABLE spend_ledger ADD COLUMN purchase_attempt_id TEXT"),
        ("envelope_id", "ALTER TABLE spend_ledger ADD COLUMN envelope_id TEXT"),
        ("envelope_version", "ALTER TABLE spend_ledger ADD COLUMN envelope_version INTEGER"),
        ("envelope_hash", "ALTER TABLE spend_ledger ADD COLUMN envelope_hash TEXT"),
        ("quote_hash", "ALTER TABLE spend_ledger ADD COLUMN quote_hash TEXT"),
        ("result_json", "ALTER TABLE spend_ledger ADD COLUMN result_json TEXT"),
        ("error", "ALTER TABLE spend_ledger ADD COLUMN error TEXT"),
        ("dispatch_token", "ALTER TABLE spend_ledger ADD COLUMN dispatch_token TEXT"),
        ("updated_at", "ALTER TABLE spend_ledger ADD COLUMN updated_at REAL"),
    ):
        if col not in cols:
            cx.execute(ddl)
    cx.execute("UPDATE spend_ledger SET updated_at=created_at WHERE updated_at IS NULL")
    cx.execute("DROP INDEX IF EXISTS idx_ledger_idem")
    cx.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_idem
           ON spend_ledger(mandate_id, idempotency_key)
           WHERE idempotency_key IS NOT NULL
             AND status NOT IN ('released','cancelled','definitive_failure')"""
    )
    cx.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_state_expiry "
        "ON spend_ledger(status, expires_at)"
    )
    cx.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_envelope_live
           ON spend_ledger(envelope_id)
           WHERE envelope_id IS NOT NULL
             AND status NOT IN ('released','cancelled','definitive_failure')"""
    )
    for row in cx.execute("SELECT * FROM mandates").fetchall():
        mandate = _row_to_mandate(row)
        _insert_policy_revision(cx, mandate)
    now = time.time()
    cx.execute(
        """INSERT OR IGNORE INTO authority_ceilings (
               user_id, window, ceiling_paise, version, created_at, updated_at
           ) VALUES ('user_demo', 'weekly', 200000, 1, ?, ?)""",
        (now, now),
    )


def _row_to_mandate(r: sqlite3.Row) -> Mandate:
    return Mandate(
        id=r["id"], user_id=r["user_id"], agent_id=r["agent_id"], label=r["label"],
        cap_paise=r["cap_paise"], window=Window(r["window"]),
        per_txn_cap_paise=r["per_txn_cap_paise"],
        allowed_categories=json.loads(r["allowed_categories"]),
        blocked_categories=json.loads(r["blocked_categories"]),
        active=bool(r["active"]), version=r["version"],
        created_at=r["created_at"], updated_at=r["updated_at"],
    )


def _row_to_envelope(row: sqlite3.Row) -> PurchaseEnvelope:
    return PurchaseEnvelope(
        id=row["id"],
        user_id=row["user_id"],
        agent_id=row["agent_id"],
        label=row["label"],
        goal=row["goal"],
        merchant_id=row["merchant_id"],
        currency=row["currency"],
        max_total_paise=row["max_total_paise"],
        fulfillment_profile_id=row["fulfillment_profile_id"],
        delivery_deadline=row["delivery_deadline"],
        expires_at=row["expires_at"],
        slots=[EnvelopeSlot.model_validate(item) for item in json.loads(row["slots_json"])],
        blocked_categories=json.loads(row["blocked_categories"]),
        max_purchases=row["max_purchases"],
        action_name=row["action_name"],
        status=EnvelopeStatus(row["status"]),
        version=row["version"],
        envelope_hash=row["envelope_hash"],
        mandate_id=row["mandate_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _insert_policy_revision(cx: sqlite3.Connection, mandate: Mandate) -> None:
    cx.execute(
        """INSERT OR IGNORE INTO policy_revisions
           (mandate_id,version,policy_hash,policy_json,created_at)
           VALUES (?,?,?,?,?)""",
        (
            mandate.id,
            mandate.version,
            policy_hash(mandate),
            canonical_json(policy_payload(mandate)),
            mandate.updated_at,
        ),
    )


def save_envelope_draft(envelope: PurchaseEnvelope) -> PurchaseEnvelope:
    if envelope.status is not EnvelopeStatus.DRAFT:
        raise ValueError("Only a draft envelope can be created")
    if envelope.envelope_hash != compute_envelope_hash(envelope):
        raise ValueError("Envelope hash does not match its canonical fields")
    with _conn() as cx:
        cx.execute(
            """INSERT INTO purchase_envelopes (
                   id,user_id,agent_id,label,goal,merchant_id,currency,
                   max_total_paise,fulfillment_profile_id,delivery_deadline,
                   expires_at,slots_json,blocked_categories,max_purchases,
                   action_name,status,version,envelope_hash,mandate_id,
                   created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                envelope.id,
                envelope.user_id,
                envelope.agent_id,
                envelope.label,
                envelope.goal,
                envelope.merchant_id,
                envelope.currency,
                envelope.max_total_paise,
                envelope.fulfillment_profile_id,
                envelope.delivery_deadline,
                envelope.expires_at,
                canonical_json([slot.model_dump(mode="json") for slot in envelope.slots]),
                canonical_json(envelope.blocked_categories),
                envelope.max_purchases,
                envelope.action_name,
                envelope.status.value,
                envelope.version,
                envelope.envelope_hash,
                envelope.mandate_id,
                envelope.created_at,
                envelope.updated_at,
            ),
        )
        _insert_audit_row(
            cx,
            event="ENVELOPE_DRAFTED",
            session_id=None,
            code="DRAFT",
            cart_total_paise=0,
            cap_paise=envelope.max_total_paise,
            payload={
                "envelope_id": envelope.id,
                "envelope_hash": envelope.envelope_hash,
                "goal": envelope.goal,
            },
        )
    return get_envelope(envelope.id)  # type: ignore[return-value]


def get_envelope(envelope_id: str) -> PurchaseEnvelope | None:
    with _conn() as cx:
        row = cx.execute(
            "SELECT * FROM purchase_envelopes WHERE id=?", (envelope_id,)
        ).fetchone()
    return _row_to_envelope(row) if row else None


def list_envelopes(user_id: str = "user_demo") -> list[PurchaseEnvelope]:
    with _conn() as cx:
        rows = cx.execute(
            "SELECT * FROM purchase_envelopes WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [_row_to_envelope(row) for row in rows]


def activate_envelope(envelope_id: str, expected_hash: str) -> PurchaseEnvelope:
    """Atomically activate the envelope and its underlying spend policy."""
    now = time.time()
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute(
            "SELECT * FROM purchase_envelopes WHERE id=?", (envelope_id,)
        ).fetchone()
        if not row:
            raise LookupError("UNKNOWN_ENVELOPE")
        current = _row_to_envelope(row)
        if current.status is not EnvelopeStatus.DRAFT:
            raise ValueError("ENVELOPE_NOT_DRAFT")
        if current.expires_at <= now:
            raise ValueError("ENVELOPE_EXPIRED")
        if current.envelope_hash != expected_hash:
            raise ValueError("ENVELOPE_HASH_CHANGED")
        if current.envelope_hash != compute_envelope_hash(current):
            raise ValueError("ENVELOPE_STORAGE_INTEGRITY_FAILURE")

        mandate_id = f"mnd_{uuid.uuid4().hex[:12]}"
        cx.execute(
            "UPDATE mandates SET active=0,version=version+1,updated_at=? "
            "WHERE user_id=? AND agent_id=? AND active=1",
            (now, current.user_id, current.agent_id),
        )
        cx.execute(
            """INSERT INTO mandates (
                   id,user_id,agent_id,label,cap_paise,window,per_txn_cap_paise,
                   allowed_categories,blocked_categories,active,version,created_at,updated_at
               ) VALUES (?,?,?,?,?,'per_transaction',?,'[]',?,1,1,?,?)""",
            (
                mandate_id,
                current.user_id,
                current.agent_id,
                "Purchase Envelope spend fence",
                current.max_total_paise,
                current.max_total_paise,
                canonical_json(current.blocked_categories),
                now,
                now,
            ),
        )
        mandate_row = cx.execute(
            "SELECT * FROM mandates WHERE id=?", (mandate_id,)
        ).fetchone()
        _insert_policy_revision(cx, _row_to_mandate(mandate_row))

        activated = current.model_copy(
            update={
                "status": EnvelopeStatus.ACTIVE,
                "version": current.version + 1,
                "mandate_id": mandate_id,
                "updated_at": now,
                "envelope_hash": "",
            }
        )
        activated = activated.model_copy(
            update={"envelope_hash": compute_envelope_hash(activated)}
        )
        cx.execute(
            """UPDATE purchase_envelopes
               SET status=?,version=?,mandate_id=?,envelope_hash=?,updated_at=?
               WHERE id=? AND version=? AND status='draft'""",
            (
                activated.status.value,
                activated.version,
                mandate_id,
                activated.envelope_hash,
                now,
                envelope_id,
                current.version,
            ),
        )
        _insert_audit_row(
            cx,
            event="ENVELOPE_ACTIVATED",
            session_id=None,
            mandate_id=mandate_id,
            mandate_version=1,
            code="ACTIVE",
            cap_paise=activated.max_total_paise,
            payload={
                "envelope_id": activated.id,
                "envelope_version": activated.version,
                "envelope_hash": activated.envelope_hash,
            },
        )
        return activated


def revoke_envelope(envelope_id: str, expected_version: int) -> PurchaseEnvelope:
    now = time.time()
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute(
            "SELECT * FROM purchase_envelopes WHERE id=?", (envelope_id,)
        ).fetchone()
        if not row:
            raise LookupError("UNKNOWN_ENVELOPE")
        current = _row_to_envelope(row)
        if current.version != expected_version:
            raise ValueError("ENVELOPE_VERSION_CHANGED")
        if current.status is not EnvelopeStatus.ACTIVE:
            raise ValueError("ENVELOPE_NOT_ACTIVE")

        revoked = current.model_copy(
            update={
                "status": EnvelopeStatus.REVOKED,
                "version": current.version + 1,
                "updated_at": now,
                "envelope_hash": "",
            }
        )
        revoked = revoked.model_copy(
            update={"envelope_hash": compute_envelope_hash(revoked)}
        )
        cx.execute(
            """UPDATE purchase_envelopes
               SET status='revoked',version=?,envelope_hash=?,updated_at=?
               WHERE id=? AND version=? AND status='active'""",
            (
                revoked.version,
                revoked.envelope_hash,
                now,
                envelope_id,
                current.version,
            ),
        )
        if current.mandate_id:
            cx.execute(
                "UPDATE mandates SET active=0,version=version+1,updated_at=? WHERE id=?",
                (now, current.mandate_id),
            )
            mandate_row = cx.execute(
                "SELECT * FROM mandates WHERE id=?", (current.mandate_id,)
            ).fetchone()
            if mandate_row:
                _insert_policy_revision(cx, _row_to_mandate(mandate_row))
        _insert_audit_row(
            cx,
            event="ENVELOPE_REVOKED",
            mandate_id=current.mandate_id,
            mandate_version=None,
            code="REVOKED",
            cap_paise=current.max_total_paise,
            payload={"envelope_id": envelope_id, "version": revoked.version},
        )
        return revoked


def create_mandate(m: MandateCreate) -> Mandate:
    now = time.time()
    mid = f"mnd_{uuid.uuid4().hex[:12]}"
    with _conn() as cx:
        # One active mandate per (user, agent) — a new one supersedes the old.
        cx.execute(
            "UPDATE mandates SET active=0, updated_at=? WHERE user_id=? AND agent_id=? AND active=1",
            (now, m.user_id, m.agent_id),
        )
        cx.execute(
            """INSERT INTO mandates (id,user_id,agent_id,label,cap_paise,window,
               per_txn_cap_paise,allowed_categories,blocked_categories,active,version,
               created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,1,1,?,?)""",
            (mid, m.user_id, m.agent_id, m.label, m.cap_rupees * 100, m.window.value,
             # `is not None`, not truthiness: a per-transaction cap of 0 is the
             # most restrictive value a shopper can express. Treating it as
             # falsy stored NULL and removed the cap entirely — the exact
             # inversion of intent. update_mandate already got this right.
             (m.per_txn_cap_rupees * 100) if m.per_txn_cap_rupees is not None else None,
             json.dumps(m.allowed_categories), json.dumps(m.blocked_categories),
             now, now),
        )
        row = cx.execute("SELECT * FROM mandates WHERE id=?", (mid,)).fetchone()
        _insert_policy_revision(cx, _row_to_mandate(row))
    log_event(event="MANDATE_CREATED", mandate_id=mid, mandate_version=1,
              payload={"cap_paise": m.cap_rupees * 100, "window": m.window.value})
    return get_mandate(mid)  # type: ignore[return-value]


def get_mandate(mandate_id: str) -> Optional[Mandate]:
    with _conn() as cx:
        r = cx.execute("SELECT * FROM mandates WHERE id=?", (mandate_id,)).fetchone()
    return _row_to_mandate(r) if r else None


def get_active_mandate(user_id: str, agent_id: str) -> Optional[Mandate]:
    """Returns the mandate currently governing this agent.

    Prefers an ACTIVE mandate; if none is active it still returns the most
    recent one so the caller can distinguish "revoked" from "never existed".
    Collapsing those two into one answer would tell the shopper to create a
    mandate they already have, and would lose the revocation audit trail.
    """
    with _conn() as cx:
        r = cx.execute(
            "SELECT * FROM mandates WHERE user_id=? AND agent_id=? "
            "ORDER BY active DESC, created_at DESC, updated_at DESC LIMIT 1",
            (user_id, agent_id),
        ).fetchone()
    return _row_to_mandate(r) if r else None


def list_mandates(user_id: str) -> list[Mandate]:
    with _conn() as cx:
        rows = cx.execute(
            "SELECT * FROM mandates WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
        ).fetchall()
    return [_row_to_mandate(r) for r in rows]


def update_mandate(mandate_id: str, u: MandateUpdate) -> Optional[Mandate]:
    """Every edit bumps `version`. The agent re-reads the mandate on every turn,
    so the new limit binds on the very next prompt — that is Revocation Latency."""
    now = time.time()
    fields, vals = [], []
    if u.cap_rupees is not None:
        fields.append("cap_paise=?"); vals.append(u.cap_rupees * 100)
    if u.per_txn_cap_rupees is not None:
        fields.append("per_txn_cap_paise=?"); vals.append(u.per_txn_cap_rupees * 100)
    if u.active is not None:
        fields.append("active=?"); vals.append(1 if u.active else 0)
    if u.allowed_categories is not None:
        fields.append("allowed_categories=?"); vals.append(json.dumps(u.allowed_categories))
    if u.blocked_categories is not None:
        fields.append("blocked_categories=?"); vals.append(json.dumps(u.blocked_categories))
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute("SELECT * FROM mandates WHERE id=?", (mandate_id,)).fetchone()
        if not row:
            return None
        cur = _row_to_mandate(row)
        if not fields:
            return cur
        fields += ["version=version+1", "updated_at=?"]
        vals.extend((now, mandate_id))
        cx.execute(f"UPDATE mandates SET {', '.join(fields)} WHERE id=?", vals)
        updated = cx.execute("SELECT * FROM mandates WHERE id=?", (mandate_id,)).fetchone()
        m = _row_to_mandate(updated)
        _insert_policy_revision(cx, m)
    log_event(event="MANDATE_UPDATED", mandate_id=mandate_id,
              mandate_version=m.version,
              payload=u.model_dump(exclude_none=True))
    return m


_CONSUMED_SQL = """
SELECT COALESCE(SUM(amount_paise),0) AS s FROM spend_ledger
 WHERE mandate_id=?
   AND ((status IN ('committed','settled') AND created_at>=?)
        OR status IN ('action_issued','dispatching','unknown')
        OR (status IN ('reserved','authorized') AND COALESCE(expires_at,0) > ?))
"""


def spent_in_window(mandate_id: str, window: Window) -> int:
    """Headroom consumed by settled, issued, in-flight, or unknown actions.

    An ambiguous or issued action remains exposure. Only a never-dispatched
    authorization may expire and return headroom automatically.
    """
    if window == Window.PER_TXN:
        return 0
    now = time.time()
    since = now - WINDOW_SECONDS[window]
    with _conn() as cx:
        r = cx.execute(_CONSUMED_SQL, (mandate_id, since, now)).fetchone()
    return int(r["s"])


_USER_EXPOSURE_SQL = """
SELECT COALESCE(SUM(amount_paise),0) AS s FROM spend_ledger
 WHERE user_id=?
   AND ((status IN ('committed','settled') AND created_at>=?)
        OR status IN ('action_issued','dispatching','unknown')
        OR (status IN ('reserved','authorized') AND COALESCE(expires_at,0) > ?))
"""


def get_authority_ceiling(user_id: str = "user_demo") -> AuthorityCeiling | None:
    with _conn() as cx:
        row = cx.execute(
            "SELECT * FROM authority_ceilings WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            return None
        return AuthorityCeiling(
            user_id=row["user_id"],
            window=Window(row["window"]),
            ceiling_paise=int(row["ceiling_paise"]),
            version=int(row["version"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )


def set_authority_ceiling(
    user_id: str, ceiling_paise: int, window: Window = Window.WEEKLY
) -> None:
    now = time.time()
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        cx.execute(
            """INSERT INTO authority_ceilings (user_id, window, ceiling_paise, version, created_at, updated_at)
               VALUES (?, ?, ?, 1, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   ceiling_paise=excluded.ceiling_paise,
                   window=excluded.window,
                   version=version+1,
                   updated_at=excluded.updated_at""",
            (user_id, window.value, ceiling_paise, now, now),
        )


def get_authority_view(user_id: str = "user_demo") -> dict[str, Any]:
    now = time.time()
    with _conn() as cx:
        row = cx.execute(
            "SELECT * FROM authority_ceilings WHERE user_id=?", (user_id,)
        ).fetchone()
        window_str = row["window"] if row else "weekly"
        window = Window(window_str)
        ceiling_paise = int(row["ceiling_paise"]) if row else 200000
        since = now - WINDOW_SECONDS[window] if window != Window.PER_TXN else 0
        exposure = int(
            cx.execute(_USER_EXPOSURE_SQL, (user_id, since, now)).fetchone()["s"]
        )
        active_count = cx.execute(
            "SELECT COUNT(*) AS c FROM purchase_envelopes WHERE user_id=? AND status='active'",
            (user_id,),
        ).fetchone()["c"]
        headroom = max(0, ceiling_paise - exposure)
        return {
            "user_id": user_id,
            "window": window_str,
            "ceiling_paise": ceiling_paise,
            "ceiling_rupees": ceiling_paise / 100.0,
            "total_exposure_paise": exposure,
            "total_exposure_rupees": exposure / 100.0,
            "remaining_headroom_paise": headroom,
            "remaining_headroom_rupees": headroom / 100.0,
            "active_envelopes_count": int(active_count),
        }


def reserve_headroom(mandate_id: str, amount_paise: int, idempotency_key: str,
                     ttl_seconds: int | None = None) -> Reservation:
    """Atomically claim headroom under a mandate. The only way to reach money.

    Runs the re-check and the write inside one BEGIN IMMEDIATE transaction, so
    two concurrent turns cannot both observe the same free headroom. Returns a
    Reservation; callers must branch only on `.granted`.

    `idempotency_key` makes retries safe: the same key returns the same
    reservation, and a key whose work already committed replays the stored
    Razorpay reference instead of charging again.
    """
    ttl = RESERVATION_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    now = time.time()
    cx = _configure(sqlite3.connect(get_settings().db_path, timeout=15.0))
    try:
        cx.execute("BEGIN IMMEDIATE")               # take the write lock up front

        m = cx.execute("SELECT * FROM mandates WHERE id=?", (mandate_id,)).fetchone()
        if not m:
            cx.rollback()
            return Reservation(granted=False, reason="UNKNOWN_MANDATE")
        if not m["active"]:
            cx.rollback()
            return Reservation(granted=False, mandate_id=mandate_id,
                               reason="MANDATE_REVOKED")

        prior = cx.execute(
            "SELECT * FROM spend_ledger WHERE mandate_id=? AND idempotency_key=? "
            "AND status!='released' ORDER BY created_at DESC LIMIT 1",
            (mandate_id, idempotency_key),
        ).fetchone()
        if prior:
            if prior["status"] == "committed":
                cx.commit()
                return Reservation(granted=True, id=prior["id"], mandate_id=mandate_id,
                                   amount_paise=prior["amount_paise"], replayed=True,
                                   razorpay_ref=prior["razorpay_ref"],
                                   reason="REPLAYED_COMMITTED")
            if (prior["expires_at"] or 0) > now:
                cx.commit()
                return Reservation(granted=True, id=prior["id"], mandate_id=mandate_id,
                                   amount_paise=prior["amount_paise"],
                                   reason="REPLAYED_RESERVED")
            # Expired: free it so this key can be retried cleanly.
            cx.execute("UPDATE spend_ledger SET status='released', expires_at=NULL "
                       "WHERE id=?", (prior["id"],))

        window = Window(m["window"])
        since = now - WINDOW_SECONDS[window]
        consumed = int(cx.execute(_CONSUMED_SQL, (mandate_id, since, now)).fetchone()["s"])
        headroom = m["cap_paise"] - consumed

        if amount_paise > headroom:
            cx.commit()
            return Reservation(granted=False, mandate_id=mandate_id,
                               amount_paise=amount_paise, headroom_paise=max(0, headroom),
                               reason="INSUFFICIENT_HEADROOM")

        rid = f"rsv_{uuid.uuid4().hex[:12]}"
        cx.execute(
            "INSERT INTO spend_ledger (id,mandate_id,amount_paise,status,"
            "idempotency_key,expires_at,razorpay_ref,created_at) "
            "VALUES (?,?,?,'reserved',?,?,NULL,?)",
            (rid, mandate_id, amount_paise, idempotency_key, now + ttl, now),
        )
        cx.commit()
        return Reservation(granted=True, id=rid, mandate_id=mandate_id,
                           amount_paise=amount_paise,
                           headroom_paise=headroom - amount_paise, reason="RESERVED")
    finally:
        cx.close()


def _row_to_action_grant(row: sqlite3.Row) -> ActionGrant:
    legacy_states = {
        "reserved": ActionState.AUTHORIZED,
        "committed": ActionState.ACTION_ISSUED,
        "released": ActionState.CANCELLED,
    }
    raw_state = str(row["status"])
    state = legacy_states[raw_state] if raw_state in legacy_states else ActionState(raw_state)
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return ActionGrant(
        id=row["id"],
        mandate_id=row["mandate_id"],
        mandate_version=int(row["mandate_version"] or 0),
        policy_hash=row["policy_hash"] or "",
        user_id=row["user_id"] or "",
        agent_id=row["agent_id"] or "",
        session_id=row["session_id"] or "",
        merchant_id=row["merchant_id"] or "",
        action_name=row["action_name"] or "",
        action_schema_hash=row["action_schema_hash"] or "",
        args_hash=row["args_hash"] or "",
        cart_hash=row["cart_hash"] or "",
        amount_paise=int(row["amount_paise"]),
        currency=row["currency"] or "",
        purchase_attempt_id=row["purchase_attempt_id"] or row["idempotency_key"] or "",
        envelope_id=row["envelope_id"],
        envelope_version=row["envelope_version"],
        envelope_hash=row["envelope_hash"],
        quote_hash=row["quote_hash"],
        state=state,
        expires_at=row["expires_at"],
        provider_ref=row["razorpay_ref"],
        result=result,
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"] or row["created_at"]),
    )


def get_action_grant(grant_id: str) -> ActionGrant | None:
    with _conn() as cx:
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
    return _row_to_action_grant(row) if row else None


def get_action_grant_for_attempt(
    mandate_id: str, purchase_attempt_id: str
) -> ActionGrant | None:
    with _conn() as cx:
        row = cx.execute(
            """SELECT * FROM spend_ledger
               WHERE mandate_id=? AND idempotency_key=?
                 AND status NOT IN ('released','cancelled','definitive_failure')
               ORDER BY created_at DESC LIMIT 1""",
            (mandate_id, purchase_attempt_id),
        ).fetchone()
    return _row_to_action_grant(row) if row else None


def _action_denial(
    mandate: Mandate | None,
    request: AuthorizationRequest,
    code: DecisionCode,
    message: str,
    already_spent_paise: int = 0,
) -> MandateDecision:
    cap = mandate.cap_paise if mandate else 0
    return MandateDecision(
        allowed=False,
        code=code,
        mandate_id=mandate.id if mandate else request.mandate_id,
        mandate_version=mandate.version if mandate else None,
        cart_total_paise=request.cart.total_paise,
        cap_paise=cap,
        already_spent_paise=already_spent_paise,
        headroom_paise=max(0, cap - already_spent_paise),
        human_message=message,
    )


def _replay_decision(mandate: Mandate, request: AuthorizationRequest) -> MandateDecision:
    return MandateDecision(
        allowed=True,
        code=DecisionCode.ALLOW,
        mandate_id=mandate.id,
        mandate_version=request.expected_mandate_version,
        cart_total_paise=request.cart.total_paise,
        cap_paise=mandate.cap_paise,
        human_message="This exact purchase attempt already has a stored result.",
    )


def _binding_conflicts(
    row: sqlite3.Row,
    request: AuthorizationRequest,
    args_hash: str,
    amount_paise: int,
    currency: str,
) -> list[str]:
    expected = {
        "user_id": request.context.user_id,
        "agent_id": request.context.agent_id,
        "session_id": request.context.session_id,
        "merchant_id": request.context.merchant_id,
        "action_name": request.action_name,
        "action_schema_hash": request.action_schema_hash,
        "args_hash": args_hash,
        "cart_hash": request.cart_hash,
        "amount_paise": amount_paise,
        "currency": currency,
        "purchase_attempt_id": request.purchase_attempt_id,
        "envelope_id": request.envelope_id,
        "envelope_version": request.expected_envelope_version,
        "envelope_hash": request.expected_envelope_hash,
        "quote_hash": request.quote.quote_hash if request.quote else None,
    }
    return [name for name, value in expected.items() if row[name] != value]


def _insert_replay_audit(
    cx: sqlite3.Connection,
    mandate: Mandate,
    request: AuthorizationRequest,
    grant: ActionGrant,
    reason: str,
) -> None:
    _insert_audit_row(
        cx,
        event="ACTION_REPLAY_RETURNED",
        session_id=request.context.session_id,
        mandate_id=mandate.id,
        mandate_version=mandate.version,
        code=reason,
        cart_total_paise=request.cart.total_paise,
        cap_paise=mandate.cap_paise,
        payload={
            "grant_id": grant.id,
            "purchase_attempt_id": request.purchase_attempt_id,
            "original_state": grant.state.value,
            "provider_call_made": False,
            "surface": "authorization_gate",
        },
    )


def authorize_and_reserve(request: AuthorizationRequest) -> AuthorizationOutcome:
    """Atomically evaluate the complete policy and mint one exact action grant."""
    from .actions import (
        ActionNotRegistered,
        InvalidActionArguments,
        canonicalize_action,
    )
    from .mandate import verify

    now = time.time()
    amount_paise = request.cart.total_paise
    currency = request.args.get("currency")
    raw_amount = request.args.get("amount")
    computed_cart_hash = compute_cart_hash(request.cart)
    request_args_hash = action_args_hash(request.action_name, request.args)

    cx = _configure(sqlite3.connect(get_settings().db_path, timeout=15.0))
    try:
        cx.execute("BEGIN IMMEDIATE")
        mandate_row = cx.execute(
            "SELECT * FROM mandates WHERE id=?", (request.mandate_id,)
        ).fetchone()
        mandate = _row_to_mandate(mandate_row) if mandate_row else None

        if not mandate:
            decision = _action_denial(
                None,
                request,
                DecisionCode.BLOCK_NO_MANDATE,
                "No authorization policy exists for this agent.",
            )
            _insert_audit_row(
                cx,
                event="AUTHORIZATION_ATTEMPT",
                session_id=request.context.session_id,
                mandate_id=request.mandate_id,
                code=decision.code.value,
                cart_total_paise=amount_paise,
            )
            cx.commit()
            return AuthorizationOutcome(
                authorized=False, decision=decision, reason="UNKNOWN_POLICY"
            )

        registry_reason = None
        try:
            registered_action = canonicalize_action(request.action_name, request.args)
        except ActionNotRegistered:
            registry_reason = "ACTION_NOT_REGISTERED"
        except InvalidActionArguments:
            registry_reason = "ACTION_ARGUMENTS_INVALID"
        else:
            if request.action_schema_hash != registered_action.schema_hash:
                registry_reason = "ACTION_SCHEMA_MISMATCH"
            elif request.args != registered_action.args:
                registry_reason = "ACTION_ARGUMENTS_NOT_CANONICAL"

        if registry_reason:
            decision = _action_denial(
                mandate,
                request,
                DecisionCode.BLOCK_INVALID_ACTION,
                "The requested action is not registered with its exact approved schema.",
            )
            _insert_audit_row(
                cx,
                event="AUTHORIZATION_REJECTED",
                session_id=request.context.session_id,
                mandate_id=mandate.id,
                mandate_version=mandate.version,
                code=registry_reason,
                cart_total_paise=amount_paise,
                cap_paise=mandate.cap_paise,
                payload={"action": request.action_name},
            )
            cx.commit()
            return AuthorizationOutcome(
                authorized=False,
                decision=decision,
                reason=registry_reason,
            )

        prior = cx.execute(
            """SELECT * FROM spend_ledger
               WHERE mandate_id=? AND idempotency_key=?
                 AND status NOT IN ('released','cancelled','definitive_failure')
               ORDER BY created_at DESC LIMIT 1""",
            (request.mandate_id, request.purchase_attempt_id),
        ).fetchone()
        if prior:
            conflicts = _binding_conflicts(
                prior, request, request_args_hash, amount_paise, str(currency)
            )
            if conflicts:
                decision = _action_denial(
                    mandate,
                    request,
                    DecisionCode.BLOCK_INVALID_ACTION,
                    "This purchase-attempt identity is already bound to a different action.",
                )
                _insert_audit_row(
                    cx,
                    event="AUTHORIZATION_REJECTED",
                    session_id=request.context.session_id,
                    mandate_id=mandate.id,
                    mandate_version=mandate.version,
                    code="IDEMPOTENCY_BINDING_CONFLICT",
                    cart_total_paise=amount_paise,
                    cap_paise=mandate.cap_paise,
                    payload={"conflicting_fields": conflicts, "grant_id": prior["id"]},
                )
                cx.commit()
                return AuthorizationOutcome(
                    authorized=False,
                    decision=decision,
                    reason="IDEMPOTENCY_BINDING_CONFLICT",
                )

            status = str(prior["status"])
            grant = _row_to_action_grant(prior)
            if status in ("committed", "action_issued", "settled"):
                _insert_replay_audit(cx, mandate, request, grant, "REPLAYED_RESULT")
                cx.commit()
                return AuthorizationOutcome(
                    authorized=True,
                    decision=_replay_decision(mandate, request),
                    grant=grant,
                    replayed=True,
                    reason="REPLAYED_RESULT",
                )
            if status in ("dispatching", "unknown"):
                replay_reason = (
                    "UNKNOWN_OUTCOME" if status == "unknown" else "ACTION_IN_PROGRESS"
                )
                _insert_replay_audit(cx, mandate, request, grant, replay_reason)
                cx.commit()
                return AuthorizationOutcome(
                    authorized=False,
                    decision=_replay_decision(mandate, request),
                    grant=grant,
                    in_progress=True,
                    reason=replay_reason,
                )
            if status in ("reserved", "authorized") and (prior["expires_at"] or 0) > now:
                _insert_replay_audit(cx, mandate, request, grant, "REUSED_AUTHORIZATION")
                cx.commit()
                return AuthorizationOutcome(
                    authorized=True,
                    decision=_replay_decision(mandate, request),
                    grant=grant,
                    reason="REUSED_AUTHORIZATION",
                )
            if status in ("reserved", "authorized"):
                cx.execute(
                    """UPDATE spend_ledger
                       SET status='cancelled',expires_at=NULL,error=?,updated_at=?
                       WHERE id=? AND status IN ('reserved','authorized')""",
                    ("AUTHORIZATION_EXPIRED", now, prior["id"]),
                )

        invalid_reason = None
        if request.context.user_id != mandate.user_id or request.context.agent_id != mandate.agent_id:
            invalid_reason = "ACTION_CONTEXT_MISMATCH"
        elif request.expected_mandate_version != mandate.version:
            invalid_reason = "POLICY_VERSION_CHANGED"
        elif request.cart_hash != computed_cart_hash:
            invalid_reason = "CART_HASH_MISMATCH"
        elif amount_paise <= 0:
            invalid_reason = "EMPTY_OR_ZERO_CART"
        elif isinstance(raw_amount, bool) or not isinstance(raw_amount, int):
            invalid_reason = "ACTION_AMOUNT_INVALID"
        elif raw_amount != amount_paise:
            invalid_reason = "ACTION_AMOUNT_MISMATCH"
        elif currency != "INR":
            invalid_reason = "ACTION_CURRENCY_INVALID"

        if invalid_reason:
            code = (
                DecisionCode.BLOCK_STALE_POLICY_VERSION
                if invalid_reason == "POLICY_VERSION_CHANGED"
                else DecisionCode.BLOCK_INVALID_ACTION
            )
            decision = _action_denial(
                mandate,
                request,
                code,
                "The confirmed action no longer matches the current policy or canonical cart.",
            )
            _insert_audit_row(
                cx,
                event="AUTHORIZATION_REJECTED",
                session_id=request.context.session_id,
                mandate_id=mandate.id,
                mandate_version=mandate.version,
                code=invalid_reason,
                cart_total_paise=amount_paise,
                cap_paise=mandate.cap_paise,
            )
            cx.commit()
            return AuthorizationOutcome(
                authorized=False, decision=decision, reason=invalid_reason
            )

        if request.envelope_id is not None:
            from .envelope import verify_quote

            envelope_row = cx.execute(
                "SELECT * FROM purchase_envelopes WHERE id=?", (request.envelope_id,)
            ).fetchone()
            envelope = _row_to_envelope(envelope_row) if envelope_row else None
            envelope_reason = None
            if not envelope:
                envelope_reason = "UNKNOWN_ENVELOPE"
            elif request.quote is None:
                envelope_reason = "QUOTE_REQUIRED"
            elif request.expected_envelope_version != envelope.version:
                envelope_reason = "ENVELOPE_VERSION_CHANGED"
            elif request.expected_envelope_hash != envelope.envelope_hash:
                envelope_reason = "ENVELOPE_HASH_CHANGED"
            elif envelope.envelope_hash != compute_envelope_hash(envelope):
                envelope_reason = "ENVELOPE_STORAGE_INTEGRITY_FAILURE"
            elif (
                envelope.user_id != request.context.user_id
                or envelope.agent_id != request.context.agent_id
                or envelope.merchant_id != request.context.merchant_id
                or envelope.mandate_id != mandate.id
                or envelope.action_name != request.action_name
            ):
                envelope_reason = "ENVELOPE_CONTEXT_MISMATCH"
            elif request.quote.cart != request.cart:
                envelope_reason = "QUOTE_CART_MISMATCH"
            else:
                envelope_decision = verify_quote(envelope, request.quote, now=now)
                if not envelope_decision.allowed:
                    envelope_reason = envelope_decision.code

            if envelope_reason:
                decision = _action_denial(
                    mandate,
                    request,
                    DecisionCode.BLOCK_INVALID_ACTION,
                    "The final quote is outside the active Purchase Envelope.",
                )
                _insert_audit_row(
                    cx,
                    event="ENVELOPE_AUTHORIZATION_REJECTED",
                    session_id=request.context.session_id,
                    mandate_id=mandate.id,
                    mandate_version=mandate.version,
                    code=envelope_reason,
                    cart_total_paise=amount_paise,
                    cap_paise=envelope.max_total_paise if envelope else 0,
                    payload={"envelope_id": request.envelope_id},
                )
                cx.commit()
                return AuthorizationOutcome(
                    authorized=False, decision=decision, reason=envelope_reason
                )

            prior_use = cx.execute(
                """SELECT id,status FROM spend_ledger
                   WHERE envelope_id=?
                     AND status NOT IN ('released','cancelled','definitive_failure')
                   ORDER BY created_at DESC LIMIT 1""",
                (request.envelope_id,),
            ).fetchone()
            if prior_use:
                decision = _action_denial(
                    mandate,
                    request,
                    DecisionCode.BLOCK_INVALID_ACTION,
                    "This one-purchase envelope has already been used or is in flight.",
                )
                _insert_audit_row(
                    cx,
                    event="ENVELOPE_AUTHORIZATION_REJECTED",
                    session_id=request.context.session_id,
                    mandate_id=mandate.id,
                    mandate_version=mandate.version,
                    code="ENVELOPE_ALREADY_USED",
                    cart_total_paise=amount_paise,
                    cap_paise=envelope.max_total_paise,
                    payload={
                        "envelope_id": request.envelope_id,
                        "existing_grant_id": prior_use["id"],
                        "existing_status": prior_use["status"],
                    },
                )
                cx.commit()
                return AuthorizationOutcome(
                    authorized=False, decision=decision, reason="ENVELOPE_ALREADY_USED"
                )
        elif any(
            value is not None
            for value in (
                request.expected_envelope_version,
                request.expected_envelope_hash,
                request.quote,
            )
        ):
            decision = _action_denial(
                mandate,
                request,
                DecisionCode.BLOCK_INVALID_ACTION,
                "Incomplete Purchase Envelope binding.",
            )
            cx.commit()
            return AuthorizationOutcome(
                authorized=False, decision=decision, reason="INCOMPLETE_ENVELOPE_BINDING"
            )

        window = mandate.window
        since = now - WINDOW_SECONDS[window]
        consumed = int(
            cx.execute(_CONSUMED_SQL, (mandate.id, since, now)).fetchone()["s"]
        )
        decision = verify(request.cart, mandate, consumed)
        if not decision.allowed:
            _insert_audit_row(
                cx,
                event="AUTHORIZATION_ATTEMPT",
                session_id=request.context.session_id,
                mandate_id=mandate.id,
                mandate_version=mandate.version,
                code=decision.code.value,
                cart_total_paise=amount_paise,
                cap_paise=mandate.cap_paise,
                payload={"already_exposed_paise": consumed},
            )
            cx.commit()
            return AuthorizationOutcome(
                authorized=False, decision=decision, reason=decision.code.value
            )

        # Cross-mandate user authority ceiling check inside the transaction
        ceiling_row = cx.execute(
            "SELECT * FROM authority_ceilings WHERE user_id=?",
            (request.context.user_id,),
        ).fetchone()
        if ceiling_row:
            c_window = Window(ceiling_row["window"])
            ceiling_paise = int(ceiling_row["ceiling_paise"])
            since_c = now - WINDOW_SECONDS[c_window] if c_window != Window.PER_TXN else 0
            user_exposure = int(
                cx.execute(
                    _USER_EXPOSURE_SQL, (request.context.user_id, since_c, now)
                ).fetchone()["s"]
            )
            if user_exposure + amount_paise > ceiling_paise:
                ceiling_decision = MandateDecision(
                    allowed=False,
                    code=DecisionCode.BLOCK_USER_CEILING_EXCEEDED,
                    mandate_id=mandate.id,
                    mandate_version=mandate.version,
                    cart_total_paise=amount_paise,
                    cap_paise=ceiling_paise,
                    already_spent_paise=user_exposure,
                    headroom_paise=max(0, ceiling_paise - user_exposure),
                    human_message=(
                        f"The requested amount of ₹{amount_paise / 100:.2f} exceeds your "
                        f"aggregate user authority ceiling of ₹{ceiling_paise / 100:.2f} ({ceiling_row['window']}). "
                        f"Current exposure: ₹{user_exposure / 100:.2f}."
                    ),
                )
                _insert_audit_row(
                    cx,
                    event="AUTHORIZATION_ATTEMPT",
                    session_id=request.context.session_id,
                    mandate_id=mandate.id,
                    mandate_version=mandate.version,
                    code=DecisionCode.BLOCK_USER_CEILING_EXCEEDED.value,
                    cart_total_paise=amount_paise,
                    cap_paise=ceiling_paise,
                    payload={
                        "user_id": request.context.user_id,
                        "ceiling_paise": ceiling_paise,
                        "user_exposure_paise": user_exposure,
                        "requested_paise": amount_paise,
                    },
                )
                cx.commit()
                return AuthorizationOutcome(
                    authorized=False,
                    decision=ceiling_decision,
                    reason=DecisionCode.BLOCK_USER_CEILING_EXCEEDED.value,
                )

        revision_hash = policy_hash(mandate)
        _insert_policy_revision(cx, mandate)
        grant_id = f"act_{uuid.uuid4().hex}"
        expires_at = now + request.ttl_seconds
        cx.execute(
            """INSERT INTO spend_ledger (
                   id,mandate_id,amount_paise,status,idempotency_key,expires_at,
                   razorpay_ref,user_id,agent_id,session_id,merchant_id,
                   mandate_version,policy_hash,action_name,action_schema_hash,
                   args_json,args_hash,cart_hash,currency,purchase_attempt_id,
                   envelope_id,envelope_version,envelope_hash,quote_hash,
                   result_json,error,dispatch_token,created_at,updated_at
               ) VALUES (
                   :id,:mandate_id,:amount_paise,'authorized',:idempotency_key,
                   :expires_at,NULL,:user_id,:agent_id,:session_id,:merchant_id,
                   :mandate_version,:policy_hash,:action_name,:action_schema_hash,
                   :args_json,:args_hash,:cart_hash,:currency,:purchase_attempt_id,
                   :envelope_id,:envelope_version,:envelope_hash,:quote_hash,
                   NULL,NULL,NULL,:created_at,:updated_at
               )""",
            {
                "id": grant_id,
                "mandate_id": mandate.id,
                "amount_paise": amount_paise,
                "idempotency_key": request.purchase_attempt_id,
                "expires_at": expires_at,
                "user_id": request.context.user_id,
                "agent_id": request.context.agent_id,
                "session_id": request.context.session_id,
                "merchant_id": request.context.merchant_id,
                "mandate_version": mandate.version,
                "policy_hash": revision_hash,
                "action_name": request.action_name,
                "action_schema_hash": request.action_schema_hash,
                "args_json": canonical_json(request.args),
                "args_hash": request_args_hash,
                "cart_hash": request.cart_hash,
                "currency": currency,
                "purchase_attempt_id": request.purchase_attempt_id,
                "envelope_id": request.envelope_id,
                "envelope_version": request.expected_envelope_version,
                "envelope_hash": request.expected_envelope_hash,
                "quote_hash": request.quote.quote_hash if request.quote else None,
                "created_at": now,
                "updated_at": now,
            },
        )
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        _insert_audit_row(
            cx,
            event="AUTHORIZATION_ATTEMPT",
            session_id=request.context.session_id,
            mandate_id=mandate.id,
            mandate_version=mandate.version,
            code=DecisionCode.ALLOW.value,
            cart_total_paise=amount_paise,
            cap_paise=mandate.cap_paise,
            payload={
                "grant_id": grant_id,
                "action": request.action_name,
                "args_hash": request_args_hash,
                "cart_hash": request.cart_hash,
                "policy_hash": revision_hash,
                "purchase_attempt_id": request.purchase_attempt_id,
                "envelope_id": request.envelope_id,
                "envelope_version": request.expected_envelope_version,
                "envelope_hash": request.expected_envelope_hash,
                "quote_hash": request.quote.quote_hash if request.quote else None,
            },
        )
        cx.commit()
        return AuthorizationOutcome(
            authorized=True,
            decision=decision,
            grant=_row_to_action_grant(row),
            reason="AUTHORIZED",
        )
    finally:
        cx.close()


def _cancel_grant_in_transaction(
    cx: sqlite3.Connection,
    row: sqlite3.Row,
    reason: str,
) -> None:
    now = time.time()
    cx.execute(
        """UPDATE spend_ledger
           SET status='cancelled',expires_at=NULL,error=?,updated_at=?
           WHERE id=? AND status IN ('reserved','authorized')""",
        (reason, now, row["id"]),
    )
    _insert_audit_row(
        cx,
        event="ACTION_REJECTED",
        session_id=row["session_id"],
        mandate_id=row["mandate_id"],
        mandate_version=row["mandate_version"],
        code=reason,
        cart_total_paise=row["amount_paise"],
        payload={"grant_id": row["id"], "action": row["action_name"]},
    )


def cancel_action_grant(grant_id: str, reason: str) -> bool:
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        if not row or row["status"] not in ("reserved", "authorized"):
            return False
        _cancel_grant_in_transaction(cx, row, reason)
        return True


def claim_action_grant(
    grant_id: str,
    *,
    context: ActionContext,
    action_name: str,
    action_schema_hash: str,
    args: dict,
    cart_hash: str,
) -> tuple[ActionGrant | None, str | None, str]:
    """Claim single dispatch ownership after exact binding and policy fencing."""
    now = time.time()
    args_hash = action_args_hash(action_name, args)
    cx = _configure(sqlite3.connect(get_settings().db_path, timeout=15.0))
    try:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        if not row:
            cx.rollback()
            return None, None, "UNKNOWN_GRANT"

        status = str(row["status"])
        if status == "dispatching":
            cx.commit()
            return _row_to_action_grant(row), None, "ACTION_IN_PROGRESS"
        if status == "unknown":
            cx.commit()
            return _row_to_action_grant(row), None, "UNKNOWN_OUTCOME"
        if status in ("committed", "action_issued", "settled"):
            cx.commit()
            return _row_to_action_grant(row), None, "ALREADY_ISSUED"
        if status not in ("reserved", "authorized"):
            cx.commit()
            return _row_to_action_grant(row), None, "GRANT_NOT_ACTIVE"
        if (row["expires_at"] or 0) <= now:
            _cancel_grant_in_transaction(cx, row, "AUTHORIZATION_EXPIRED")
            cx.commit()
            return None, None, "AUTHORIZATION_EXPIRED"

        mismatches = []
        expected = {
            "user_id": context.user_id,
            "agent_id": context.agent_id,
            "session_id": context.session_id,
            "merchant_id": context.merchant_id,
            "action_name": action_name,
            "action_schema_hash": action_schema_hash,
            "args_hash": args_hash,
            "cart_hash": cart_hash,
        }
        for name, value in expected.items():
            if row[name] != value:
                mismatches.append(name)
        amount = args.get("amount")
        currency = args.get("currency")
        if isinstance(amount, bool) or amount != row["amount_paise"]:
            mismatches.append("amount_paise")
        if currency != row["currency"]:
            mismatches.append("currency")
        if mismatches:
            _cancel_grant_in_transaction(
                cx, row, "ACTION_BINDING_MISMATCH:" + ",".join(sorted(set(mismatches)))
            )
            cx.commit()
            return None, None, "ACTION_BINDING_MISMATCH"

        mandate_row = cx.execute(
            "SELECT * FROM mandates WHERE id=?", (row["mandate_id"],)
        ).fetchone()
        mandate = _row_to_mandate(mandate_row) if mandate_row else None
        if (
            not mandate
            or not mandate.active
            or mandate.version != row["mandate_version"]
            or policy_hash(mandate) != row["policy_hash"]
        ):
            _cancel_grant_in_transaction(cx, row, "POLICY_CHANGED_BEFORE_DISPATCH")
            cx.commit()
            return None, None, "POLICY_CHANGED_BEFORE_DISPATCH"

        if row["envelope_id"]:
            envelope_row = cx.execute(
                "SELECT * FROM purchase_envelopes WHERE id=?", (row["envelope_id"],)
            ).fetchone()
            envelope = _row_to_envelope(envelope_row) if envelope_row else None
            if (
                not envelope
                or envelope.status is not EnvelopeStatus.ACTIVE
                or envelope.version != row["envelope_version"]
                or envelope.envelope_hash != row["envelope_hash"]
                or compute_envelope_hash(envelope) != row["envelope_hash"]
            ):
                _cancel_grant_in_transaction(
                    cx, row, "ENVELOPE_CHANGED_BEFORE_DISPATCH"
                )
                cx.commit()
                return None, None, "ENVELOPE_CHANGED_BEFORE_DISPATCH"

        dispatch_token = f"dsp_{uuid.uuid4().hex}"
        updated = cx.execute(
            """UPDATE spend_ledger
               SET status='dispatching',dispatch_token=?,expires_at=NULL,updated_at=?
               WHERE id=? AND status IN ('reserved','authorized')""",
            (dispatch_token, now, grant_id),
        )
        if updated.rowcount != 1:
            cx.rollback()
            return None, None, "DISPATCH_CLAIM_CONFLICT"
        claimed = cx.execute(
            "SELECT * FROM spend_ledger WHERE id=?", (grant_id,)
        ).fetchone()
        _insert_audit_row(
            cx,
            event="ACTION_DISPATCH_STARTED",
            session_id=row["session_id"],
            mandate_id=row["mandate_id"],
            mandate_version=row["mandate_version"],
            code="DISPATCHING",
            cart_total_paise=row["amount_paise"],
            payload={"grant_id": grant_id, "action": action_name},
        )
        cx.commit()
        return _row_to_action_grant(claimed), dispatch_token, "DISPATCH_CLAIMED"
    finally:
        cx.close()


def mark_action_issued(
    grant_id: str,
    dispatch_token: str,
    *,
    provider_ref: str | None,
    result: dict,
) -> ActionGrant:
    now = time.time()
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        updated = cx.execute(
            """UPDATE spend_ledger
               SET status='action_issued',razorpay_ref=?,result_json=?,
                   error=NULL,dispatch_token=NULL,updated_at=?
               WHERE id=? AND status IN ('dispatching','unknown')
                 AND dispatch_token=?""",
            (provider_ref, canonical_json(result), now, grant_id, dispatch_token),
        )
        if updated.rowcount != 1:
            raise RuntimeError("ACTION_ISSUED_TRANSITION_CONFLICT")
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        if row["envelope_id"]:
            envelope_row = cx.execute(
                "SELECT * FROM purchase_envelopes WHERE id=?", (row["envelope_id"],)
            ).fetchone()
            if envelope_row and envelope_row["status"] == EnvelopeStatus.ACTIVE.value:
                current = _row_to_envelope(envelope_row)
                consumed = current.model_copy(
                    update={
                        "status": EnvelopeStatus.CONSUMED,
                        "updated_at": now,
                        "envelope_hash": "",
                    }
                )
                consumed = consumed.model_copy(
                    update={"envelope_hash": compute_envelope_hash(consumed)}
                )
                cx.execute(
                    """UPDATE purchase_envelopes
                       SET status='consumed',envelope_hash=?,updated_at=?
                       WHERE id=? AND status='active' AND version=?""",
                    (
                        consumed.envelope_hash,
                        now,
                        consumed.id,
                        consumed.version,
                    ),
                )
                _insert_audit_row(
                    cx,
                    event="ENVELOPE_CONSUMED",
                    session_id=row["session_id"],
                    mandate_id=row["mandate_id"],
                    mandate_version=row["mandate_version"],
                    code="CONSUMED",
                    cart_total_paise=row["amount_paise"],
                    payload={
                        "envelope_id": consumed.id,
                        "grant_id": grant_id,
                    },
                )
        _insert_audit_row(
            cx,
            event="ACTION_ISSUED",
            session_id=row["session_id"],
            mandate_id=row["mandate_id"],
            mandate_version=row["mandate_version"],
            code="ACTION_ISSUED",
            cart_total_paise=row["amount_paise"],
            payload={"grant_id": grant_id, "provider_ref": provider_ref},
        )
        return _row_to_action_grant(row)


def settle_issued_action(
    grant_id: str,
    *,
    provider_ref: str | None,
    result: dict,
) -> ActionGrant:
    """Record that the provider says this action's money actually moved.

    This is the only transition into `settled`, and it exists so that
    invariant 10 has a way to be *satisfied* rather than only respected.
    Issuing a payment link records ACTION_ISSUED; settlement is a separate
    fact that only an authoritative provider observation may assert.

    Deliberately not callable with a caller-supplied status: `app/reconciler.py`
    fetches the provider's own view first and passes what it read. Nothing on
    the HTTP surface can declare a payment settled.
    """
    now = time.time()
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        updated = cx.execute(
            """UPDATE spend_ledger
               SET status='settled',razorpay_ref=COALESCE(?,razorpay_ref),
                   result_json=?,error=NULL,dispatch_token=NULL,updated_at=?
               WHERE id=? AND status='action_issued'""",
            (provider_ref, canonical_json(result), now, grant_id),
        )
        if updated.rowcount != 1:
            raise RuntimeError("SETTLEMENT_TRANSITION_CONFLICT")
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        _insert_audit_row(
            cx,
            event="ACTION_SETTLED",
            session_id=row["session_id"],
            mandate_id=row["mandate_id"],
            mandate_version=row["mandate_version"],
            code="SETTLED",
            cart_total_paise=row["amount_paise"],
            payload={"grant_id": grant_id, "provider_ref": provider_ref},
        )
        return _row_to_action_grant(row)


def open_actions_for_reconciliation(limit: int = 50) -> list[ActionGrant]:
    """Grants whose provider outcome is not yet final.

    `action_issued` means a link exists but nobody has confirmed payment.
    `unknown` means we do not know whether money moved. Both hold exposure and
    both are resolvable only by asking the provider.
    """
    with _conn() as cx:
        rows = cx.execute(
            """SELECT * FROM spend_ledger
               WHERE status IN ('action_issued','unknown')
               ORDER BY updated_at ASC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [_row_to_action_grant(r) for r in rows]


def recover_stale_dispatches(cutoff_seconds: float = 60.0) -> int:
    """Turn crash-stranded dispatch claims into UNKNOWN without freeing headroom.

    The provider may have accepted the action before this process disappeared,
    so recovery must never cancel or retry it. The original dispatch token is
    retained: a late result held by that exact owner may still close the state.
    """
    now = time.time()
    cutoff = now - max(0.0, cutoff_seconds)
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        rows = cx.execute(
            """SELECT * FROM spend_ledger
               WHERE status='dispatching'
                 AND COALESCE(updated_at,created_at)<=?""",
            (cutoff,),
        ).fetchall()
        for row in rows:
            updated = cx.execute(
                """UPDATE spend_ledger
                   SET status='unknown',error=?,updated_at=?
                   WHERE id=? AND status='dispatching'""",
                ("PROCESS_INTERRUPTED_AFTER_DISPATCH_CLAIM", now, row["id"]),
            )
            if updated.rowcount != 1:
                continue
            _insert_audit_row(
                cx,
                event="ACTION_OUTCOME_UNKNOWN",
                session_id=row["session_id"],
                mandate_id=row["mandate_id"],
                mandate_version=row["mandate_version"],
                code="STALE_DISPATCH_RECOVERED",
                cart_total_paise=row["amount_paise"],
                payload={
                    "grant_id": row["id"],
                    "reason": "PROCESS_INTERRUPTED_AFTER_DISPATCH_CLAIM",
                },
            )
        return len(rows)


def mark_action_unknown(grant_id: str, dispatch_token: str, error: str) -> ActionGrant:
    now = time.time()
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        updated = cx.execute(
            """UPDATE spend_ledger
               SET status='unknown',error=?,updated_at=?
               WHERE id=? AND status='dispatching' AND dispatch_token=?""",
            (error[:500], now, grant_id, dispatch_token),
        )
        if updated.rowcount != 1:
            raise RuntimeError("UNKNOWN_TRANSITION_CONFLICT")
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        _insert_audit_row(
            cx,
            event="ACTION_OUTCOME_UNKNOWN",
            session_id=row["session_id"],
            mandate_id=row["mandate_id"],
            mandate_version=row["mandate_version"],
            code="UNKNOWN",
            cart_total_paise=row["amount_paise"],
            payload={"grant_id": grant_id, "error": error[:200]},
        )
        return _row_to_action_grant(row)


def mark_action_definitive_failure(
    grant_id: str, dispatch_token: str, error: str
) -> ActionGrant:
    now = time.time()
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        updated = cx.execute(
            """UPDATE spend_ledger
               SET status='definitive_failure',error=?,dispatch_token=NULL,updated_at=?
               WHERE id=? AND status='dispatching' AND dispatch_token=?""",
            (error[:500], now, grant_id, dispatch_token),
        )
        if updated.rowcount != 1:
            raise RuntimeError("FAILURE_TRANSITION_CONFLICT")
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        _insert_audit_row(
            cx,
            event="ACTION_DEFINITIVE_FAILURE",
            session_id=row["session_id"],
            mandate_id=row["mandate_id"],
            mandate_version=row["mandate_version"],
            code="DEFINITIVE_FAILURE",
            cart_total_paise=row["amount_paise"],
            payload={"grant_id": grant_id, "error": error[:200]},
        )
        return _row_to_action_grant(row)


def reconcile_unknown(
    grant_id: str,
    *,
    accepted: bool,
    provider_ref: str | None = None,
    result: dict | None = None,
    settled: bool = False,
) -> ActionGrant:
    """Resolve UNKNOWN only from an authoritative provider observation."""
    now = time.time()
    new_status = "settled" if accepted and settled else (
        "action_issued" if accepted else "definitive_failure"
    )
    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        updated = cx.execute(
            """UPDATE spend_ledger
               SET status=?,razorpay_ref=COALESCE(?,razorpay_ref),result_json=?,
                   error=NULL,dispatch_token=NULL,updated_at=?
               WHERE id=? AND status='unknown'""",
            (
                new_status,
                provider_ref,
                canonical_json(result or {}),
                now,
                grant_id,
            ),
        )
        if updated.rowcount != 1:
            raise RuntimeError("RECONCILIATION_TRANSITION_CONFLICT")
        row = cx.execute("SELECT * FROM spend_ledger WHERE id=?", (grant_id,)).fetchone()
        _insert_audit_row(
            cx,
            event="ACTION_RECONCILED",
            session_id=row["session_id"],
            mandate_id=row["mandate_id"],
            mandate_version=row["mandate_version"],
            code=new_status.upper(),
            cart_total_paise=row["amount_paise"],
            payload={"grant_id": grant_id, "provider_ref": provider_ref},
        )
        return _row_to_action_grant(row)


def find_committed_reservation(mandate_id: str, idempotency_key: str) -> Reservation | None:
    """Has this legacy reservation already reached its committed state?

    This helper exists for the historical race-regression path. The active
    checkout flow uses exact action grants and distinct issued/settled states.
    """
    with _conn() as cx:
        r = cx.execute(
            "SELECT * FROM spend_ledger WHERE mandate_id=? AND idempotency_key=? "
            "AND status='committed' ORDER BY created_at DESC LIMIT 1",
            (mandate_id, idempotency_key),
        ).fetchone()
    if not r:
        return None
    return Reservation(granted=True, id=r["id"], mandate_id=mandate_id,
                       amount_paise=r["amount_paise"], replayed=True,
                       razorpay_ref=r["razorpay_ref"], reason="REPLAYED_COMMITTED")


def commit_reservation(reservation_id: str, razorpay_ref: str | None = None) -> bool:
    """Legacy test helper; an expired unclaimed hold can never commit late."""
    with _conn() as cx:
        updated = cx.execute(
            "UPDATE spend_ledger SET status='committed', expires_at=NULL, razorpay_ref=? "
            "WHERE id=? AND status='reserved' AND COALESCE(expires_at,0)>?",
            (razorpay_ref, reservation_id, time.time()),
        )
    return updated.rowcount == 1


def release_reservation(reservation_id: str) -> bool:
    """Legacy helper. Only a never-dispatched reservation may be released."""
    with _conn() as cx:
        updated = cx.execute(
            "UPDATE spend_ledger SET status='released', expires_at=NULL "
            "WHERE id=? AND status='reserved'",
            (reservation_id,),
        )
    return updated.rowcount == 1


def record_spend(mandate_id: str, amount_paise: int, razorpay_ref: str | None = None) -> None:
    """Write a committed spend directly, with NO reservation.

    Unsafe under concurrency by construction — kept only for backfill and for
    the test that reproduces the check-then-act race. Production paths must go
    through reserve_headroom() -> commit_reservation().
    """
    with _conn() as cx:
        cx.execute(
            "INSERT INTO spend_ledger (id,mandate_id,amount_paise,status,razorpay_ref,created_at) "
            "VALUES (?,?,?,'committed',?,?)",
            (f"spn_{uuid.uuid4().hex[:12]}", mandate_id, amount_paise, razorpay_ref, time.time()),
        )


def _insert_audit_row(
    cx: sqlite3.Connection,
    *,
    event: str,
    session_id: str | None = None,
    mandate_id: str | None = None,
    mandate_version: int | None = None,
    code: str | None = None,
    cart_total_paise: int | None = None,
    cap_paise: int | None = None,
    payload: dict | None = None,
) -> None:
    cx.execute(
        """INSERT INTO audit_log (id,session_id,mandate_id,mandate_version,event,code,
           cart_total_paise,cap_paise,payload,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            f"aud_{uuid.uuid4().hex[:12]}",
            session_id,
            mandate_id,
            mandate_version,
            event,
            code,
            cart_total_paise,
            cap_paise,
            json.dumps(payload or {}),
            time.time(),
        ),
    )


def log_event(event: str, session_id: str | None = None, mandate_id: str | None = None,
              mandate_version: int | None = None, code: str | None = None,
              cart_total_paise: int | None = None, cap_paise: int | None = None,
              payload: dict | None = None) -> None:
    with _conn() as cx:
        _insert_audit_row(
            cx,
            event=event,
            session_id=session_id,
            mandate_id=mandate_id,
            mandate_version=mandate_version,
            code=code,
            cart_total_paise=cart_total_paise,
            cap_paise=cap_paise,
            payload=payload,
        )


def audit_trail(session_id: str | None = None, limit: int = 200) -> list[dict]:
    q = "SELECT * FROM audit_log"
    args: tuple = ()
    if session_id:
        q += " WHERE session_id=?"
        args = (session_id,)
    q += " ORDER BY created_at DESC LIMIT ?"
    with _conn() as cx:
        rows = cx.execute(q, (*args, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"] or "{}")
        out.append(d)
    return out


def metrics(user_id: str = "user_demo") -> dict:
    """Observed action-safety and lifecycle metrics for one policy owner."""
    with _conn() as cx:
        policy_ids = [
            row["id"]
            for row in cx.execute(
                "SELECT id FROM mandates WHERE user_id=?", (user_id,)
            ).fetchall()
        ]
        if not policy_ids:
            return {
                "authorization_attempts": 0,
                "denied_authorizations": 0,
                "authorization_denial_rate": 0.0,
                "denied_requested_value_paise": 0,
                "payment_link_issued_value_paise": 0,
                "confirmed_test_payment_value_paise": 0,
                "unknown_outcome_value_paise": 0,
                "outstanding_authorized_exposure_paise": 0,
                "unauthorized_actuator_calls": 0,
                "cart_policy_previews": 0,
                "envelopes_activated": 0,
                "envelope_quotes_allowed": 0,
                "envelope_quotes_blocked": 0,
                "in_envelope_recoveries": 0,
            }
        placeholders = ",".join("?" for _ in policy_ids)
        attempts = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders})
                  AND event IN ('AUTHORIZATION_ATTEMPT','AUTHORIZATION_REJECTED')""",
            policy_ids,
        ).fetchone()["c"]
        denied = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders})
                  AND event IN ('AUTHORIZATION_ATTEMPT','AUTHORIZATION_REJECTED')
                  AND code IS NOT NULL AND code!='ALLOW'""",
            policy_ids,
        ).fetchone()["c"]
        denied_value = cx.execute(
            f"""SELECT COALESCE(SUM(cart_total_paise),0) s FROM audit_log
                WHERE mandate_id IN ({placeholders})
                  AND event IN ('AUTHORIZATION_ATTEMPT','AUTHORIZATION_REJECTED')
                  AND code IS NOT NULL AND code!='ALLOW'""",
            policy_ids,
        ).fetchone()["s"]
        previews = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders})
                  AND event='CART_POLICY_PREVIEW'""",
            policy_ids,
        ).fetchone()["c"]
        issued = cx.execute(
            """SELECT COALESCE(SUM(amount_paise),0) s FROM spend_ledger
               WHERE user_id=? AND status='action_issued'""",
            (user_id,),
        ).fetchone()["s"]
        settled = cx.execute(
            """SELECT COALESCE(SUM(amount_paise),0) s FROM spend_ledger
               WHERE user_id=? AND status='settled'""",
            (user_id,),
        ).fetchone()["s"]
        unknown = cx.execute(
            """SELECT COALESCE(SUM(amount_paise),0) s FROM spend_ledger
               WHERE user_id=? AND status='unknown'""",
            (user_id,),
        ).fetchone()["s"]
        outstanding = cx.execute(
            """SELECT COALESCE(SUM(amount_paise),0) s FROM spend_ledger
               WHERE user_id=?
                 AND (status IN ('dispatching','unknown','action_issued')
                      OR (status='authorized' AND COALESCE(expires_at,0)>?))""",
            (user_id, time.time()),
        ).fetchone()["s"]
        rejected = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders}) AND event='ACTION_REJECTED'""",
            policy_ids,
        ).fetchone()["c"]
        envelopes_activated = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders}) AND event='ENVELOPE_ACTIVATED'""",
            policy_ids,
        ).fetchone()["c"]
        envelope_quotes_allowed = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders}) AND event='ENVELOPE_QUOTE_ALLOWED'""",
            policy_ids,
        ).fetchone()["c"]
        envelope_quotes_blocked = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders}) AND event='ENVELOPE_QUOTE_BLOCKED'""",
            policy_ids,
        ).fetchone()["c"]
        envelope_recoveries = cx.execute(
            f"""SELECT COUNT(*) c FROM audit_log
                WHERE mandate_id IN ({placeholders})
                  AND event='ENVELOPE_RECOVERY_APPLIED'""",
            policy_ids,
        ).fetchone()["c"]
    return {
        "authorization_attempts": int(attempts),
        "denied_authorizations": int(denied),
        "authorization_denial_rate": round(denied / attempts, 4) if attempts else 0.0,
        "denied_requested_value_paise": int(denied_value),
        "payment_link_issued_value_paise": int(issued),
        "confirmed_test_payment_value_paise": int(settled),
        "unknown_outcome_value_paise": int(unknown),
        "outstanding_authorized_exposure_paise": int(outstanding),
        "unauthorized_actuator_calls": int(rejected),
        "cart_policy_previews": int(previews),
        "envelopes_activated": int(envelopes_activated),
        "envelope_quotes_allowed": int(envelope_quotes_allowed),
        "envelope_quotes_blocked": int(envelope_quotes_blocked),
        "in_envelope_recoveries": int(envelope_recoveries),
    }
