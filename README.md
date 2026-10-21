# Video2SOP Fast Mode

Video2SOP is a local-first application that turns a screen recording into a screenshot-backed SOP in DOCX and Markdown formats, with a JSON workflow API. It is built for process documentation, not generic video analysis.

The current implementation is local-first:

- OpenCV extracts dense frames for metric scoring and selected frames for evidence.
- A deterministic segmentation engine detects screen-state boundaries.
- OCR enriches segment evidence when native Tesseract is installed. The app resolves `TESSERACT_CMD`, PATH, and common Windows installation paths.
- Rule-based classification and deterministic cleanup reduce noise, passive filler, and weak duplicates.
- Local Ollama vision generation can produce evidence-backed SOP wording when inference succeeds. If vision generation fails, the app can fall back to an OCR draft when OCR text is available or a diagnostic draft when semantic evidence is unavailable.
- `.env` and optional Streamlit secrets are loaded automatically.
- The final DOCX includes screenshots, confidence indicators, timeline-safe phase sections, and a cleanup quality appendix.

## Product Promise

Turn a process recording into a professional SOP in minutes.

The product supports the following modes:

- **Ollama vision mode:** attempts vision-based step generation and verification using the configured local model.
- **OCR draft mode:** uses locally extracted text to create a draft when vision generation is unavailable or unsuccessful.
- **Diagnostic draft mode:** produces diagnostic output when semantic evidence is insufficient. The document requires review.

Model configuration does not guarantee successful inference. Generated instructions must be checked against their screenshot evidence.

## What the App Produces

The generated DOCX includes:

- `SOP: {process_name}` title
- Summary, prerequisites, and assumptions
- Chronological steps rendered in timeline phase sections
- Screenshot evidence for each step
- System, action, expected output, and confidence
- Low-confidence review checklist
- Cleanup and quality report appendix
- Job metadata appendix

The app does not pad weak runs with invented steps. If the recording only supports a short SOP, the output stays short and records warnings rather than pretending the process was fully captured.

## Current Pipeline

- Video upload and local storage
- Dense frame extraction
- Adaptive screen-state segmentation
- OCR preprocessing and extraction
- Rule-based system classification
- Local vision step generation when available
- OCR-based and diagnostic fallback generation
- Risky-step verification
- Deterministic SOP cleanup and quality scoring
- DOCX export

## Requirements

- Python 3.10 or newer, subject to dependency compatibility
- `streamlit`
- `opencv-python`
- `numpy`
- `pillow`
- `python-docx`
- `pytesseract`
- `python-dotenv`
- Native Tesseract OCR installed on the system
- Ollama and a compatible local vision model for optional vision inference

Python package dependencies are listed in `requirements.txt`.

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install native dependencies on macOS if needed:

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

## Ollama Configuration

Create a `.env` file in the repository root:

```dotenv
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=qwen3-vl:4b
OLLAMA_BASE_URL=http://localhost:11434/v1/
TESSERACT_CMD=/opt/homebrew/bin/tesseract
```

The `ollama` API key value is a local placeholder for the Ollama-compatible endpoint, not a hosted-service credential.

Install the configured model if it is not already available:

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
Real environment variable > .env > Streamlit secrets > default
```

Successful model installation does not guarantee successful inference. Context limits, memory usage, image payload size, and response truncation may affect generation. When vision inference fails, the app should report fallback output honestly.

## Running the App

Launch Streamlit:

```bash
python -m streamlit run app.py
```

Open:

```text
http://localhost:8501
```

### UI Workflow

1. Enter a process name.
2. Optionally provide department or system notes.
3. Select the target audience and available quality profile.
4. Upload a recording.
5. Start the job.
6. Review cleanup diagnostics and readiness.
7. Download the generated DOCX.

Each completed job also writes `sop.md` and `artifacts/workflow.json`. Markdown image references use paths relative to the job folder when possible.

The current interface supports recording upload. Browser-based recording should only be listed as a feature if it has been separately implemented and tested.

## HTTP API

The API processes an uploaded video synchronously and returns the workflow JSON plus artifact download URLs. For a five-minute recording, the HTTP request may remain open while processing runs.

Install the API dependencies (they are also listed in `requirements.txt`):

```bash
python -m pip install -r requirements.txt
```

Start the API server:

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Health check: `GET http://127.0.0.1:8000/health`

Upload a recording (replace the path with a real video):

```bash
curl -X POST http://127.0.0.1:8000/record-to-sop \
  -F "video=@./recording.mp4" \
  -F "process_name=Update Customer Record" \
  -F "target_audience=New employee"
```

