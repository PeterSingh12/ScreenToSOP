# ScreenToSOP — Screen Recording to Standard Operating Procedure

ScreenToSOP is a full-stack application that converts screen recordings into screenshot-backed Standard Operating Procedures (SOPs) in DOCX and Markdown formats, with a structured JSON workflow API.

Built for A3i-Accel's **Assignment 5: Screen-to-SOP Agent — Recording to Procedure Document**, the project aims to turn recorded workflows into reusable process documentation that people can follow, review, and use to identify potential automation opportunities.

## Why ScreenToSOP?

Organizations often rely on employees to explain how business processes work. These explanations may be recorded during meetings or captured as screen recordings, but converting them into clear, reusable documentation takes time.

ScreenToSOP automates much of this documentation process by analyzing screen recordings, identifying screen-state changes, extracting visible text, organizing workflow events, and generating structured procedures with screenshot evidence.

For A3i-Accel, this creates a foundation for capturing process knowledge and identifying repeatable tasks that may be suitable for automation through an A3i App, Ant, or Agent.

## Features

- **Video processing:** Extracts frames from uploaded screen recordings using OpenCV and supporting video tools.
- **Screen-state segmentation:** Detects visual changes and identifies candidate boundaries between workflow steps.
- **OCR-based understanding:** Uses Tesseract to extract visible text from screenshots.
- **Workflow classification:** Applies rule-based classification and cleanup to reduce irrelevant events, duplicate steps, and generic instructions.
- **AI-assisted generation:** Supports optional local vision-model generation through Ollama.
- **Fallback generation:** Produces OCR-based drafts or diagnostic output when vision generation fails or the available evidence is insufficient.
- **Quality checks:** Evaluates generated steps and surfaces warnings, confidence indicators, and readiness information.
- **Multiple output formats:** Generates Word SOPs, Markdown documentation, and structured workflow JSON.
- **Screenshot-backed procedures:** Associates workflow steps with visual evidence where available.
- **REST API:** Exposes a FastAPI endpoint for submitting recordings and retrieving generated results.
- **React frontend:** Provides a web interface for uploading recordings and reviewing generated procedures.
- **Streamlit interface:** Retains an alternative local interface.
- **Automated tests:** Includes tests for implemented API and pipeline functionality.

## Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Backend API | Python, FastAPI | Accept recordings and expose workflow results |
| Frontend | React, Vite, JavaScript | User interface for submitting recordings and reviewing outputs |
| Video processing | OpenCV, FFmpeg | Frame extraction and video processing |
| OCR | Tesseract, pytesseract | Extract visible text from screenshots |
| Workflow segmentation | Python, deterministic rules | Detect screen-state changes and candidate workflow events |
| AI generation | Ollama with a compatible vision model | Generate step descriptions when inference succeeds |
| Document generation | python-docx | Export procedures to Word |
| Structured output | Markdown, JSON | Produce portable documentation and machine-readable workflows |
| Testing | pytest | Validate tested application and pipeline behavior |

## How It Works

1. **Upload:** The user submits a screen recording along with process metadata.
2. **Frame extraction:** The pipeline extracts frames and computes visual information from the recording.
3. **Segmentation:** Screen-state changes are analyzed to identify candidate workflow events.
4. **OCR:** Tesseract extracts text visible in relevant frames.
5. **Classification:** Rule-based logic organizes events and reduces irrelevant content.
6. **Instruction generation:** The configured Ollama vision model attempts to generate evidence-backed instructions.
7. **Fallback handling:** If vision generation fails or evidence is insufficient, the application can produce an OCR-derived draft or diagnostic output.
8. **Validation and cleanup:** Generated steps are checked and cleaned up, and quality issues are surfaced.
9. **Document export:** The application generates DOCX and Markdown SOPs alongside structured workflow JSON.
10. **Review:** The user inspects the generated steps, screenshots, warnings, and readiness before using or sharing the procedure.

The application avoids padding weak results with invented steps. When the recording does not provide sufficient evidence, the resulting procedure may be shorter and require human review.

## Architecture

```text
Screen Recording
       |
       v
React Frontend
       |
       v
FastAPI Backend
POST /record-to-sop
       |
       v
Video Processing
OpenCV / FFmpeg
       |
       v
Screen-State Segmentation
       |
       v
OCR Extraction
Tesseract
       |
       v
Event Classification
and Evidence Preparation
       |
       v
Instruction Generation
       |
       +--------------------+
       |                    |
       v                    v
Ollama Vision         OCR / Diagnostic
Generation               Fallback
       |                    |
       +--------------------+
                  |
                  v
        Validation and Cleanup
                  |
                  v
           Quality Scoring
                  |
         +--------+--------+
         |        |        |
         v        v        v
       DOCX    Markdown   Workflow
                           JSON
```

