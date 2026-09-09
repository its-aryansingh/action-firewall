"""What this merchant will refuse, published before an agent proposes anything.

THE GAP THIS CLOSES
-------------------
An AI buyer can already discover what this store SELLS — catalog, JSON-LD, the
MCP tool surface. It cannot discover what the store will REFUSE. So today an
agent drafts an order, submits it, and learns the rules by breaking them. The
Policy Delta explains what to change, which is better than a bare "no", but it is
still after the fact.

That gap is not local to this project. ACP standardises checkout, UCP
standardises discovery, AP2 standardises how an authorization is represented —
none of them standardises what a merchant will refuse. A store that publishes its
acceptance rules is one an agent can transact with on the FIRST attempt, which is
what "sellable to AI buyers" actually requires.

Replayed against this repository's own violation corpus: of 800 constructed
violations, 700 (88%) would never have been proposed by an agent that read this
document first. Of the 492 that ended in a refusal with no repair available, 442
(90%) were preventable — Rs 5,10,385 of orders that died for want of a rule the
store already knew and never said.

WHAT PUBLICATION CANNOT DO
--------------------------
It prevents mistakes. It does not stop attacks. The remaining 12% of that corpus
is `catalog_fact_tamper` and `quote_hash_tamper` — an agent that forges a price
or a digest already knows the rules and is choosing to break them. Publication is
a courtesy to honest agents; the firewall is what handles the rest. Both numbers
belong in any claim made about this file.

DRIFT IS THE REAL RISK
----------------------
A published policy that no longer matches enforcement is worse than none: it
invites an agent to rely on a promise the server will not keep. So this document
is GENERATED from the same objects the verifier reads — `DEFAULT_CHANNEL_POLICY`,
`DEFAULT_BLOCKED_TAGS`, `ACTION_REGISTRY` — never hand-maintained alongside them.
`tests/test_acceptance_policy.py` additionally proves each published rule
BEHAVIOURALLY, by constructing a cart that violates it and asserting the verifier
actually refuses. Consistency with a constant is not enough; the claim is about
behaviour.

NAMING
------
Served at `/agent-commerce/v1/acceptance-policy`, deliberately NOT at
`/.well-known/ucp`. UCP's well-known path is a real convention with a real
schema (Google, Shopify, Amazon, Stripe and others on its council); serving
something else there would be a near-miss of a published standard rather than an
implementation of it. This is our own document and it says so.
"""
from __future__ import annotations

from typing import Any

from .actions import ACTION_REGISTRY
from .authorization import digest
from .channel_policy import DEFAULT_CHANNEL_POLICY
from .envelope import DEFAULT_BLOCKED_TAGS
from .merchant import CATALOG_REVISION, DEFAULT_MERCHANT_ID, DEFAULT_MERCHANT_NAME

#: Bumped when the SHAPE of this document changes, so an agent can tell a schema
#: change from a policy change. The policy_hash below covers the content.
ACCEPTANCE_POLICY_SCHEMA = "action-firewall/acceptance-policy@1"

#: What a caller may do about each refusal. Published so an agent can decide
#: whether to retry with a correction, ask its human, or give up — without
#: guessing from a code string.
RECOVERY_SEMANTICS: dict[str, str] = {
    "repair": (
        "The intent is acceptable and the arguments are not. A corrected proposal "
        "derived from the deltas may be resubmitted without a new human approval."
    ),
    "fresh_approval": (
        "Outside what the customer authorised. A human must widen the envelope "
        "before any equivalent proposal can succeed. Do not retry unchanged."
    ),
    "stop": (
        "No correction of this proposal can be authorised. Do not retry, with or "
        "without changes to the arguments."
    ),
}


def build_acceptance_policy() -> dict[str, Any]:
    """The merchant's acceptance rules, derived from what is actually enforced."""
    channel = DEFAULT_CHANNEL_POLICY

    document: dict[str, Any] = {
        "schema": ACCEPTANCE_POLICY_SCHEMA,
        "merchant_id": DEFAULT_MERCHANT_ID,
        "display_name": DEFAULT_MERCHANT_NAME,
        "currency": "INR",
        "amounts_are_in": "integer paise",
        "catalog_revision": CATALOG_REVISION,

        "will_accept": {
            "categories": sorted(channel["allowed_categories"]),
            "actions": sorted(channel["allowed_actions"]),
            "max_order_paise": channel["max_order_paise"],
        },

        "will_refuse": {
            "categories": sorted(channel["blocked_categories"]),
            # The rule a category allowlist cannot express. Free-Range Eggs sit
            # in `dairy`, which this buyer allows; the tag `eggs` is what a
            # pure-vegetarian kitchen must never receive.
            "ingredient_tags": sorted(DEFAULT_BLOCKED_TAGS),
            "any_action_not_listed_in": "will_accept.actions",
            "orders_above_paise": channel["max_order_paise"],
        },

        "requires": {
            "human_activation": (
                "A Purchase Envelope must be explicitly activated by the customer "
                "before any proposal against it can be authorised. No API call can "
                "perform that activation."
            ),
            "server_priced_quote": (
                "Prices, totals and availability are computed server-side from the "
                "catalog revision above. Client-supplied prices are discarded, and "
                "a proposal whose line facts disagree with the catalog is refused."
            ),
            "single_use_authorization": (
                "An authorization is bound to one cart, one amount and one purchase "
                "attempt. It cannot be replayed against a different proposal."
            ),
            "stock_at_dispatch": (
                "Availability is re-read when the order is authorised, not when it "
                "was quoted. A quote priced when four units were on the shelf will "
                "not dispatch once one remains."
            ),
        },

        "on_refusal": {
            "returns": "a list of Policy Deltas, each naming one field, its expected "
                       "value, the observed value, and a recovery",
            "recoveries": RECOVERY_SEMANTICS,
        },

        # Stating the limit is part of the claim. An agent should know that
        # reading this document makes it a well-behaved caller, not a trusted one.
        "not_covered_by_this_document": (
            "Publication prevents mistakes, not attacks. Proposals that forge "
            "catalog facts or a quote digest are refused by verification at "
            "authorization time regardless of anything stated here, and reading "
            "this document confers no additional trust."
        ),

        "registered_actions": {
            name: {"version": spec.version, "schema_hash": spec.schema_hash}
            for name, spec in sorted(ACTION_REGISTRY.items())
        },
    }

    document["policy_hash"] = digest(document)
    return document


def compute_acceptance_policy_hash() -> str:
    """The hash a decision cites, so an agent can check which rules were applied."""
    return build_acceptance_policy()["policy_hash"]
