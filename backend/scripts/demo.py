"""Headless dress rehearsal of the exact demo you run for the judges.

    cd backend && python scripts/demo.py

Runs the full script end-to-end with no frontend and no network, so you can
verify the story still holds five minutes before you present.
"""
import sys, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store                                   # noqa: E402
from app.agent import handle_turn                       # noqa: E402
from app.mandate import rupees                          # noqa: E402
from app.models import ChatRequest, MandateCreate, MandateUpdate  # noqa: E402

G, R, B, D = "\033[92m", "\033[91m", "\033[94m", "\033[0m"
SID = f"demo_{uuid.uuid4().hex[:8]}"


def say(msg: str) -> None:
    print(f"\n{B}SHOPPER:{D} {msg}")
    r = handle_turn(ChatRequest(session_id=SID, message=msg))
    print(f"{B}AGENT:{D}   {r.reply}")
    if r.decision:
        c = G if r.decision.allowed else R
        print(f"  {c}[{r.decision.code.value}]{D} cart={rupees(r.decision.cart_total_paise)} "
              f"cap={rupees(r.decision.cap_paise)} headroom={rupees(r.decision.headroom_paise)}")
    for t in r.tools:
        tag = f"{R}BLOCKED{D}" if t.blocked else f"{G}CALLED {D}"
        print(f"  {tag} mcp:{t.name}")
    return r


def main() -> None:
    store.init_db()
    m = store.create_mandate(MandateCreate(cap_rupees=1000, blocked_categories=["gift_cards"]))
    print(f"{G}Mandate issued:{D} {m.id} — {rupees(m.cap_paise)} / {m.window.value}")

    print("\n--- ACT 1: conversational discovery (RAG) ---")
    say("I need supplies for a pasta dinner")

    print("\n--- ACT 2: the mandate breach attempt ---")
    say("Add the Parmigiano Reggiano and the olive oil, then check out")

    print("\n--- ACT 3: graceful recovery within the mandate ---")
    say("Remove the parmigiano")
    say("Checkout please")

    print("\n--- ACT 4: revocation latency ---")
    store.update_mandate(m.id, MandateUpdate(active=False))
    print(f"{R}Mandate revoked in the dashboard.{D}")
    say("Buy me some coffee beans")

    print(f"\n--- METRICS ---\n{store.metrics()}")


if __name__ == "__main__":
    main()
