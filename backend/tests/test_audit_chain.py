"""The audit trail must make tampering detectable, not merely inconvenient.

audit_log already carries BEFORE UPDATE / DELETE / overwrite triggers. Those
defend the table against this application's own connections and they are worth
having. They are not tamper evidence: anyone holding the .db file can drop a
trigger, edit a row, recreate the trigger, and nothing in the table disagrees
with them. Every test below does exactly that — drops the guard, edits, puts it
back — because that is the actual threat, and a chain that only survives attacks
the database already blocks proves nothing.

What the chain buys: an edit anywhere forces recomputation of every entry after
it. What it does not buy: anything about entries written before the chain
existed. `verify_audit_chain` says so in its own output, and
`test_the_caveat_is_published` holds it to that.
"""
import os
import sqlite3
import tempfile

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "chain.db")
os.environ["DEMO_MODE"] = "true"
os.environ["OPENAI_API_KEY"] = ""

from app import store  # noqa: E402
from app.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chain.db"))
    get_settings.cache_clear()
    store.init_db()
    yield
    get_settings.cache_clear()


def write(n: int, prefix: str = "EVENT") -> None:
    for i in range(n):
        store.log_event(
            event=f"{prefix}_{i}",
            session_id="session_chain",
            code="OK",
            cart_total_paise=100 * (i + 1),
            payload={"i": i},
        )


def raw():
    """A connection with the append-only guards stood down — i.e. an attacker
    with the file, which is the only interesting adversary here."""
    cx = sqlite3.connect(get_settings().db_path)
    cx.row_factory = sqlite3.Row
    cx.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
    cx.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
    cx.execute("DROP TRIGGER IF EXISTS audit_log_no_overwrite")
    return cx


# ---------------------------------------------------------------------------
# It holds when nothing has happened to it
# ---------------------------------------------------------------------------
def test_an_untouched_chain_verifies():
    write(6)
    result = store.verify_audit_chain()
    assert result["valid"] is True
    assert result["entries"] == 6
    assert result["first_broken_seq"] is None
    assert result["head_hash"] and result["head_hash"] != result["genesis"]


def test_an_empty_chain_verifies_against_genesis():
    """Length zero is a valid chain. A verifier that only works once there is
    data would report its first real failure as indistinguishable from startup."""
    result = store.verify_audit_chain()
    assert result["valid"] is True
    assert result["entries"] == 0
    assert result["head_hash"] == result["genesis"]


def test_the_head_moves_with_every_entry():
    write(1)
    first = store.verify_audit_chain()["head_hash"]
    write(1, prefix="LATER")
    assert store.verify_audit_chain()["head_hash"] != first


# ---------------------------------------------------------------------------
# It breaks when something has
# ---------------------------------------------------------------------------
def test_editing_an_entry_breaks_the_chain_at_that_entry():
    write(5)
    cx = raw()
    target = cx.execute("SELECT id, seq FROM audit_log ORDER BY seq LIMIT 1 OFFSET 2").fetchone()
    cx.execute("UPDATE audit_log SET code=? WHERE id=?", ("TAMPERED", target["id"]))
    cx.commit()
    cx.close()

    result = store.verify_audit_chain()
    assert result["valid"] is False
    assert result["first_broken_seq"] == target["seq"]
    assert result["broken_entry_id"] == target["id"]
    assert "edited" in result["reason"]


def test_changing_the_payload_alone_breaks_the_chain():
    """The digest covers every stored column. A field left out of it is a field
    an editor may change for free — which is how a chain ends up proving less
    than its presence suggests."""
    write(3)
    cx = raw()
    target = cx.execute("SELECT id, seq FROM audit_log ORDER BY seq LIMIT 1").fetchone()
    cx.execute('UPDATE audit_log SET payload=? WHERE id=?', ('{"i": 999}', target["id"]))
    cx.commit()
    cx.close()
    assert store.verify_audit_chain()["first_broken_seq"] == target["seq"]


