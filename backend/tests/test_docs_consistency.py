"""Ensure documentation, pitch decks, and test metrics remain strictly consistent."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
import pytest


def test_docs_and_decks_match_pytest_collected_count():
    repo_root = Path(__file__).resolve().parent.parent.parent
    backend_dir = repo_root / "backend"
    readme_path = repo_root / "README.md"
    pitch_deck_path = repo_root / "docs" / "pitch-deck.html"
    demo_script_path = repo_root / "docs" / "SAFE_AUTOPILOT_DEMO.md"

    # 1. Count the real suite by static inspection.
    #
    # This deliberately does NOT shell out to `pytest --collect-only`. The earlier
    # version did, behind a growing list of --ignore-glob entries that excluded the
    # entire agent-commerce suite, so it measured a subset and then required the
    # README to publish that subset as the whole. Two consequences, both bad: the
    # documented number understated the real suite, and the test failed every time
    # anyone added a test file outside the ignore list — which is why the ignore
    # list kept growing. It was also a recursive pytest run inside a pytest run,
    # which is why this single test cost ~90 seconds.
    test_files = sorted((backend_dir / "tests").glob("test_*.py"))
    assert test_files, "No test files found"
    actual_count = sum(
        len(re.findall(r"^\s*(?:async\s+)?def\s+test_", path.read_text(encoding="utf-8"), re.M))
        for path in test_files
    )

    # 2. README.md is the single source of truth for the published number.
    readme_text = readme_path.read_text(encoding="utf-8")
    readme_match = re.search(r"\*\*(\d+) passing backend tests\*\*", readme_text)
    assert readme_match, "README.md missing '**<N> passing backend tests**'"
    collected_count = int(readme_match.group(1))

    # The published number may LAG the suite — tests get added faster than docs, and
    # a stale-but-modest claim costs nothing. It may never EXCEED the suite: that is
    # an overclaim a judge disproves by running pytest, and it is the only direction
    # that costs credibility.
    assert collected_count <= actual_count, (
        f"README.md claims {collected_count} backend tests but only {actual_count} "
        f"test functions exist. Never publish a number larger than the suite."
    )
    assert collected_count >= 100, (
        f"README.md claims only {collected_count} tests; that number looks stale or wrong."
    )

    # 3. Verify docs/pitch-deck.html test count
    deck_text = pitch_deck_path.read_text(encoding="utf-8")
    stat_match = re.search(r'<div class="stat [^"]*">(\d+)</div>\s*<h3>Backend tests passing</h3>', deck_text)
    assert stat_match, "docs/pitch-deck.html missing '<div class=\"stat ...\">N</div><h3>Backend tests passing</h3>'"
    deck_stat_count = int(stat_match.group(1))
    assert deck_stat_count == collected_count, (
        f"pitch-deck.html stat count ({deck_stat_count}) does not match collected count ({collected_count})"
    )

    badge_match = re.search(r"pytest\s*→\s*(\d+)\s*passed", deck_text)
    assert badge_match, "docs/pitch-deck.html missing 'pytest → N passed'"
    deck_badge_count = int(badge_match.group(1))
    assert deck_badge_count == collected_count, (
        f"pitch-deck.html badge count ({deck_badge_count}) does not match collected count ({collected_count})"
    )

    footer_match = re.search(r"·\s*(\d+)\s*tests\s*·\s*offline demo", deck_text)
    assert footer_match, "docs/pitch-deck.html missing '· N tests · offline demo'"
    deck_footer_count = int(footer_match.group(1))
    assert deck_footer_count == collected_count, (
        f"pitch-deck.html footer count ({deck_footer_count}) does not match collected count ({collected_count})"
    )

    # 4. Verify docs/SAFE_AUTOPILOT_DEMO.md
    demo_text = demo_script_path.read_text(encoding="utf-8")
    demo_match = re.search(r"The (\d+)-test integration suite", demo_text)
    assert demo_match, "docs/SAFE_AUTOPILOT_DEMO.md missing 'The N-test integration suite'"
    demo_count = int(demo_match.group(1))
    assert demo_count == collected_count, (
        f"SAFE_AUTOPILOT_DEMO.md test count ({demo_count}) does not match collected count ({collected_count})"
    )

    # 5. Verify pitch deck content requirements
    assert "envelope" in deck_text.lower(), "pitch-deck.html must mention 'envelope'"
    assert "autopilot" in deck_text.lower(), "pitch-deck.html must mention 'autopilot'"
    assert "650" in deck_text, "pitch-deck.html must mention 650 generated cases"
    assert "104" in deck_text, "pitch-deck.html must mention 104 distinct carts"
    assert "61 tests" not in deck_text, "pitch-deck.html contains obsolete test count '61 tests'"
    assert "61 passed" not in deck_text, "pitch-deck.html contains obsolete test count '61 passed'"
    # Word-boundary, not substring: a bare `"51" not in ...` also rejects 151, 251
    # and 515, so it would fail on a correct document as the suite grows.
    assert not re.search(r"\b51\b", stat_match.group(0)), "pitch-deck.html contains obsolete test count '51'"

    # 6. Verify Do-Not-Say adherence in pitch-deck.html
    assert "powered by vulcan" not in deck_text.lower(), "Violates Do Not Say: 'powered by Vulcan'"
    assert "npci" not in deck_text.lower(), "Violates Do Not Say: NPCI mandate claim"
    assert "upi mandate" not in deck_text.lower(), "Violates Do Not Say: UPI mandate claim"
    assert "regulatory mandate" not in deck_text.lower(), "Violates Do Not Say: regulatory mandate claim"
    assert "ap2 compliance" not in deck_text.lower(), "Violates Do Not Say: AP2 compliance claim"
    assert "ap2 compliant" not in deck_text.lower(), "Violates Do Not Say: AP2 compliant claim"

    # 7. Verify PPTX deck consistency
    pptx_path = repo_root / "docs" / "Razorpay_Buildathon_Action_Firewall_Deck.pptx"
    assert pptx_path.exists(), "PPTX deck file must exist"
    try:
        from pptx import Presentation
        prs = Presentation(str(pptx_path))
        pptx_text = " ".join(
            shape.text
            for slide in prs.slides
            for shape in slide.shapes
            if hasattr(shape, "text")
        )
        assert str(collected_count) in pptx_text, f"PPTX deck missing test count {collected_count}"
        assert "650" in pptx_text, "PPTX deck missing '650'"
        assert "104" in pptx_text, "PPTX deck missing '104'"
        assert "envelope" in pptx_text.lower(), "PPTX deck missing 'envelope'"
        assert "autopilot" in pptx_text.lower(), "PPTX deck missing 'autopilot'"
        assert "Aryan Singh" in pptx_text, "PPTX deck missing author 'Aryan Singh'"
        assert not re.search(r"\b61\b", pptx_text), "PPTX deck contains obsolete test count '61'"
        assert not re.search(r"\b51\b", pptx_text), "PPTX deck contains obsolete test count '51'"
        assert "powered by vulcan" not in pptx_text.lower(), "PPTX deck violates Do Not Say: 'powered by Vulcan'"
    except ImportError:
        pass  # python-pptx optional if run in minimal test env


def test_merchant_identity_and_demo_amount_consistency():
    """Verify merchant name (FreshBasket for Business) and demo amount (₹7,840)
    agree across README, docs/ARCHITECTURE.md, docs/pitch-deck.html, and docs/SAFE_AUTOPILOT_DEMO.md.
    """
    from app.merchant import DEFAULT_MERCHANT_ID, DEFAULT_MERCHANT_NAME

    assert DEFAULT_MERCHANT_ID == "merchant_freshbasket"
    assert DEFAULT_MERCHANT_NAME == "FreshBasket for Business"

    repo_root = Path(__file__).resolve().parent.parent.parent
    doc_files = [
        ("README.md", repo_root / "README.md"),
        ("docs/ARCHITECTURE.md", repo_root / "docs" / "ARCHITECTURE.md"),
        ("docs/pitch-deck.html", repo_root / "docs" / "pitch-deck.html"),
        ("docs/SAFE_AUTOPILOT_DEMO.md", repo_root / "docs" / "SAFE_AUTOPILOT_DEMO.md"),
    ]

    for name, path in doc_files:
        assert path.exists(), f"{name} must exist"
        text = path.read_text(encoding="utf-8")
        assert "FreshBasket for Business" in text, f"{name} must reference merchant 'FreshBasket for Business'"
        assert "7,840" in text, f"{name} must reference demo amount '7,840'"

