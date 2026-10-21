from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

from pipeline.runtime_config import get_config, has_vision_model_config


SPECIFIC_ACTION_RE = re.compile(
    r"\b(click|type|enter|press|save|post|submit|delete|approve)\b",
    re.I,
)
EXACT_VALUE_RE = re.compile(r"\b\d{4,}|\$?\d+\.\d{2}\b")

ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def _encode_image(path: str) -> str:
    """Resize and encode an evidence screenshot for Ollama vision inference."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((960, 540))

            buffer = BytesIO()
            image.save(
                buffer,
                format="JPEG",
                quality=76,
                optimize=True,
            )
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

    except Exception:
        # Fallback for image formats PIL cannot process.
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("utf-8")


def _sanitize_risky_text(text: str) -> str:
    """Conservatively remove potentially unsupported exact values."""
    text = EXACT_VALUE_RE.sub("the visible value", text)
    text = re.sub(r"\b[Cc]lick\b", "Select", text)
    text = re.sub(r"\b[Tt]ype\b", "Enter", text)
    return re.sub(r"\s+", " ", text).strip()


def mark_risks(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag SOP steps that need evidence-aware verification."""
    marked = []

    for step in steps:
        text = f"{step.get('action', '')} {step.get('expected_output', '')}"

        risky = (
            step.get("confidence") != "high"
            or bool(SPECIFIC_ACTION_RE.search(text))
            or bool(EXACT_VALUE_RE.search(text))
            or bool(step.get("coverage_review_required"))
            or (
                step.get("rule_system")
                and step.get("system")
                and step.get("rule_system") != "Other"
                and step.get("system") != step.get("rule_system")
            )
        )

        marked.append({**step, "risky": risky})

    return marked


def _extract_json(text: str) -> list[dict[str, Any]]:
    """Parse a JSON array from the verification model response."""
    if not text:
        raise ValueError("Empty Ollama verification response")

    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()

    match = re.search(r"\[[\s\S]*\]", stripped)
    payload = match.group(0) if match else stripped

    data = json.loads(payload)

    if not isinstance(data, list):
        raise ValueError("Verification response is not a JSON array")

    return [item for item in data if isinstance(item, dict)]


def _ollama_chat_url() -> str:
    """Resolve the native Ollama chat endpoint from runtime configuration."""
    base_url = (
        get_config("OLLAMA_BASE_URL", "http://localhost:11434")
        or "http://localhost:11434"
    ).strip().rstrip("/")

    # Accept a server root or a URL ending in /v1 or /api.
    for suffix in ("/v1", "/api"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)].rstrip("/")
            break

    return f"{base_url}/api/chat"


def _call_ollama_chat(
    messages: list[dict[str, Any]],
    model: str,
) -> str:
    """Call Ollama's native chat API using the Python standard library."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }

    request = urllib.request.Request(
        _ollama_chat_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    timeout = min(
        35.0,
        float(get_config("OLLAMA_TIMEOUT", "180") or "180"),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"Ollama returned HTTP {exc.code}: {details}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not connect to Ollama at {_ollama_chat_url()}: {exc}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError("Ollama verification request timed out") from exc

    message = result.get("message", {})
    content = message.get("content", "") if isinstance(message, dict) else ""

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned an empty verification message")

    return content


def _call_verify(
    risky_steps: list[dict[str, Any]],
    model: str,
) -> list[dict[str, Any]]:
    """Verify risky SOP steps using local Ollama vision reasoning."""
    payload = [
        {
            "event_id": step["event_id"],
            "system": step.get("system", "Other"),
            "action": step.get("action", ""),
            "expected_output": step.get("expected_output", ""),
            "confidence": step.get("confidence", "low"),
            "ocr": (step.get("ocr") or "")[:900],
            "coverage_review_required": bool(
                step.get("coverage_review_required")
            ),
            "possible_missing_operation": bool(
                step.get("possible_missing_operation")
            ),
            "action_hint": step.get("action_hint"),
        }
        for step in risky_steps
    ]

    prompt = """You verify and conservatively improve business SOP steps.

