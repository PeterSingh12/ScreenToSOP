from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline.runtime_config import get_config, has_vision_model_config


GENERATION_PROMPT = """You generate business SOP steps from segmented screen-recording evidence.

Rules:
- Return a JSON array containing exactly one object for every input event_id.
- Do not skip, duplicate, merge, or invent event_ids.
- Treat one event_id as one possible SOP step produced by the segmentation engine.
- If an event spans a long configuration sequence, describe the most specific visible action for that event, not the whole sequence.
- If a screenshot shows a dialog, pane, field configuration area, chart setup, slicer setup, or calculation setup that changes workflow state, describe that configuration action explicitly.
- Do not compress a measure-add action and a rename action unless the evidence clearly shows one combined operation.
- Prefer separate event-specific steps for adding a measure, changing a calculation, showing values as a percentage, renaming a field, inserting a chart, inserting a slicer, and applying a slicer selection when these appear across distinct events.
- Do not hallucinate clicks, typed values, names, or outcomes.
- Only describe what is supported by the screenshots and OCR.
- Use stable_frame evidence first; before/after frames provide context only.
- If uncertain, use a conservative, event-specific action rather than inventing details.
- If an event appears operational but uncertain, produce a conservative step instead of repeatedly saying "Review the visible process screen."
- Use business process language, not toolbar or menu noise.
- Keep each action concise and usable by a new employee.
- Use the system label supplied with each event unless the evidence clearly supports another allowed label.
- Return only valid JSON. Do not wrap the output in Markdown fences.
- Use exactly this schema:
[
  {
    "event_id": 1,
    "system": "SAP|Excel|Email|Slack/Teams|Browser|PDF|File Explorer|Other",
    "action": "A concise, evidence-grounded action",
    "expected_output": "The observable result supported by the evidence",
    "confidence": "high|medium|low"
  }
]
"""

ALLOWED_CONFIDENCE = {"high", "medium", "low"}

GENERIC_REVIEW_SIGNATURES = {
    "review the visible process screen",
    "review the process state shown",
    "review the process screen shown",
}

KEY_TERM_RE = re.compile(
    r"\b(pivottable|pivot\s+table|pivotchart|pivot\s+chart|slicer|field|fields|row|rows|column|columns|value|values|measure|percentage|sum|maximum|chart|filter|dialog|table|worksheet|export|submit|save)\b",
    re.I,
)


def _encode_image(path: str) -> str:
    """Encode a resized screenshot as JPEG for the local vision model."""
    try:
        from io import BytesIO
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((960, 540))
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=76, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception:
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("utf-8")


def _extract_json(text: str) -> list[dict[str, Any]]:
    """Extract a JSON array from model output."""
    if not text:
        raise ValueError("Empty Ollama model output")

    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()

    match = re.search(r"\[[\s\S]*\]", stripped)
    payload = match.group(0) if match else stripped
    data = json.loads(payload)

    if not isinstance(data, list):
        raise ValueError("Model output is not a JSON array")

    return [item for item in data if isinstance(item, dict)]




def _image_parts_for_event(
    event: dict[str, Any],
    include_context_images: bool,
) -> list[tuple[str, str]]:
    """Use one primary screenshot per event to control context size."""
    candidates = [
        event.get("evidence_frame"),
        event.get("path"),
        event.get("screenshot"),
    ]

    seen: set[str] = set()

    for path in candidates:
        if path and path not in seen and Path(path).is_file():
            seen.add(path)
            return [("evidence_frame", path)]

    return []



def _ollama_chat_endpoint() -> str:
    """Build Ollama's native chat endpoint from the configured base URL."""
    base_url = (
        get_config("OLLAMA_BASE_URL", "http://localhost:11434")
        or "http://localhost:11434"
    ).strip().rstrip("/")

    # Accept the server root or a base URL ending in /v1 or /api.
    if base_url.endswith("/v1"):
        base_url = base_url[:-3].rstrip("/")
    if base_url.endswith("/api"):
        base_url = base_url[:-4].rstrip("/")

    return f"{base_url}/api/chat"


