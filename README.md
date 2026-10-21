# ScreenToSOP
### Turn screen recordings into screenshot-backed Standard Operating Procedures

ScreenToSOP is a Python and React application that converts a screen recording into a structured, step-by-step Standard Operating Procedure (SOP). It combines video processing, OCR, workflow segmentation, step-description generation, validation, and document export to help turn a recorded software walkthrough into reusable instructions.

This project was developed for **A3i-Accel Intern Assignment 5: Screen-to-SOP Agent — Recording to Procedure Document**.

## Table of Contents

- [Problem and Objective](#problem-and-objective)
- [Features](#features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Requirements](#requirements)
- [Local Setup](#local-setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Generated Artifacts](#generated-artifacts)
- [Testing](#testing)
- [Evaluation and Success Criteria](#evaluation-and-success-criteria)
- [Limitations and Future Improvements](#limitations-and-future-improvements)
- [Repository Structure](#repository-structure)

## Problem and Objective

Software procedures are often documented manually, even when the process has already been demonstrated in a screen recording. Manual documentation takes time and can omit important actions or interface details.

ScreenToSOP aims to reduce that effort by processing a recording and producing a reviewable procedure containing ordered steps, timestamps, relevant interface context, and screenshot evidence.

The intended users include teams documenting internal workflows, onboarding processes, software operations, and repeatable business procedures.

## Features

The repository contains the following components:

- **Video processing:** Uses FFmpeg and OpenCV to process recordings and extract frames for analysis.
- **Text extraction:** Uses Tesseract OCR to read visible interface text from selected frames.
- **Workflow segmentation:** Organizes extracted visual evidence into candidate steps.
- **Step-description generation:** Uses a configurable local vision-model integration when available, with fallback behavior for cases where generated descriptions are unavailable or unsuitable.
- **Validation and cleanup:** Includes pipeline components for cleaning, checking, and refining generated steps.
- **Document export:** Produces SOP documents in Microsoft Word (`.docx`) and Markdown (`.md`) formats.
- **Structured workflow output:** Exposes workflow data through a FastAPI endpoint and job artifacts.
- **Web interface:** Provides a React application for interacting with the workflow.
- **Automated tests:** Includes tests for API behavior, pipeline processing, segmentation, validation-related components, and document export.

Generated instructions should be reviewed before being used as authoritative operational documentation.

## Architecture

The application is organized into four main layers.

1. **Frontend:** A React application built with Vite provides the browser-facing interface.
2. **API:** FastAPI accepts recordings and processing options, starts the workflow, and returns structured results.
3. **Processing pipeline:** Python modules handle video processing, OCR, segmentation, step classification, cleanup, and validation. A local vision model can assist with step descriptions.
4. **Export and storage:** The application stores job artifacts and produces the SOP documents and structured workflow data.

### Processing flow

1. Select or record a screen walkthrough and provide the required processing inputs.
2. Submit the recording to the backend.
3. Extract frames and identify useful visual evidence.
4. Apply OCR and organize the evidence into candidate workflow steps.
5. Generate or construct step descriptions and validate the resulting sequence.
6. Export the SOP and structured workflow artifacts.
7. Review the generated procedure and any uncertainty indicators.

The exact quality of generated instructions depends on the recording, visible interface text, segmentation, and availability of the configured vision model.

## Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Frontend | React, Vite, JavaScript | Browser interface |
| Backend | Python, FastAPI, Uvicorn | HTTP API and request handling |
| Video processing | FFmpeg, OpenCV | Frame extraction and video analysis |
| OCR | Tesseract | Extract visible text |
| AI-assisted descriptions | Ollama with a compatible vision model | Optional visual interpretation |
| Document generation | python-docx | Word SOP export |
| Structured output | JSON and Markdown | Workflow data and portable documentation |
| Testing | pytest | Automated backend and pipeline tests |

## Requirements

The following are needed for the full local workflow:

- Python 3.11 or newer, compatible with the dependencies in `requirements.txt`
- Node.js and npm
- FFmpeg
- Tesseract OCR
- Git

For AI-assisted descriptions, install Ollama and download a compatible vision model. The project can use its fallback processing path when model generation is unavailable, but the resulting descriptions may be less specific.

### macOS dependency installation

Install system dependencies with Homebrew:

```bash
brew install ffmpeg tesseract
```

Install Node.js from https://nodejs.org/ if `node` and `npm` are not available.

Install Ollama from https://ollama.com/ if you want to use local vision-model inference.

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/PeterSingh12/ScreenToSOP.git
cd ScreenToSOP
```

### 2. Create and activate a Python environment

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Keep the virtual environment activated when running the backend or tests.

### 3. Install frontend dependencies

Open a second terminal in the repository directory:

```bash
cd frontend
npm install
```

### 4. Configure environment variables

Create a local `.env` file in the project root. Do not commit this file or put credentials in source code.

Example configuration:

```dotenv
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=qwen3-vl:4b
OLLAMA_BASE_URL=http://localhost:11434/v1/
TESSERACT_CMD=/opt/homebrew/bin/tesseract
```

These values are examples for a local macOS setup. Update `TESSERACT_CMD` if Tesseract is installed elsewhere. The Ollama URL assumes Ollama is running on the same machine.

The `ollama` API key value is a local compatibility placeholder for setups that do not require a real remote API key. It is not a cloud credential. Follow the configured model client's requirements if your environment differs.

The application should be run with the environment configuration expected by its runtime modules. Do not publish private credentials, personal recordings, or sensitive screenshots.

### 5. Optional: Prepare the local vision model

Start Ollama and download the configured model if it is not already installed:

```bash
ollama pull qwen3-vl:4b
```

Ensure Ollama is running before testing AI-assisted generation. Model availability and performance depend on your hardware and local configuration.

## Running the Application

Run the backend and frontend in separate terminals.

### Terminal 1: FastAPI backend

From the repository root, with `.venv` activated:

```bash
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Open the API health endpoint:

http://127.0.0.1:8000/health

Interactive API documentation is available at:

http://127.0.0.1:8000/docs

### Terminal 2: React frontend

```bash
cd frontend
npm run dev
```

Open the local URL printed by Vite, normally:

http://localhost:5173

If the frontend needs a different backend address, configure `VITE_API_BASE_URL` in the frontend environment and restart the development server.

### Production frontend build check

From the `frontend` directory:

```bash
npm run build
```

Vite writes the production build to `frontend/dist/`. This build check does not itself deploy the application.

## Configuration

| Variable | Purpose |
|---|---|
| `OLLAMA_API_KEY` | API-client compatibility setting for the configured model endpoint |
| `OLLAMA_MODEL` | Vision model identifier |
| `OLLAMA_BASE_URL` | Base URL for the model service |
| `TESSERACT_CMD` | Path to the Tesseract executable |
| `VITE_API_BASE_URL` | Backend base URL used by the frontend |

Use environment-specific values rather than hardcoding machine paths. The Tesseract path shown above is a common Homebrew path on Apple Silicon Macs, not a universal location.

## API Reference

The main processing endpoint is:

`POST /record-to-sop`

It accepts a screen recording and processing metadata as a multipart form request.

### Request fields

| Field | Description |
|---|---|
| `video` | Uploaded screen-recording file |
| `process_name` | Name of the workflow being documented |
| `target_audience` | Intended reader of the generated SOP |
| `department_notes` | Optional contextual instructions |
| `quality_profile` | Processing-quality profile |

The endpoint returns structured workflow information. Individual steps are designed to represent fields such as:

- `step`: Step number
- `timestamp`: Approximate point in the recording
- `action`: Description of the action
- `ui_element`: Relevant interface element
- `screenshot_url`: Screenshot evidence reference
- `note`: Additional context or review information

The exact response fields and validation behavior are defined by the implementation in `api.py`.

### Example request

After starting the backend, use the following command from the project root. Replace the sample video path with a real recording:

```bash
curl -X POST "http://127.0.0.1:8000/record-to-sop" \
  -F "video=@sample-recording.mp4" \
  -F "process_name=Sample Workflow" \
  -F "target_audience=New Team Member" \
  -F "department_notes=Explain important interface actions" \
  -F "quality_profile=balanced"
```

The example illustrates the multipart request shape. Accepted quality-profile values and any additional validation constraints should be checked in the current API implementation or at `/docs`.

## Generated Artifacts

For a processed job, the backend exposes job artifacts through routes of the following form:

| Artifact | Route |
|---|---|
| Word SOP | `/jobs/{job_id}/sop.docx` |
| Markdown SOP | `/jobs/{job_id}/sop.md` |
| Structured workflow | `/jobs/{job_id}/workflow.json` |

Use the actual `job_id` returned by the API response.

The Word and Markdown documents are intended to make the procedure easy to share and review. The workflow JSON provides structured data for further inspection or integration.

Artifact availability depends on the backend's job-storage configuration and the lifetime of the local environment.

## Testing

Run the backend tests from the repository root with the virtual environment activated:

```bash
pytest -q
```

Build the frontend separately:

```bash
cd frontend
npm run build
```

The test suite includes API and pipeline-related tests. Passing automated tests provides evidence that tested code paths behave as expected; it does not by itself prove end-to-end accuracy, successful completion of every recording type, or achievement of the assignment's performance targets.

For a manual smoke test:

1. Start the backend and frontend.
2. Open the frontend in a browser.
3. Submit a short, non-sensitive sample recording.
4. Confirm that the API processes the request.
5. Inspect the generated steps and screenshots.
6. Open the Word and Markdown artifacts.
7. Check the workflow JSON and any warnings or review indicators.

Use a recording with a clear sequence of visible actions for the first test.

## Limitations and Future Improvements

- OCR quality depends on text size, contrast, resolution, and the clarity of the recording.
- Similar-looking screens or rapid transitions can make step boundaries difficult to identify.
- A vision model may produce incomplete or incorrect action descriptions.
- Fallback descriptions can be less specific than model-generated descriptions.
- Long recordings and local model inference can take significant time and memory.
- A generated SOP requires human review before being used for important or sensitive operations.
- Local job artifacts should be treated as temporary unless persistent storage is explicitly configured.
- Sensitive-field detection and redaction should be validated on representative recordings before claiming comprehensive protection.
- A broader evaluation is needed to establish general accuracy and performance.

Potential future improvements include more robust step-boundary detection, narration transcription, stronger sensitive-data redaction, persistent artifact storage, and a larger human-reviewed evaluation set.

## Repository Structure

```text
ScreenToSOP/
├── api.py                  # FastAPI endpoints
├── app.py                  # Existing application entry point
├── worker.py               # Processing orchestration
├── pipeline/               # Video, OCR, segmentation, cleanup and export
├── storage/                # Job and artifact handling
├── frontend/               # React/Vite frontend
├── tests/                  # Automated tests
├── scripts/                # Demo, evaluation and utility scripts
├── docs/                   # Architecture and development documentation
├── requirements.txt        # Python dependencies
├── package.json            # Root JavaScript package configuration
└── .gitignore
```

Some optional or legacy components may remain in the repository. The FastAPI service is started with `uvicorn api:app`.

## Submission Notes

- Repository: https://github.com/PeterSingh12/ScreenToSOP
- Local execution is the primary setup described in this README.
- The application is not presented here as a publicly hosted service.
- Use a non-sensitive sample recording for the live demonstration.
- Include actual evaluation results and known limitations in the presentation.
- Keep local environment files, private recordings, generated personal data, and credentials out of version control.

---

**ScreenToSOP — from recorded workflows to reviewable procedures.**