## Generated Outputs

### 1. Word SOP (`sop.docx`)

The generated document can include:

- Process title.
- Summary, purpose, prerequisites, and assumptions.
- Numbered steps arranged chronologically.
- Screenshot evidence associated with workflow steps.
- System and action descriptions.
- Expected outputs and confidence indicators where available.
- Low-confidence review checklist.
- Cleanup and quality report appendix.
- Job metadata.

### 2. Markdown SOP (`sop.md`)

A Markdown version of the procedure supports readable documentation, version control, and sharing. It includes step content and screenshot references where available.

### 3. Workflow JSON

The API returns structured workflow data, including job metadata, steps, warnings, readiness, generation mode, and artifact URLs.

The assignment specifies the following fields for each step:

- `step`
- `timestamp`
- `action`
- `ui_element`
- `screenshot_url`
- `note`

The exact response schema should be verified against the implemented API.

## REST API

### Health Check

`GET /health`

Checks whether the backend is responding.

### Generate an SOP

`POST /record-to-sop`

Content type: `multipart/form-data`

The endpoint accepts a screen recording and process metadata.

| Field | Description |
|---|---|
| `video` | Screen recording file |
| `process_name` | Name of the workflow |
| `target_audience` | Intended reader of the SOP |
| `department_notes` | Optional context about the process |
| `quality_profile` | Processing profile |

Supported upload extensions include MP4, MOV, M4V, WebM, MKV, and AVI. The configured upload limit is 250 MiB.

The response contains the job ID, generated workflow steps, readiness and generation-mode labels, warnings, and artifact download URLs.

### Artifact Endpoints

```text
/jobs/{job_id}/sop.docx
/jobs/{job_id}/sop.md
/jobs/{job_id}/workflow.json
```

Screenshot and other artifact URLs depend on the generated job structure and the implemented serving routes.

The current API processes recordings synchronously. Longer recordings may keep an HTTP request open while processing completes. The current architecture is primarily intended for local demonstrations rather than high-concurrency production use.

## Installation

### Prerequisites

- Python 3.10 or newer, subject to dependency compatibility.
- Node.js and npm for the React frontend.
- Tesseract OCR.
- FFmpeg.
- Ollama and a compatible local vision model for optional vision inference.

### 1. Set Up the Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Install Native Dependencies on macOS

```bash
brew install tesseract ffmpeg
```

Verify Tesseract:

```bash
tesseract --version
```

Check local prerequisites:

```bash
python scripts/check_prereqs.py
```

### 3. Configure Ollama

Create a `.env` file in the repository root:

```dotenv
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=qwen3-vl:4b
OLLAMA_BASE_URL=http://localhost:11434/v1/
TESSERACT_CMD=/opt/homebrew/bin/tesseract
```

These are example values for a local macOS setup. Adjust the model and Tesseract path to match your environment.

The `ollama` API key value is a local placeholder for an Ollama-compatible endpoint, not a hosted-service credential.

Install the configured model if necessary:

```bash
ollama pull qwen3-vl:4b
```

Check installed models:

```bash
ollama list
```

If Ollama is already running as a background service, do not start a second server.

Configuration precedence:

```text
Environment variables > .env > Streamlit secrets > defaults
```

Successful model installation does not guarantee successful inference. Context limits, memory usage, image payload size, and response truncation may affect generation.

Never commit `.env` or other files containing credentials to GitHub.

## Running the Application

### 1. Start the FastAPI Backend

From the repository root:

```bash
source .venv/bin/activate
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Health check:

`http://127.0.0.1:8000/health`

### 2. Start the React Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, typically:

`http://localhost:5173`

The frontend can use `VITE_API_BASE_URL` to configure the backend URL. For local development, the default is:

`http://127.0.0.1:8000`

### 3. Optional Streamlit Interface

The repository also includes a Streamlit interface:

```bash
python -m streamlit run app.py
```

Open:

`http://localhost:8501`

This is an alternative local interface, separate from the React frontend.

## Typical User Workflow

