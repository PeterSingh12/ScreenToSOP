from pipeline.markdown_export import export_markdown


def test_export_markdown_includes_steps_warnings_and_screenshot(tmp_path):
    screenshot = tmp_path / "frames" / "step 1.png"
    screenshot.parent.mkdir()
    screenshot.write_bytes(b"not-a-real-image-but-existing-evidence-file")
    output = tmp_path / "sop.md"
    phases = {
        "Open application": [
            {
                "step_number": 1,
                "system": "Billing portal",
                "action": "Open the invoice list.",
                "expected_output": "The invoice list is visible.",
                "confidence": "high",
                "screenshot": str(screenshot),
                "start_time_sec": 1.2,
                "end_time_sec": 2.4,
                "screen_state_id": "state-1",
            }
        ]
    }

    result = export_markdown(
        "Invoice Review",
        phases,
        output,
        target_audience="Finance team",
        department_notes="Use the test environment.",
        warnings=["Review the generated wording."],
        job_metadata={"readiness": "needs_review", "generation_mode": "local_ocr_draft"},
    )

    text = output.read_text(encoding="utf-8")
    assert result == str(output)
    assert "# SOP: Invoice Review" in text
    assert "**Target audience:** Finance team" in text
    assert "### Open application" in text
    assert "Open the invoice list." in text
    assert "The invoice list is visible." in text
    assert "Review the generated wording." in text
    assert "![Screenshot evidence for step 1](frames/step%201.png)" in text
    assert "**Readiness:** needs_review" in text


def test_export_markdown_handles_missing_screenshot_and_empty_steps(tmp_path):
    output = tmp_path / "empty.md"
    export_markdown(
        "Empty Process",
        {"Review and validate": [{"step_number": 1, "action": "Check the record.", "screenshot": str(tmp_path / "missing.png")} ]},
        output,
    )
    text = output.read_text(encoding="utf-8")
    assert "Check the record." in text
    assert "Screenshot file unavailable" in text
    assert "**Readiness:** needs_review" in text
