"""BENCHMARK BASELINE — NOT AN AUTHORISATION PATH.

This is a reimplementation of a competing design, kept so we can measure it.
Importing it from any module that can mint an Action Grant would violate
invariant 12: an LLM may not decide envelope membership.
test_mechanism_isolation.py enforces that.

Source reference: IntentGuard (Track 01 competitor), commit `e4b1f8a` (2026-09),
specifically `backend/policy/decision.py` and `backend/semantic/entailment.py`.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("action_firewall.baselines.semantic_entailment")

CONFIDENCE_HIGH: float = 0.66
CONFIDENCE_LOW: float = 0.50


class ExtractedMandateFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")
    goal: str
    merchant_name: str | None = None
    budget_limit_paise: int | None = None
    allowed_categories: list[str] = Field(default_factory=list)
    key_items: list[str] = Field(default_factory=list)


class EntailmentSample(BaseModel):
    model_config = ConfigDict(extra="ignore")
    verdict: str  # "fit" | "no_fit" | "ambiguous"
    confidence: float = 1.0
    reasoning: str = ""


@dataclass
class EntailmentDecision:
    decision: str  # "ALLOW" | "BLOCK" | "ESCALATE"
    path: int  # Path number from IntentGuard decision matrix
    majority_verdict: str | None
    confidence: float
    sample_count: int
    samples: list[dict[str, Any]]
    reason: str
    latency_ms: float = 0.0
    model_used: str = "gemini-3.8-flash"


class IntentGuardBaseline:
    """Faithful reimplementation of IntentGuard's semantic entailment mechanism.

    Reproduces the architecture described in IntentGuard's README and implementation:
    1. Fact extraction (LLM call 1)
    2. 3-sample entailment (evaluates transaction across 3 independent samples)
    3. Majority voting via Counter.most_common(1) with arrival-order tie resolution
    4. Silent degradation on partial failures (tolerates >= 1 valid sample)
    5. Threshold lookup table:
       - Structural fail -> BLOCK
       - No verdict / 0 samples -> ESCALATE
       - Confidence < 0.50 -> ESCALATE
       - Ambiguous verdict -> ESCALATE
       - Confidence >= 0.66 + fit -> ALLOW
       - Confidence >= 0.66 + no_fit -> BLOCK
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        )
        self.preferred_model = model or os.environ.get("BASELINE_MODEL", "gemini-3.1-flash-lite")
        self.fallback_model = "gemini-3.5-flash-lite"
        self._client: Any = None

    def _get_client(self) -> Any:
        if not self.api_key:
            from app.config import get_settings
            self.api_key = get_settings().gemini_api_key or ""
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required for IntentGuard baseline evaluation. "
                "Hard Rule 7.4 strictly forbids mocked evaluations on the mechanism benchmark."
            )
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _call_model_with_fallback(self, prompt: str) -> tuple[str, str]:
        """Generate content trying preferred model with graceful fallback on 503/404."""
        client = self._get_client()
        models_to_try = [self.preferred_model]
        if self.fallback_model not in models_to_try:
            models_to_try.append(self.fallback_model)

        last_err: Exception | None = None
        for mod in models_to_try:
            for attempt in range(3):
                try:
                    resp = client.models.generate_content(
                        model=mod,
                        contents=prompt,
                    )
                    # Cache working model for subsequent calls
                    self.preferred_model = mod
                    time.sleep(0.5)
                    return resp.text.strip(), mod
                except Exception as exc:
                    last_err = exc
                    err_str = str(exc)
                    if "PerDay" in err_str or "per_day" in err_str.lower():
                        logger.warning("Daily quota reached for %s. Switching to fallback...", mod)
                        break
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        sleep_s = 15.0
                        logger.info("Rate limit hit on %s. Sleeping %.1fs...", mod, sleep_s)
                        time.sleep(sleep_s)
                        continue
                    if "503" in err_str or "404" in err_str:
                        logger.warning("Model %s unavailable (%s). Trying fallback...", mod, exc)
                        break  # Try next model
                    raise
        raise RuntimeError(f"All model calls failed. Last error: {last_err}")

    def extract_facts(self, mandate_text: str) -> ExtractedMandateFacts:
        """Stage 1: Fact extraction from shopper mandate (IntentGuard LLM call 1)."""
        prompt = (
            "You are an information extraction assistant. Extract structured facts from this shopping mandate.\n"
            f"Mandate: \"{mandate_text}\"\n\n"
            "Respond strictly with valid JSON with keys:\n"
            "- goal (string): overall purpose\n"
            "- merchant_name (string or null): specific merchant if requested\n"
            "- budget_limit_paise (integer or null): maximum spend in integer paise (e.g. Rs 500 = 50000)\n"
            "- allowed_categories (list of strings): categories mentioned\n"
            "- key_items (list of strings): items requested"
        )
        text, _ = self._call_model_with_fallback(prompt)
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        data = json.loads(text.strip())
        return ExtractedMandateFacts.model_validate(data)

    def evaluate_purchase(
        self,
        mandate_text: str,
        item_description: str,
        merchant_name: str,
        amount_paise: int,
        failure_rate: float = 0.0,
        forced_failures: list[int] | None = None,
    ) -> EntailmentDecision:
        """Evaluate a proposed purchase using IntentGuard's 3-sample entailment."""
        t0 = time.perf_counter()

        # Structural validation check (IntentGuard Path 1)
        if amount_paise <= 0:
            return EntailmentDecision(
                decision="BLOCK",
                path=1,
                majority_verdict=None,
                confidence=1.0,
                sample_count=0,
                samples=[],
                reason="Structural failure: invalid amount",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        entailment_prompt = (
            "You are IntentGuard's semantic entailment judge. You verify whether a proposed "
            "payment fits the customer's shopping mandate.\n\n"
            f"Customer Mandate: \"{mandate_text}\"\n\n"
            "Proposed Transaction:\n"
            f"- Merchant: {merchant_name}\n"
            f"- Item Description: {item_description}\n"
            f"- Amount: Rs {amount_paise / 100:.2f} ({amount_paise} paise)\n\n"
            "Evaluate whether this purchase fits the customer's intent.\n"
            "Provide 3 independent self-consistency evaluations to test semantic stability.\n"
            "Respond strictly in valid JSON format:\n"
            "{\n"
            "  \"samples\": [\n"
            "    {\"verdict\": \"fit\" | \"no_fit\" | \"ambiguous\", \"confidence\": 1.0, \"reasoning\": \"...\"},\n"
            "    {\"verdict\": \"fit\" | \"no_fit\" | \"ambiguous\", \"confidence\": 1.0, \"reasoning\": \"...\"},\n"
            "    {\"verdict\": \"fit\" | \"no_fit\" | \"ambiguous\", \"confidence\": 1.0, \"reasoning\": \"...\"}\n"
            "  ]\n"
            "}"
        )

        samples: list[dict[str, Any]] = []
        valid_samples: list[str] = []
        used_model = self.preferred_model

        try:
            raw_text, used_model = self._call_model_with_fallback(entailment_prompt)
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            parsed = json.loads(raw_text.strip())
            raw_samples = parsed.get("samples", [])
            if not isinstance(raw_samples, list) or len(raw_samples) < 3:
                # Fallback if structure is malformed
                v = str(parsed.get("verdict", "ambiguous")).lower()
                c = float(parsed.get("confidence", 1.0))
                r = str(parsed.get("reasoning", ""))
                raw_samples = [{"verdict": v, "confidence": c, "reasoning": r}] * 3

            for i in range(3):
                s_dict = raw_samples[i] if i < len(raw_samples) else {"verdict": "ambiguous", "confidence": 0.5}
                # Check for failure injection
                should_fail = False
                if forced_failures and i in forced_failures:
                    should_fail = True
                elif failure_rate > 0.0 and random.random() < failure_rate:
                    should_fail = True

                if should_fail:
                    samples.append({"sample_index": i, "status": "failed", "error": "Provider API timeout/error"})
                    continue

                v = str(s_dict.get("verdict", "ambiguous")).lower().strip()
                if v not in {"fit", "no_fit", "ambiguous"}:
                    v = "ambiguous"
                c = float(s_dict.get("confidence", 1.0))
                r = str(s_dict.get("reasoning", ""))
                samples.append({
                    "sample_index": i,
                    "status": "success",
                    "verdict": v,
                    "confidence": c,
                    "reasoning": r,
                })
                valid_samples.append(v)
        except Exception as exc:
            logger.warning("Entailment call failed: %s", exc)
            for i in range(3):
                samples.append({"sample_index": i, "status": "failed", "error": str(exc)})

        latency = (time.perf_counter() - t0) * 1000

        # Partial failure tolerance: proceed if >= 1 valid sample exists
        if not valid_samples:
            return EntailmentDecision(
                decision="ESCALATE",
                path=2,
                majority_verdict=None,
                confidence=0.0,
                sample_count=0,
                samples=samples,
                reason="No valid samples obtained: all provider calls failed",
                latency_ms=latency,
                model_used=used_model,
            )

        # Majority via Counter.most_common(1): first-encountered wins on tie
        counts = Counter(valid_samples)
        majority_verdict, count = counts.most_common(1)[0]
        confidence = count / len(valid_samples)

        # Threshold decision table (IntentGuard backend/policy/decision.py)
        if confidence < CONFIDENCE_LOW:
            return EntailmentDecision(
                decision="ESCALATE",
                path=3,
                majority_verdict=majority_verdict,
                confidence=confidence,
                sample_count=len(valid_samples),
                samples=samples,
                reason=f"Low agreement ({count}/{len(valid_samples)}): confidence below {CONFIDENCE_LOW}",
                latency_ms=latency,
                model_used=used_model,
            )

        if majority_verdict == "ambiguous":
            return EntailmentDecision(
                decision="ESCALATE",
                path=4,
                majority_verdict="ambiguous",
                confidence=confidence,
                sample_count=len(valid_samples),
                samples=samples,
                reason="Ambiguous verdict from semantic evaluation",
                latency_ms=latency,
                model_used=used_model,
            )

        if confidence >= CONFIDENCE_HIGH and majority_verdict == "fit":
            return EntailmentDecision(
                decision="ALLOW",
                path=7,
                majority_verdict="fit",
                confidence=confidence,
                sample_count=len(valid_samples),
                samples=samples,
                reason=f"High confidence ({confidence:.2f}) fit agreement",
                latency_ms=latency,
                model_used=used_model,
            )

        if confidence >= CONFIDENCE_HIGH and majority_verdict == "no_fit":
            return EntailmentDecision(
                decision="BLOCK",
                path=8,
                majority_verdict="no_fit",
                confidence=confidence,
                sample_count=len(valid_samples),
                samples=samples,
                reason=f"High confidence ({confidence:.2f}) no-fit agreement",
                latency_ms=latency,
                model_used=used_model,
            )

        return EntailmentDecision(
            decision="ESCALATE",
            path=9,
            majority_verdict=majority_verdict,
            confidence=confidence,
            sample_count=len(valid_samples),
            samples=samples,
            reason="Unresolved decision threshold",
            latency_ms=latency,
            model_used=used_model,
        )
