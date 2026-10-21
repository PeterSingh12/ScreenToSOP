from __future__ import annotations

from pathlib import Path
from typing import Any


def _phase_sections(phases: dict[str, list[dict[str, Any]]] | list[dict[str, Any]]):
    if isinstance(phases, list):
        return [
            (str(section.get("phase", "Review and validate")), section.get("steps", []))
            for section in phases
        ]
    return list(phases.items())


def _relative_evidence_path(screenshot: str | Path, output_path: Path) -> str:
    path = Path(screenshot)
    try:
        return path.resolve().relative_to(output_path.parent.resolve()).as_posix()
    except (ValueError, OSError):
        # Absolute paths are retained when the evidence is outside the output folder.
        return path.as_posix()


def export_markdown(
    process_name: str,
    phases: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
    output_path: str | Path,
    *,
    target_audience: str = "New employee",
    department_notes: str = "",
    warnings: list[str] | None = None,
    job_metadata: dict[str, Any] | None = None,
) -> str:
    """Write a readable SOP Markdown file mirroring the DOCX step content."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    phase_sections = _phase_sections(phases)
    step_count = sum(len(steps) for _, steps in phase_sections)
    metadata = job_metadata or {}
    lines = [
        f"# SOP: {process_name}",
        "",
        "## Summary",
        f"- **Process:** {process_name}",
        f"- **Target audience:** {target_audience}",
        f"- **Steps:** {step_count}",
        f"- **Readiness:** {metadata.get('readiness', 'needs_review')}",
        f"- **Generation mode:** {metadata.get('generation_mode', 'unknown')}",
        "",
    ]
    if department_notes.strip():
        lines.extend(["## Department / system notes", "", department_notes.strip(), ""])
    if warnings:
        lines.extend(["## Evidence warnings", ""])
        lines.extend([f"- {str(warning).strip()}" for warning in warnings if str(warning).strip()])
        lines.append("")

    lines.extend(["## Procedure", ""])
    for phase_name, steps in phase_sections:
        lines.extend([f"### {phase_name}", ""])
        for step in steps:
            number = step.get("step_number", "?")
            lines.extend([
                f"#### Step {number}",
                "",
                f"- **System:** {step.get('system', 'Other')}",
                f"- **Action:** {step.get('action', 'Review the visible process screen.')}",
                f"- **Expected output:** {step.get('expected_output', 'The relevant process information is visible.')}",
                f"- **Confidence:** {str(step.get('confidence', 'medium')).title()}",
            ])
            if step.get("risky"):
                lines.append("- **Review note:** This step was flagged for conservative review.")
            screenshot = step.get("screenshot")
            if screenshot:
                try:
                    start = float(step.get("start_time_sec", step.get("time_sec", 0)) or 0)
                    end = float(step.get("end_time_sec", step.get("time_sec", 0)) or 0)
                except (TypeError, ValueError):
                    start = end = 0.0
                state = step.get("screen_state_id", step.get("screen_state", "unknown"))
                lines.extend([f"- **Screenshot evidence:** {start:.1f}s–{end:.1f}s; screen state `{state}`"])
                screenshot_path = Path(screenshot)
                if screenshot_path.is_file():
                    link = _relative_evidence_path(screenshot_path, output_path).replace(" ", "%20")
                    lines.extend(["", f"![Screenshot evidence for step {number}]({link})"])
                else:
                    lines.append(f"- Screenshot file unavailable: `{screenshot_path.as_posix()}`")
            lines.append("")

    lines.extend([
        "## Review guidance",
        "",
        "This document is generated from screen-recording evidence. Review each action and screenshot before using it as an authoritative procedure.",
        "",
    ])
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)