def _call_ollama(
    events: list[dict[str, Any]],
    model: str,
    include_context_images: bool,
    max_retries: int = 1,
) -> list[dict[str, Any]]:
    """Generate event-specific SOP steps using Ollama's native API."""
    compact_events: list[dict[str, Any]] = []
    image_payloads: list[str] = []
    image_descriptions: list[str] = []

    for index, event in enumerate(events):
        previous_event = events[index - 1] if index > 0 else {}
        next_event = events[index + 1] if index + 1 < len(events) else {}

        start_time = float(
            event.get("start_time_sec", event.get("time_sec", 0)) or 0
        )
        end_time = float(
            event.get("end_time_sec", event.get("time_sec", 0)) or 0
        )
        event_text = event.get("clean_text") or ""

        compact_events.append(
            {
                "event_id": event["event_id"],
                "start_time_sec": round(start_time, 1),
                "end_time_sec": round(end_time, 1),
                "system_rule_guess": event.get("system", "Other"),
                "previous_system_rule_guess": previous_event.get("system"),
                "next_system_rule_guess": next_event.get("system"),
                "action_hint": event.get("action_hint", "review"),
                "diff_score": round(float(event.get("diff_score", 0) or 0), 4),
                "boundary_score": round(
                    float(event.get("boundary_score", 0) or 0), 4
                ),
                "screen_state_id": event.get("screen_state_id"),
                "previous_screen_state_id": previous_event.get("screen_state_id"),
                "next_screen_state_id": next_event.get("screen_state_id"),
                "ocr": event_text[:1200],
                "duration_seconds": round(end_time - start_time, 1),
                "forced_split": bool(event.get("forced_split")),
                "ocr_key_terms": sorted(
                    {
                        match.group(0).lower()
                        for match in KEY_TERM_RE.finditer(event_text)
                    }
                )[:18],
                "phase_intent_guess": event.get("phase_intent_guess"),
                "evidence_selection_reason": event.get(
                    "evidence_selection_reason"
                ),
                "previous_ocr": "",
                "next_ocr": "",
                "dense_repeated_run": bool(event.get("dense_repeated_run")),
                "ocr_blank": not bool(event_text.strip()),
            }
        )

        for image_role, image_path in _image_parts_for_event(
            event, include_context_images
        ):
            try:
                image_payload = _encode_image(image_path)
            except Exception:
                continue

            image_payloads.append(image_payload)
            image_descriptions.append(
                f"Image {len(image_payloads)} is the {image_role} screenshot "
                f"for event_id {event['event_id']}."
            )

    user_content = (
        "Convert the following segmented screen-recording events into SOP steps.\n"
        "Return one step for every supplied event_id, preserving IDs exactly.\n\n"
        "Events:\n"
        + json.dumps(compact_events, ensure_ascii=False)
    )

    if image_descriptions:
        user_content += (
            "\n\nScreenshots are attached in the same order:\n"
            + "\n".join(image_descriptions)
        )

    user_message: dict[str, Any] = {
        "role": "user",
        "content": user_content,
    }
    if image_payloads:
        user_message["images"] = image_payloads

    
    
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": GENERATION_PROMPT},
            user_message,
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
            "num_ctx": 16384,
            "num_predict": 2048,
        },
    }



    endpoint = _ollama_chat_endpoint()
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            payload = json.dumps(request_body).encode("utf-8")
            request = Request(
                endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urlopen(request, timeout=180) as response:
                response_data = json.loads(response.read().decode("utf-8"))

            
            model_message = response_data.get("message") or {}
            generated_text = model_message.get("content") or ""

            if not generated_text.strip():
                raise ValueError(
                    "Ollama returned empty content. "
                    f"Response keys: {list(response_data.keys())}; "
                    f"message: {json.dumps(model_message, ensure_ascii=False)[:2000]}; "
                    f"done_reason: {response_data.get('done_reason')}; "
                    f"prompt_eval_count: {response_data.get('prompt_eval_count')}; "
                    f"eval_count: {response_data.get('eval_count')}"
                )

            generated = _extract_json(generated_text)


            if not generated:
                raise ValueError("Ollama returned no valid SOP step objects")

            return generated

        
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(
                f"HTTP {exc.code}: {error_body}"
            )
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))

        except (
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
        ) as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))


    raise RuntimeError(f"Ollama generation failed: {last_error}")


