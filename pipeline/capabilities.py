
from __future__ import annotations

from typing import Any

from pipeline.ocr import ocr_status
from pipeline.runtime_config import config_source, has_vision_model_config


PRODUCTION_VISION = "production_vision"
LOCAL_OCR_DRAFT = "local_ocr_draft"
DIAGNOSTIC_ONLY = "diagnostic_only"


def ollama_configured() -> bool:
    """Return whether the Ollama vision-model configuration is available."""
    return has_vision_model_config()


def capability_status() -> dict[str, Any]:
    """Report available inference and OCR capabilities."""
    ollama_ready = ollama_configured()
    ocr = ocr_status()

    if ollama_ready:
        mode = PRODUCTION_VISION
    elif ocr.get("available"):
        mode = LOCAL_OCR_DRAFT
    else:
        mode = DIAGNOSTIC_ONLY

    return {
        "generation_mode": mode,
        "ollama_configured": ollama_ready,
        "ollama_config_source": (
            config_source("OLLAMA_API_KEY") if ollama_ready else "missing"
        ),
        "ocr_available": bool(ocr.get("available")),
        "ocr_status": ocr,
    }


def generation_mode_after_ocr(
    ollama_ready: bool,
    ocr_non_empty_count: int,
) -> str:
    """Select a generation mode using model configuration and OCR evidence."""
    if ollama_ready:
        return PRODUCTION_VISION

    if ocr_non_empty_count > 0:
        return LOCAL_OCR_DRAFT

    return DIAGNOSTIC_ONLY

def generation_mode_after_generation(
    ollama_calls_succeeded: int,
    ocr_non_empty_count: int,
) -> str:
    """Report the mode supported by actual generation results and OCR evidence."""
    if ollama_calls_succeeded > 0:
        return PRODUCTION_VISION

    if ocr_non_empty_count > 0:
        return LOCAL_OCR_DRAFT

    return DIAGNOSTIC_ONLY