Rules:
- Treat the supplied OCR, screenshots, and existing step as evidence, not proof.
- Preserve every supplied event_id exactly. Return one object for every input event_id.
- Do not merge, omit, duplicate, or reorder event IDs.
- Remove exact values unless the evidence clearly establishes that they are field labels or essential visible identifiers.
- Do not invent clicks, saves, postings, names, numbers, or outcomes.
- Do not claim an action happened merely because its expected result would be useful.
- Downgrade confidence when the evidence is weak, ambiguous, or incomplete.
- Prefer concise, actionable business process language over generic descriptions.
- If coverage_review_required is true and the evidence suggests a dialog, configuration pane, chart, slicer, filter, or calculation change, prefer a conservative event-specific operational step over a generic review step.
- Preserve the supplied system label unless the evidence clearly supports another system.
- If the available evidence cannot establish a more specific action, keep the existing action conservative rather than hallucinating details.
- Return only a JSON array. Do not use Markdown fences.
- Each object must contain exactly these fields:
  event_id, system, action, expected_output, confidence
- confidence must be high, medium, or low.
"""

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                prompt
                + "\n\nSteps requiring verification:\n"
                + json.dumps(payload, ensure_ascii=False)
                + "\n\nScreenshots may follow as separate image messages. "
                "Associate each screenshot with its stated event_id."
            ),
        }
    ]

    for step in risky_steps:
        screenshot = step.get("screenshot")

        if not screenshot or not Path(screenshot).is_file():
            continue

        try:
            encoded_image = _encode_image(screenshot)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Evidence screenshot for event_id "
                        f"{step['event_id']}. Use it only as supporting "
                        "evidence for that event; do not assume an action "
                        "occurred unless the evidence supports it."
                    ),
                    "images": [encoded_image],
                }
            )
        except (OSError, ValueError):
            # Continue with textual evidence if image loading fails.
            continue

    response_text = _call_ollama_chat(messages, model)
    return _extract_json(response_text)


def _sanitize_fallback(
    marked: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Safe fallback when model verification is unavailable."""
    result = []

    for step in marked:
        updated = dict(step)

        if step.get("risky"):
            updated["action"] = _sanitize_risky_text(
                step.get("action", "")
            )
            updated["expected_output"] = _sanitize_risky_text(
                step.get("expected_output", "")
            )

            if step.get("confidence") == "high":
                updated["confidence"] = "medium"

            updated["verified"] = False

        result.append(updated)

    return result


def verify_steps(
    steps: list[dict[str, Any]],
    model: str | None = None,
    max_risky: int = 24,
) -> list[dict[str, Any]]:
    """
    Verify risky SOP steps while preserving the pipeline's step contract.

    Non-risky steps remain unchanged. If Ollama is unavailable or verification
    fails, conservative local sanitization is used instead of stopping the
    SOP generation pipeline.
    """
    marked = mark_risks(steps)
    risky = [step for step in marked if step.get("risky")]

    if not risky:
        return marked

    if not has_vision_model_config():
        return _sanitize_fallback(marked)

    model = (
        model
        or get_config("OLLAMA_MODEL", "qwen3-vl:4b")
        or "qwen3-vl:4b"
    )

    risky = risky[: max(0, max_risky)]

    if not risky:
        return marked

    verified: list[dict[str, Any]] | None = None

    for attempt in range(1):
        try:
            verified = _call_verify(risky, model)
            break
        except Exception:
            if attempt == 0:
                time.sleep(1)

    if verified is None:
        return _sanitize_fallback(marked)

    # Only accept responses for event IDs that were actually sent.
    allowed_ids = set()

    for step in risky:
        try:
            allowed_ids.add(int(step["event_id"]))
        except (KeyError, TypeError, ValueError):
            continue

    updates: dict[int, dict[str, Any]] = {}

    for item in verified:
        event_id = item.get("event_id")

        if not str(event_id).isdigit():
            continue

        event_id = int(event_id)

        if event_id not in allowed_ids:
            continue

        # Keep the first valid response for each event.
        if event_id not in updates:
            updates[event_id] = item

    out = []

    for step in marked:
        updated = dict(step)

        try:
            event_id = int(step["event_id"])
        except (KeyError, TypeError, ValueError):
            out.append(updated)
            continue

        update = updates.get(event_id)

        if update:
            confidence = update.get("confidence")

            updated.update(
                {
                    "system": update.get("system") or step.get("system"),
                    "action": update.get("action") or step.get("action"),
                    "expected_output": (
                        update.get("expected_output")
                        or step.get("expected_output")
                    ),
                    "confidence": (
                        confidence
                        if confidence in ALLOWED_CONFIDENCE
                        else step.get("confidence")
                    ),
                    "verified": True,
                }
            )
        elif step.get("risky"):
            # The model may return malformed or incomplete event coverage.
            updated["verified"] = False

        if step.get("risky"):
            updated["action"] = _sanitize_risky_text(
                updated.get("action", "")
            )
            updated["expected_output"] = _sanitize_risky_text(
                updated.get("expected_output", "")
            )

        out.append(updated)

    return out