def _fallback_action(
    event: dict[str, Any],
    ollama_failed: bool = False,
) -> dict[str, Any]:
    """Produce a conservative local fallback when model generation fails."""
    system = event.get("system") or "Other"
    text = (event.get("clean_text") or "").lower()
    hint = event.get("action_hint", "")
    event_id = int(event.get("event_id", 0) or 0)
    state = event.get("screen_state_id")

    generation_source = "local_ocr" if text.strip() else "diagnostic_fallback"
    diagnostic_only = generation_source == "diagnostic_fallback"

    if "validate exported" in text or (
        "exported file" in text and ("ready" in text or "appears" in text)
    ):
        action = "Validate that the exported file is available."
        expected = "The exported file is visible and ready for review."

    elif hint == "export" or "export" in text or "download" in text:
        action = "Export the displayed data."
        expected = "The data export is prepared or completed."

    elif "submit" in text and ("confirmation" in text or "saved" in text):
        action = "Submit the visible update and review the confirmation."
        expected = "The system confirms that the update was saved."

    elif "update" in text and any(
        term in text for term in ["field", "terms", "priority", "status", "owner"]
    ):
        action = "Update the visible process fields."
        expected = "The visible fields reflect the required changes."

    elif hint == "filter" or "filter" in text:
        action = "Apply or review the visible filter criteria."
        expected = "The filtered results are displayed for review."

    elif any(
        term in text
        for term in [
            "create a new repository",
            "new repository",
            "repository name",
            "repository visibility",
            "initialize this repository",
        ]
    ):
        action = "Configure the repository details shown on the creation form."
        expected = "The repository configuration form displays the selected details."
    
    elif "quick setup" in text or "getting started" in text:
        action = "Review the newly created repository's setup page."
        expected = "The repository page displays its setup instructions."

    elif "github" in text and "repository" in text and (
        "create" in text or "new" in text
    ):
        action = "Open the GitHub repository creation workflow."
        expected = "The repository creation form is displayed."

    elif hint == "data entry" and text.strip():
        action = "Review the visible fields and their OCR-recognized labels."
        expected = "The captured screen provides field labels for manual verification."

    elif hint == "post/save" or "save" in text or "post" in text:
        action = "Save or post the visible transaction after review."
        expected = "The system records the transaction status."

    elif "invoice" in text or "supplier" in text or "vendor" in text:
        action = "Review the visible invoice or supplier details."
        expected = "The required business details are visible for validation."

    elif system == "Excel":
        if any(term in text for term in ["pivot", "field", "measure"]):
            action = "Review or configure the visible Excel analysis element."
            expected = (
                "The Excel worksheet or analysis view reflects "
                "the visible configuration change."
            )
        else:
            action = "Review or update the visible spreadsheet data."
            expected = "The spreadsheet shows the relevant working data."

    elif system == "SAP":
        action = "Open or review the visible SAP transaction screen."
        expected = "The SAP screen displays the relevant process information."

    elif hint == "navigation":
        action = "Open or navigate to the visible process area."
        expected = "The next process screen is available for review."

    elif state is not None:
        action = f"Review the process state shown at event {event_id}."
        expected = f"Screen state {state} is visible for the next workflow action."

    else:
        action = f"Review the visible process screen for event {event_id}."
        expected = (
            "The relevant process information is available "
            "for chronological review."
        )

    return {
        "event_id": event["event_id"],
        "system": system,
        "action": action,
        "expected_output": expected,
        "confidence": "low" if not event.get("clean_text") else "medium",
        "generation_source": generation_source,
        "diagnostic_only": diagnostic_only,
        "semantic_quality": "diagnostic" if diagnostic_only else "passive",
        "ollama_generation_failed": ollama_failed,
    }


