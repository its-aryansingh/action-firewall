"""A simulated provider must not mint URLs on a domain it does not own.

THE BUG THIS PINS
-----------------
The simulated adapter returned `https://rzp.io/i/<8 random hex>` as the payment
link. `rzp.io` is Razorpay's real short-link domain, and eight hex characters is
a small enough space that a fabricated path can collide with a genuine, live
payment link belonging to another merchant. A viewer clicking a "simulated"
result could therefore land on a stranger's real payment page and be invited to
pay it. The demo also looked broken, because the link never resolved.

Both problems have the same root: inventing a URL on someone else's domain. The
simulated link now points at this deployment, which serves a page stating what
would have been created and that nothing is payable.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "simlink.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    from app.config import get_settings
    from app import store

    get_settings.cache_clear()
    store.init_db()
    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _issue_link(client: TestClient) -> str:
    chat = client.post(
        "/chat",
        json={"session_id": "sess_simlink", "message": "I need supplies for a pasta dinner"},
    ).json()
    confirmed = client.post(
        "/checkout/confirm",
        json={
            "session_id": "sess_simlink",
            "expected_cart_hash": chat["cart_hash"],
            "idempotency_key": "att_simlinktest0001",
        },
    ).json()
    link = re.search(r"https?://\S+", confirmed["reply"])
    assert link, f"no payment link in reply: {confirmed['reply']}"
    return link.group(0)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_a_simulated_link_never_points_at_a_domain_we_do_not_own(client):
    url = _issue_link(client)
    assert "rzp.io" not in url, (
        "the simulated provider is minting URLs on Razorpay's real short-link "
        "domain; a fabricated path there can collide with a live payment link"
    )
    assert "razorpay.com" not in url
    assert "/simulated/payment-link/" in url


def test_the_link_resolves_to_a_page_this_deployment_serves(client):
    url = _issue_link(client)
    path = url.split("/simulated/payment-link/")[-1]
    page = client.get(f"/simulated/payment-link/{path}")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]


def test_the_page_says_plainly_that_nothing_is_payable(client):
    """A page that looks like a checkout but isn't one would be worse than a 404."""
    url = _issue_link(client)
    path = url.split("/simulated/payment-link/")[-1]
    body = client.get(f"/simulated/payment-link/{path}").text.lower()
    assert "simulated" in body
    assert "not payable" in body
    assert "no provider was called" in body
    assert "not a settlement" in body


def test_the_page_shows_the_amount_that_was_actually_authorised(client):
    url = _issue_link(client)
    path = url.split("/simulated/payment-link/")[-1]
    body = client.get(f"/simulated/payment-link/{path}").text
    # The attempt id is carried through so a viewer can tie the page to the audit trail.
    assert "att_simlinktest0001" in body
    assert "₹" in body


def test_an_unknown_link_is_a_404_not_an_invented_page(client):
    assert client.get("/simulated/payment-link/plink_doesnotexist").status_code == 404


def test_the_page_escapes_caller_supplied_text(client):
    """Description and notes originate with the caller, so they reach HTML."""
    from app import mcp_client

    mcp_client._SIMULATED_LINKS["plink_xsstest"] = {
        "id": "plink_xsstest",
        "amount": 41_700,
        "currency": "INR",
        "description": "<script>alert(1)</script>",
        "reference_id": "att_x",
        "notes": {"purchase_attempt_id": "att_x"},
        "grant_id": "act_x",
    }
    body = client.get("/simulated/payment-link/plink_xsstest").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