1. Enter the process name.
2. Select the target audience.
3. Add optional department or system notes.
4. Choose an available quality profile.
5. Upload a screen recording.
6. Start the processing job.
7. Review generated steps, screenshots, warnings, and readiness.
8. Download the SOP in DOCX or Markdown format.

Generated procedures should be reviewed whenever steps are ambiguous, screenshots do not support an instruction, or the pipeline reports insufficient evidence.


## Evaluation and Testing

Run the automated test suite:

```bash
python -m pytest -q
```

Compile application modules:

```bash
python -m compileall api.py app.py worker.py pipeline storage tests scripts
```

Run the deterministic demo:

```bash
python scripts/demo_run.py
```

Run the smoke test:

```bash
python scripts/smoke_test.py
```

Evaluate a completed job:

```bash
python scripts/evaluate_job.py jobs/<JOB_ID>
```

Replace `<JOB_ID>` with the directory created by the application.

Passing tests validates the tested code paths. It does not guarantee factual correctness for every recording or prove that the assignment's performance targets have been achieved.

## Pipeline Diagnostics and Artifacts

Each job is stored under:

```text
jobs/<job_id>/
```

Depending on the execution path, artifacts may include:

```text
jobs/<job_id>/
├── input.mp4
├── sop.docx
├── sop.md
└── artifacts/
    ├── workflow.json
    ├── frames.json
    ├── frame_metrics.json
    ├── boundary_candidates.json
    ├── screen_states.json
    ├── event_segments.json
    ├── segmentation_report.md
    ├── ocr_raw.json
    ├── steps_generated.json
    ├── steps_validated.json
    ├── sop_cleanup.json
    └── steps_final.json
```

Not every artifact is guaranteed to exist for every run.

These intermediate files help diagnose missed screen changes, OCR failures, generic instructions, low-confidence steps, and other quality issues.

## Quality and Readiness

The application uses readiness labels such as:

- `demo_ready`
- `needs_review`
- `not_ready`

Quality scoring may consider step coverage, low-confidence instructions, duplicates, generic steps, chronology violations, workflow density, long segments, and action plausibility.

A high semantic-coverage score is not proof that the generated instructions are correct. Each instruction should be compared with its screenshot evidence.

When vision generation fails, an OCR-derived or diagnostic draft may still be produced. Such a draft is not equivalent to a fully verified AI-generated procedure.

## Security and Privacy

Screen recordings may contain confidential business information or personal data.

- Never commit credentials, `.env`, private recordings, or generated documents containing sensitive information.
- Obtain consent before processing meeting recordings that include other participants.
- Implement and test redaction before claiming sensitive information is automatically blurred.
- Review generated documents for sensitive information before sharing.
- Treat generated procedures as drafts until their accuracy has been verified.

## Current Limitations

- Fast interactions and poor-quality recordings can cause missed steps.
- OCR depends on readable text, screen resolution, and screenshot quality.
- Local vision-model inference may fail because of resource constraints or response limits.
- OCR-derived instructions may not fully capture user intent.
- Generated procedures require human review before use in sensitive or consequential processes.
- Browser-based recording, narration transcription, and sensitive-field blurring should only be described as supported after implementation and testing.
- Processing-time and step-coverage targets must be measured across representative recordings.
- The synchronous API and local job storage are not sufficient on their own for a robust multi-user production deployment.

## Future Work

- Improve vision-model reliability and instruction grounding.
- Implement and test browser-based recording using the Screen Capture API.
- Add narration transcription using a suitable speech-recognition model.
- Implement and validate sensitive-field redaction.
- Compare generated SOPs against human-written ground truth for three sample processes.
- Measure step coverage, task reproducibility, and processing time.
- Improve screenshot-to-instruction traceability.
- Improve recovery from failed model inference.
- Harden deployment, artifact storage, and long-running job handling.
- Explore automation-candidate extraction as a stretch goal.

## Project Structure

```text
ScreenToSOP/
├── api.py
├── app.py
├── worker.py
├── frontend/
├── pipeline/
├── storage/
├── scripts/
├── tests/
├── docs/
├── requirements.txt
├── package.json
└── README.md
```

## Documentation

Additional documentation is available in:

- `docs/architecture.md`
- `docs/pipeline.md`
- `docs/configuration.md`
- `docs/development.md`
- `docs/troubleshooting.md`
- `docs/quickstart.md`
- `docs/showcase-checklist.md`

## License

A project license has not yet been specified. Add the chosen license before distributing the repository publicly.