def _looks_generic_review(action: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", action.lower()).strip()
    return any(
        normalized.startswith(signature)
        for signature in GENERIC_REVIEW_SIGNATURES
    )


def _audit_generated_steps(
    steps: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    previous_signature = ""
    run_length = 0
    event_map = {
        int(event.get("event_id", 0)): event
        for event in events
    }

    for index, step in enumerate(steps):
        action = str(step.get("action", ""))

        signature = re.sub(
            r"\W+",
            " ",
            (
                f"{step.get('system')} {action} "
                f"{step.get('expected_output')}"
            ).lower(),
        ).strip()

        event = event_map.get(int(step.get("event_id", 0)), {})

        if signature == previous_signature:
            run_length += 1
        else:
            previous_signature = signature
            run_length = 1

        if run_length >= 2 and _looks_generic_review(action):
            step["weak_coverage_candidate"] = True
            step["coverage_review_required"] = True

        excel_operational_gap = (
            step.get("system") == "Excel"
            and _looks_generic_review(action)
            and (
                step.get("action_hint") in {"data entry", "filter", "post/save"}
                or float(step.get("boundary_score", 0) or 0) >= 0.18
                or any(
                    phrase in (step.get("ocr", "") or "").lower()
                    for phrase in [
                        "field",
                        "measure",
                        "sum",
                        "maximum",
                        "percentage",
                        "pivotchart",
                        "slicer",
                        "dialog",
                        "pane",
                    ]
                )
            )
        )

        if excel_operational_gap:
            step["coverage_review_required"] = True
            step["possible_missing_operation"] = True

        previous_event = (
            event_map.get(int(events[index - 1].get("event_id", 0)))
            if index > 0 and index - 1 < len(events)
            else {}
        )
        next_event = (
            event_map.get(int(events[index + 1].get("event_id", 0)))
            if index + 1 < len(events)
            else {}
        )

        if _looks_generic_review(action) and (
            previous_event.get("screen_state_id") != event.get("screen_state_id")
            or next_event.get("screen_state_id") != event.get("screen_state_id")
        ):
            step["coverage_review_required"] = True

        duration = float(
            event.get("end_time_sec", event.get("time_sec", 0)) or 0
        ) - float(
            event.get("start_time_sec", event.get("time_sec", 0)) or 0
        )

        step["source_segment_duration_seconds"] = round(
            max(0.0, duration), 3
        )

        if duration > 45:
            step["long_segment_single_step"] = True
            step["coverage_review_required"] = True

        event_text = str(event.get("clean_text") or "").lower()
        pivot_terms = any(
            term in event_text
            for term in [
                "field",
                "measure",
                "value",
                "percentage",
                "pivotchart",
                "slicer",
            ]
        )

        if (
            step.get("system") == "Excel"
            and pivot_terms
            and _looks_generic_review(action)
        ):
            step["possible_missing_operation"] = True
            step["coverage_review_required"] = True


def generate_steps(
    events: list[dict[str, Any]],
    batch_size: int = 9,
    model: str | None = None,
    max_calls: int | None = None,
    include_context_images: bool = True,
    run_stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate SOP steps while preserving one output per input event."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    model = (
        model
        or get_config("OLLAMA_MODEL", "qwen3-vl:4b")
        or "qwen3-vl:4b"
    )

    use_ollama = has_vision_model_config()

    if run_stats is not None:
        run_stats.setdefault("ollama_calls_attempted", 0)
        run_stats.setdefault("ollama_calls_succeeded", 0)
        run_stats.setdefault("ollama_errors", [])

    all_steps: list[dict[str, Any]] = []
    calls_used = 0

    for start in range(0, len(events), batch_size):
        batch = events[start : start + batch_size]
        generated: list[dict[str, Any]] = []
        model_failed = False

        if use_ollama and (max_calls is None or calls_used < max_calls):
            calls_used += 1

            if run_stats is not None:
                run_stats["ollama_calls_attempted"] += 1

            try:
                generated = _call_ollama(
                    batch,
                    model=model,
                    include_context_images=include_context_images,
                )

                if run_stats is not None:
                    run_stats["ollama_calls_succeeded"] += 1

                for item in generated:
                    item["generation_source"] = "ollama_vision"
                    item["diagnostic_only"] = False
                    item["semantic_quality"] = "operational"

            except Exception as exc:
                model_failed = True
                if run_stats is not None:
                    run_stats["ollama_errors"].append(str(exc))
                generated = []

        if not generated:
            generated = [
                _fallback_action(event, ollama_failed=model_failed)
                for event in batch
            ]

        by_event = {
            int(item.get("event_id", -1)): item
            for item in generated
            if str(item.get("event_id", "")).isdigit()
        }

        # Emit one step for every input event, even if the model omits an ID,
        # returns duplicate IDs, or fails to produce valid JSON.
        for event in batch:
            event_id = int(event["event_id"])
            item = by_event.get(event_id)

            if item is None:
                item = _fallback_action(
                    event,
                    ollama_failed=model_failed,
                )

            fallback = _fallback_action(
                event,
                ollama_failed=model_failed,
            )

            all_steps.append(
                {
                    "event_id": event_id,
                    "system": (
                        item.get("system")
                        or event.get("system")
                        or "Other"
                    ),
                    "action": (
                        str(item.get("action") or "").strip()
                        or fallback["action"]
                    ),
                    "expected_output": (
                        str(item.get("expected_output") or "").strip()
                        or fallback["expected_output"]
                    ),
                    "confidence": (
                        str(item.get("confidence") or "medium").lower()
                        if str(item.get("confidence") or "").lower()
                        in ALLOWED_CONFIDENCE
                        else "medium"
                    ),
                    "screenshot": (
                        event.get("evidence_frame") or event.get("path")
                    ),
                    "before_frame": event.get("before_frame"),
                    "after_frame": event.get("after_frame"),
                    "ocr": event.get("clean_text", ""),
                    "time_sec": event.get("time_sec", 0),
                    "start_time_sec": event.get(
                        "start_time_sec",
                        event.get("time_sec", 0),
                    ),
                    "end_time_sec": event.get(
                        "end_time_sec",
                        event.get("time_sec", 0),
                    ),
                    "boundary_score": event.get("boundary_score", 0),
                    "screen_state_id": event.get("screen_state_id"),
                    "source_segment_duration_seconds": round(
                        max(
                            0.0,
                            float(
                                event.get(
                                    "end_time_sec",
                                    event.get("time_sec", 0),
                                )
                                or 0
                            )
                            - float(
                                event.get(
                                    "start_time_sec",
                                    event.get("time_sec", 0),
                                )
                                or 0
                            ),
                        ),
                        3,
                    ),
                    "forced_split": bool(event.get("forced_split")),
                    "confidence_components": event.get(
                        "confidence_components", {}
                    ),
                    "action_hint": event.get("action_hint", "review"),
                    "rule_system": event.get("system", "Other"),
                    "source_event_index": event_id,
                    "generation_source": (
                        item.get("generation_source")
                        or fallback["generation_source"]
                    ),
                    "diagnostic_only": bool(
                        item.get(
                            "diagnostic_only",
                            fallback["diagnostic_only"],
                        )
                    ),
                    "semantic_quality": (
                        item.get("semantic_quality")
                        or fallback["semantic_quality"]
                    ),
                    "ollama_generation_failed": bool(
                        item.get("ollama_generation_failed")
                        or model_failed
                    ),
                }
            )

    _audit_generated_steps(all_steps, events)

    return all_steps[:40]