def test_changing_the_amount_alone_breaks_the_chain():
    write(3)
    cx = raw()
    target = cx.execute("SELECT id, seq FROM audit_log ORDER BY seq LIMIT 1 OFFSET 1").fetchone()
    cx.execute("UPDATE audit_log SET cart_total_paise=1 WHERE id=?", (target["id"],))
    cx.commit()
    cx.close()
    assert store.verify_audit_chain()["valid"] is False


def test_deleting_an_entry_is_detected_as_a_gap():
    write(5)
    cx = raw()
    target = cx.execute("SELECT id, seq FROM audit_log ORDER BY seq LIMIT 1 OFFSET 2").fetchone()
    cx.execute("DELETE FROM audit_log WHERE id=?", (target["id"],))
    cx.commit()
    cx.close()

    result = store.verify_audit_chain()
    assert result["valid"] is False
    assert result["first_broken_seq"] == target["seq"]
    assert "missing" in result["reason"]


def test_truncating_the_tail_is_the_one_edit_a_chain_cannot_see():
    """Honest limit, asserted rather than hoped for. Removing entries from the
    END leaves a shorter chain that is internally perfect. Only someone who
    recorded the earlier head_hash can tell. This test exists so nobody reads
    the green tick as 'nothing was removed'."""
    write(5)
    head_before = store.verify_audit_chain()["head_hash"]

    cx = raw()
    cx.execute("DELETE FROM audit_log WHERE seq >= 4")
    cx.commit()
    cx.close()

    after = store.verify_audit_chain()
    assert after["valid"] is True, "a truncated chain still verifies — that is the limit"
    assert after["entries"] == 3
    assert after["head_hash"] != head_before, (
        "the head must move, because publishing it is the only defence against this"
    )


# ---------------------------------------------------------------------------
# It survives the way this system actually writes
# ---------------------------------------------------------------------------
def test_concurrent_writers_produce_one_chain_not_two():
    """Two writers reading the same tail would fork: two entries, same
    prev_hash, both plausible. UNIQUE(seq) makes the loser retry instead."""
    import threading

    errors: list[Exception] = []

    def writer(n: int):
        try:
            for i in range(10):
                store.log_event(event=f"T{n}_{i}", session_id=f"s{n}", payload={"n": n, "i": i})
        except Exception as exc:  # pragma: no cover - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"writers failed: {errors}"
    result = store.verify_audit_chain()
    assert result["valid"] is True
    assert result["entries"] == 40, "every write must be in the chain exactly once"


def test_entries_written_through_the_normal_path_are_chained():
    """log_event is not the only writer — _insert_audit_row is called from
    inside other transactions too. If those bypassed the chain the trail would
    be half-linked and the verifier would still say valid."""
    write(2)
    with store._conn() as cx:
        store._insert_audit_row(cx, event="INNER_TRANSACTION", session_id="s1")
    result = store.verify_audit_chain()
    assert result["valid"] is True
    assert result["entries"] == 3
    assert result["unchained_legacy_entries"] == 0


# ---------------------------------------------------------------------------
# It says what it does not prove
# ---------------------------------------------------------------------------
def test_the_caveat_is_published():
    write(2)
    result = store.verify_audit_chain()
    caveat = result["caveat"].lower()
    assert "retroactively" in caveat
    assert "head_hash" in caveat
    assert result["unchained_legacy_entries"] == 0


def test_a_pre_chain_database_is_linked_and_counted_honestly():
    """A database written before the chain existed gets linked at migration.
    Those hashes are computed from the rows as they then stood, so they prove
    nothing about earlier edits. The migration must still leave the chain
    complete and verifiable rather than half-populated."""
    write(3)
    cx = raw()
    cx.execute("UPDATE audit_log SET seq=NULL, prev_hash=NULL, entry_hash=NULL")
    cx.commit()
    cx.close()

    assert store.verify_audit_chain()["unchained_legacy_entries"] == 3
    store.init_db()  # re-run migration
    result = store.verify_audit_chain()
    assert result["valid"] is True
    assert result["entries"] == 3
    assert result["unchained_legacy_entries"] == 0
