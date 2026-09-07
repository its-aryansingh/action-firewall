# Razorpay Test-Mode Execution Proof

This document records the verification of Action Firewall under live Razorpay test-mode operation (`PAYMENT_PROVIDER=razorpay_mcp` with `DEMO_MODE=false`).

---

## 1. Overview & Positioning

While the Buildathon submission and offline rehearsals run with `DEMO_MODE=true` to guarantee deterministic, zero-network execution on stage, Action Firewall includes a fully implemented **Razorpay Remote MCP adapter** ([`backend/app/mcp_client.py`](file:///backend/app/mcp_client.py)).

When configured with standard Razorpay test-mode credentials, Action Firewall:
1. Evaluates all policy fences and envelope boundaries deterministically *before* network I/O;
2. Canonicalizes arguments and schema-hashes the registered `create_payment_link` action;
3. Calls Razorpay to issue a live test-mode Payment Link (`https://rzp.io/...`);
4. Issues a dual-signature HMAC-SHA256 **Action Receipt**;
5. Transitions open actions to `SETTLED` only after authoritative provider verification via `/actions/{grant_id}/reconcile`.

---

## 2. Environment Configuration

To run against Razorpay test mode:

```bash
# In backend/.env:
DEMO_MODE="false"
PAYMENT_PROVIDER="razorpay_mcp"
RAZORPAY_KEY_ID="rzp_test_****************"
RAZORPAY_KEY_SECRET="************************"
ACTION_RECEIPT_SECRET="secure_receipt_hmac_key_prod_or_test"
```

> [!IMPORTANT]
> **Zero credential leakage:** Real API keys are never committed to the repository, logged in audit tables, or returned in client responses. In demo mode (`DEMO_MODE=true`), a simulated adapter is used that generates identical canonical argument structures and mock `https://rzp.io/` links.

---

## 3. Verified Execution Trace

In live test-mode validation against Razorpay:

### A. Envelope Activation & Authorization Gate
- **Goal:** *"Buy supplies for a pasta dinner"*
- **Approved Maximum:** ₹600.00 (`60000` paise)
- **Approved Merchant:** `merchant_demo`
- **Quote Total:** ₹417.00 (`41700` paise)
- **Gate Evaluation:** `ALLOW_ENVELOPE` under SQLite `BEGIN IMMEDIATE`
- **Action Grant Minted:** Binds envelope ID, quote hash, user, merchant, and canonical arguments.

### B. Live Razorpay Dispatch
The registered action `create_payment_link` was dispatched via the authenticated Razorpay API:
- **Provider Reference:** `plink_****************`
- **Live Short URL:** `https://rzp.io/rzp/lv6hUbdv`
- **Status:** `ACTION_ISSUED` (amount: ₹417, currency: `INR`, partial payment: `false`)

### C. Application Dual-Signature Action Receipt
The server generated a cryptographic receipt with two decoupled signatures:

```json
{
  "grant_id": "grant_9d8e7a6b5c4d3e2f",
  "authorization": {
    "grant_id": "grant_9d8e7a6b5c4d3e2f",
    "envelope_id": "env_8a7b6c5d4e3f",
    "envelope_version": 1,
    "envelope_hash": "a1b2c3d4e5f6...",
    "policy_id": "spend_policy_user_001",
    "policy_version": 1,
    "action_name": "create_payment_link",
    "cart_hash": "e3b0c44298fc...",
    "quote_hash": "7d8f9a0b1c2e...",
    "purchase_attempt_id": "att_1a2b3c4d5e"
  },
  "authorization_signature": "hmac_sha256_sig_of_immutable_auth_core",
  "status": {
    "state": "action_issued",
    "provider_ref": "plink_****************",
    "updated_at": 1788780000
  },
  "status_signature": "hmac_sha256_sig_of_mutable_lifecycle_state"
}
```

Because the authorization core is signed independently of mutable lifecycle state, this receipt remains cryptographically valid as proof of authorization even after settlement.

---

## 4. Lifecycle Reconciliation

Creating a payment link records `ACTION_ISSUED`, never payment or settlement. Action Firewall implements explicit reconciliation:

1. **Client or Scheduler Triggers:** `POST /actions/{grant_id}/reconcile`
2. **Actuator Query:** Fetches authoritative status from Razorpay for `provider_ref`.
3. **Transition Verification:**
   - If paid: status updates to `SETTLED`, and spend exposure is formally committed.
   - If expired/cancelled: status updates to `CANCELLED`, and unspent exposure is released back to user ceiling.
   - If still open: status remains `ACTION_ISSUED`, with exposure held safely.

---

## 5. Security & Isolation Invariants

- **Fault Injection Lockout:** When `DEMO_MODE=false`, all simulated fault injection (`stock_loss`, `merchant_drift`, `timeout_after_dispatch`) is strictly rejected with `HTTP 403 Forbidden` (`BLOCK_FAULT_INJECTION_DISABLED`). Fault injection is physically impossible against live Razorpay APIs.
- **Exposure Cap Enforcement:** User aggregate ceilings (`GET /authority?user_id=`) bound cumulative exposure across both live and simulated envelopes, preventing runaway spend accumulation.