The response contains `job_id`, readiness and generation-mode labels, the structured `steps` array, warnings, and URLs for DOCX, Markdown, and workflow JSON. Supported upload extensions are MP4, MOV, M4V, WEBM, MKV, and AVI; the API upload limit is 250 MiB. Artifact URLs are served by the same API process. The endpoint is synchronous and intended for local demonstration, not high-concurrency production deployment.

## Run a Local Demo

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

Replace `<JOB_ID>` with the job directory created by the demo.

## Run Tests

```bash
python -m pytest -q
```

Compile the application modules:

```bash
python -m compileall app.py worker.py pipeline storage tests scripts
```

Passing tests validate the tested code paths. They do not guarantee successful vision generation or factual correctness for every recording.

## Quality Profiles

Profiles are defined in `pipeline/config.py`.

Available profiles and their processing limits depend on the current implementation. Review `pipeline/config.py` for the exact frame limits, OCR limits, event limits, generation-call limits, and verification settings.

## Job Output and Artifacts

Each job is stored under:

```text
jobs/<job_id>/
```

Important artifacts include:

- `input.mp4` — source recording, when retained
- `sop.docx` — generated SOP
- `sop.md` — Markdown SOP with equivalent step content and screenshot references
- `artifacts/workflow.json` — final structured workflow, readiness, generation mode, and warnings
- `artifacts/frames.json` — frame extraction information
- `artifacts/frame_metrics.json` — per-frame visual metrics
- `artifacts/boundary_candidates.json` — candidate boundary decisions
- `artifacts/screen_states.json` — recurring screen-state information
- `artifacts/event_segments.json` — segmented workflow evidence
- `artifacts/segmentation_report.md` — segmentation diagnostics
- `artifacts/ocr_raw.json` — OCR output
- `artifacts/steps_generated.json` — initially generated or fallback steps
- `artifacts/steps_validated.json` — validated steps before cleanup
- `artifacts/sop_cleanup.json` — cleanup details and quality report
- `artifacts/steps_final.json` — final cleaned workflow steps

Not every artifact is guaranteed to exist for every run.

## Quality and Readiness

The application assigns a readiness state:

- `demo_ready`
- `needs_review`
- `not_ready`

Quality scoring may consider step coverage, low-confidence instructions, duplicates, generic steps, chronology violations, workflow density, long single-step segments, and phase/action plausibility.

A high semantic-coverage score is not proof that the generated instructions are correct. Compare each instruction with its screenshot evidence.

### Local Demo Evaluation

One observed demo run produced:

| Metric | Result |
|---|---:|
| Events | 6 |
| Generated steps | 6 |
| Validated steps | 6 |
| Final steps | 5 |
| OCR frames | 10 |
| OCR frames with non-empty text | 10 |
| Operational actions | 5 |
| Generic review steps | 0 |
| Phase errors | 0 |
| Semantic coverage | 1.0 |
| Quality score | 70 |
| Readiness | `needs_review` |

Generation sources for this run were five OCR-derived steps and one diagnostic fallback step before cleanup.

These figures describe a single local demo run, not a general benchmark.

## Project Structure

```text
ScreenToSOP/
├── app.py
├── worker.py
├── pipeline/
├── storage/
├── scripts/
├── tests/
├── docs/
├── requirements.txt
└── README.md
```

## Documentation

- `docs/architecture.md`
- `docs/pipeline.md`
- `docs/configuration.md`
- `docs/development.md`
- `docs/troubleshooting.md`
- `docs/quickstart.md`

## Security and Repository Hygiene

Ensure `.gitignore` excludes:

- `.env` and other secret-bearing environment files
- `.streamlit/secrets.toml`
- Uploaded recordings and screenshots
- Generated SOP documents and job artifacts
- SQLite databases and local logs
- Virtual environments and cache directories

Never commit credentials, private recordings, or generated documents containing sensitive information.

## Known Limitations

- Poor-quality recordings and fast interactions can lead to missed steps.
- OCR depends on readable text, screen resolution, and image quality.
- Local vision-model inference may fail because of resource constraints or response limits.
- OCR-derived instructions may not fully capture user intent or the meaning of visual actions.
- Generated SOPs require human review before being used for sensitive or consequential processes.
- The application is designed for local, single-user use rather than as a hosted multi-user service.
- Processing-time and coverage targets must be measured across representative recordings before being claimed as achieved.

## Future Work

- Improve local vision-model reliability.
- Add and test browser-based recording if required.
- Benchmark step coverage and processing time across representative recordings.
- Improve screenshot-to-instruction traceability.
- Expand evaluation using human-reviewed ground-truth SOPs.
- Improve recovery and error reporting for failed model inference.

## License

Add the project's chosen license before publishing the repository.