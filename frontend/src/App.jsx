
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileText,
  Film,
  Info,
  Monitor,
  Play,
  RotateCcw,
  ShieldCheck,
  Square,
  Upload,
  Video,
  X,
} from "lucide-react";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const ACCEPTED_VIDEO_TYPES = [
  ".mp4",
  ".mov",
  ".mkv",
  ".avi",
  ".webm",
];

const READINESS_LABELS = {
  demo_ready: "Demo-ready",
  needs_review: "Needs manual review",
  not_ready: "Not ready",
};

function getReadinessTone(readiness) {
  if (readiness === "demo_ready") return "success";
  if (readiness === "not_ready") return "danger";
  return "warning";
}

function getArtifactUrl(result, keys) {
  const artifacts = result?.artifacts || result?.downloads || {};

  for (const key of keys) {
    const value =
      artifacts[key] ??
      result?.[key] ??
      result?.output?.[key];

    if (typeof value === "string" && value.trim()) {
      if (/^https?:\/\//i.test(value)) return value;
      return `${API_BASE_URL}${value.startsWith("/") ? "" : "/"}${value}`;
    }
  }

  return null;
}

function getWorkflowSteps(result) {
  const candidates = [
    result?.workflow?.steps,
    result?.steps,
    result?.workflow?.workflow_steps,
    result?.data?.workflow?.steps,
  ];

  return candidates.find(Array.isArray) || [];
}

function getStepDescription(step) {
  return (
    step?.action_description ||
    step?.description ||
    step?.action ||
    step?.instruction ||
    step?.title ||
    "No description was provided for this step."
  );
}

function getStepScreenshot(step, jobId) {
  const value =
    step?.screenshot_url ||
    step?.screenshot ||
    step?.image_url ||
    step?.screenshot_path ||
    null;

  if (!value || typeof value !== "string") return null;

  if (/^https?:\/\//i.test(value)) return value;

  // If the backend returned a local path inside this job directory,
  // convert it to the API's screenshot-serving URL.
  const marker = jobId ? `/jobs/${jobId}/` : "";
  const markerIndex = marker ? value.indexOf(marker) : -1;

  if (markerIndex >= 0) {
    const relativePath = value.slice(markerIndex + marker.length);
    return `${API_BASE_URL}/jobs/${jobId}/screenshots/${relativePath
      .split("/")
      .map(encodeURIComponent)
      .join("/")}`;
  }

  // Already a relative API URL.
  if (value.startsWith("/jobs/")) return `${API_BASE_URL}${value}`;

  return null;
}

function App() {
  const [processName, setProcessName] = useState("");
  const [targetAudience, setTargetAudience] = useState("New employee");
  const [departmentNotes, setDepartmentNotes] = useState("");
  const [videoFile, setVideoFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState(null);
  const [activeTab, setActiveTab] = useState("steps");
  const [dragActive, setDragActive] = useState(false);

  const fileInputRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const recordingTimerRef = useRef(null);
  const previewUrlRef = useRef("");

  useEffect(() => {
    return () => {
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }

      if (recorderRef.current?.state === "recording") {
        recorderRef.current.stop();
      }

      streamRef.current?.getTracks().forEach((track) => track.stop());

      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    };
  }, []);

  function setSelectedVideo(file) {
    if (!file) return;

    const extension = `.${file.name.split(".").pop()}`.toLowerCase();

    if (!ACCEPTED_VIDEO_TYPES.includes(extension)) {
      setErrorMessage(
        "Unsupported video format. Choose an MP4, MOV, MKV, AVI, or WebM file."
      );
      return;
    }

    if (file.size === 0) {
      setErrorMessage("The selected video is empty. Choose another file.");
      return;
    }

    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
    }

    const url = URL.createObjectURL(file);
    previewUrlRef.current = url;

    setVideoFile(file);
    setPreviewUrl(url);
    setResult(null);
    setErrorMessage("");
  }

  function clearVideo() {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = "";
    }

    setVideoFile(null);
    setPreviewUrl("");
    setResult(null);
    setErrorMessage("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function startRecording() {
    setErrorMessage("");

    if (!navigator.mediaDevices?.getDisplayMedia) {
      setErrorMessage(
        "Screen recording is not supported in this browser. Try a recent version of Chrome or Edge, or upload a recording instead."
      );
      return;
    }

    if (typeof MediaRecorder === "undefined") {
      setErrorMessage(
        "This browser cannot record screen video. You can still upload an existing recording."
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          frameRate: { ideal: 10, max: 15 },
        },
        audio: false,
      });

      streamRef.current = stream;
      chunksRef.current = [];

      const supportedTypes = [
        "video/webm;codecs=vp9",
        "video/webm;codecs=vp8",
        "video/webm",
      ];

      const mimeType = supportedTypes.find((type) =>
        MediaRecorder.isTypeSupported(type)
      );

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        setErrorMessage(
          "The browser encountered an error while recording. Please try again or upload a video."
        );
        setIsRecording(false);
      };

      recorder.onstop = () => {
        const actualMimeType = recorder.mimeType || "video/webm";
        const blob = new Blob(chunksRef.current, {
          type: actualMimeType,
        });

        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;

        if (blob.size > 0) {
          const file = new File(
            [blob],
            `screen-recording-${Date.now()}.webm`,
            { type: actualMimeType }
          );
          setSelectedVideo(file);
        }

        setIsRecording(false);
        setRecordingSeconds(0);

        if (recordingTimerRef.current) {
          clearInterval(recordingTimerRef.current);
          recordingTimerRef.current = null;
        }
      };

      const videoTrack = stream.getVideoTracks()[0];

      if (videoTrack) {
        videoTrack.addEventListener(
          "ended",
          () => {
            if (recorder.state === "recording") {
              recorder.stop();
            }
          },
          { once: true }
        );
      }

      recorder.start(1000);
      setIsRecording(true);
      setRecordingSeconds(0);

      recordingTimerRef.current = setInterval(() => {
        setRecordingSeconds((seconds) => seconds + 1);
      }, 1000);
    } catch (error) {
      if (error?.name === "NotAllowedError") {
        setErrorMessage(
          "Screen sharing was cancelled or permission was denied. Allow screen sharing or upload a video instead."
        );
      } else {
        setErrorMessage(
          error?.message ||
          "Could not start screen recording. Please try again."
        );
      }
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
  }

  function formatDuration(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(
      seconds
    ).padStart(2, "0")}`;
  }

  async function generateSOP(event) {
    event.preventDefault();

    if (!videoFile) {
      setErrorMessage("Record your screen or select a video first.");
      return;
    }

    setIsGenerating(true);
    setErrorMessage("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("video", videoFile);
      formData.append("process_name", processName.trim());
      formData.append("target_audience", targetAudience.trim());
      formData.append("department_notes", departmentNotes.trim());

      const response = await fetch(`${API_BASE_URL}/record-to-sop`, {
        method: "POST",
        body: formData,
      });

      const responseText = await response.text();
      let responseData = {};

      try {
        responseData = responseText ? JSON.parse(responseText) : {};
      } catch {
        responseData = { detail: responseText };
      }

      if (!response.ok) {
        const detail =
          responseData?.detail ||
          responseData?.message ||
          `The server returned HTTP ${response.status}.`;

        throw new Error(
          typeof detail === "string"
            ? detail
            : JSON.stringify(detail)
        );
      }

      setResult(responseData);
      setActiveTab("steps");
    } catch (error) {
      setErrorMessage(
        error?.message ||
        "Could not connect to the Screen-to-SOP API. Confirm that the backend is running and try again."
      );
    } finally {
      setIsGenerating(false);
    }
  }

  function resetWorkspace() {
    if (isRecording) {
      stopRecording();
    }

    setProcessName("");
    setTargetAudience("New employee");
    setDepartmentNotes("");
    clearVideo();
    setResult(null);
    setErrorMessage("");
    setActiveTab("steps");
  }

  const steps = getWorkflowSteps(result);
  const readiness =
    result?.readiness ||
    result?.cleanup_report?.readiness ||
    result?.workflow?.readiness ||
    result?.meta?.cleanup_report?.readiness ||
    "needs_review";

  const warnings = [
    ...(Array.isArray(result?.warnings) ? result.warnings : []),
    ...(Array.isArray(result?.meta?.warnings) ? result.meta.warnings : []),
    ...(Array.isArray(result?.cleanup_report?.warnings)
      ? result.cleanup_report.warnings
      : []),
  ].filter((warning, index, all) => all.indexOf(warning) === index);

  const docxUrl = getArtifactUrl(result, [
    "docx",
    "docx_url",
    "sop_docx",
    "sop_docx_url",
    "document_url",
    "download_url",
  ]);

  const markdownUrl = getArtifactUrl(result, [
    "markdown",
    "markdown_url",
    "md",
    "md_url",
    "sop_md",
    "sop_md_url",
  ]);

  const workflowUrl = getArtifactUrl(result, [
    "workflow_json",
    "workflow_url",
    "json_url",
  ]);

  const jobId = result?.job_id || result?.id || result?.job?.id;
  const generationMode =
    result?.generation_mode ||
    result?.cleanup_report?.generation_mode ||
    result?.meta?.generation_mode;

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Screen to SOP home">
          <span className="brand-mark">
            <FileText size={23} strokeWidth={2.2} />
          </span>
          <span className="brand-copy">
            <span className="brand-name">Screen<span>to</span>SOP</span>
            <span className="brand-caption">WORKFLOW DOCUMENTATION</span>
          </span>
        </a>

        <div className="topbar-right">
          <span className="local-badge">
            <span className="status-dot" />
            Local processing
          </span>
          <span className="topbar-divider" />
          <span className="version-label">Workspace</span>
        </div>
      </header>

      <main className="page-content">
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="eyebrow-line" />
              FROM SCREEN RECORDING TO STANDARD PROCEDURE
            </div>
            <h1>
              Turn your workflow
              <br />
              into a <span>repeatable SOP.</span>
            </h1>
            <p className="hero-description">
              Record a process or upload a video. Generate a step-by-step
              procedure with screenshots that helps someone else do the same
              task.
            </p>

            <div className="hero-points">
              <span><Check size={15} /> Step-by-step instructions</span>
              <span><Check size={15} /> Screenshot-backed output</span>
              <span><Check size={15} /> Editable Word document</span>
            </div>
          </div>

          <div className="hero-visual" aria-hidden="true">
            <div className="visual-window">
              <div className="visual-window-bar">
                <span className="window-dot" />
                <span className="window-dot" />
                <span className="window-dot" />
                <span className="visual-window-title">Process overview</span>
              </div>
              <div className="visual-body">
                <div className="visual-sidebar">
                  <span className="visual-side-icon active"><Monitor size={15} /></span>
                  <span className="visual-side-icon"><FileText size={15} /></span>
                  <span className="visual-side-icon"><Activity size={15} /></span>
                </div>
                <div className="visual-document">
                  <div className="visual-doc-heading" />
                  <div className="visual-doc-subheading" />
                  <div className="visual-step">
                    <span>01</span>
                    <div>
                      <i />
                      <b />
                    </div>
                    <CheckCircle2 size={17} />
                  </div>
                  <div className="visual-step">
                    <span>02</span>
                    <div>
                      <i />
                      <b />
                    </div>
                    <CheckCircle2 size={17} />
                  </div>
                  <div className="visual-step">
                    <span>03</span>
                    <div>
                      <i />
                      <b />
                    </div>
                    <Clock3 size={17} />
                  </div>
                  <div className="visual-doc-footer">
                    <span />
                    <span />
                  </div>
                </div>
              </div>
              <div className="visual-status">
                <span className="visual-status-icon"><Check size={14} /></span>
                <span>Procedure structure ready</span>
              </div>
            </div>
            <div className="visual-float visual-float-top">
              <span className="float-icon"><Video size={16} /></span>
              <span><b>Screen capture</b><small>Video input</small></span>
            </div>
            <div className="visual-float visual-float-bottom">
              <span className="float-icon document-float"><FileText size={17} /></span>
              <span><b>SOP document</b><small>DOCX output</small></span>
              <CheckCircle2 size={17} className="float-check" />
            </div>
          </div>
        </section>

        <section className="workspace-grid">
          <div className="main-column">
            <div className="section-heading">
              <div>
                <div className="section-kicker">01 / INPUT</div>
                <h2>Create your procedure</h2>
                <p>Start with a recording, then add context for a more useful SOP.</p>
              </div>
              <span className="step-count">STEP 1 OF 2</span>
            </div>

            <form onSubmit={generateSOP}>
              <section className="panel source-panel">
                <div className="panel-heading">
                  <div className="panel-icon"><Video size={19} /></div>
                  <div>
                    <h3>Screen recording</h3>
                    <p>Capture a process live or upload a saved video.</p>
                  </div>
                </div>

                <div className="source-options">
                  <button
                    type="button"
                    className={`source-option ${isRecording ? "source-option-active" : ""}`}
                    onClick={isRecording ? stopRecording : startRecording}
                    disabled={isGenerating}
                  >
                    <span className={`source-option-icon ${isRecording ? "recording-icon" : ""}`}>
                      {isRecording ? <Square size={18} /> : <Monitor size={19} />}
                    </span>
                    <span className="source-option-copy">
                      <strong>{isRecording ? "Stop recording" : "Record your screen"}</strong>
                      <small>
                        {isRecording
                          ? `Recording in progress · ${formatDuration(recordingSeconds)}`
                          : "Choose a screen or application window"}
                      </small>
                    </span>
                    {isRecording ? (
                      <span className="recording-indicator"><span /> REC</span>
                    ) : (
                      <ChevronRight size={18} className="option-chevron" />
                    )}
                  </button>

                  <div className="source-separator"><span>OR</span></div>

                  <button
                    type="button"
                    className={`upload-zone ${dragActive ? "upload-zone-active" : ""}`}
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setDragActive(true);
                    }}
                    onDragLeave={() => setDragActive(false)}
                    onDrop={(event) => {
                      event.preventDefault();
                      setDragActive(false);
                      setSelectedVideo(event.dataTransfer.files?.[0]);
                    }}
                    disabled={isGenerating || isRecording}
                  >
                    <span className="upload-icon"><Upload size={21} /></span>
                    <span className="upload-copy">
                      <strong>Click to upload <span>or drag and drop</span></strong>
                      <small>MP4, MOV, MKV, AVI or WebM</small>
                    </span>
                    <span className="upload-action">Browse files</span>
                  </button>

                  <input
                    ref={fileInputRef}
                    className="visually-hidden"
                    type="file"
                    accept={ACCEPTED_VIDEO_TYPES.join(",")}
                    onChange={(event) => {
                      setSelectedVideo(event.target.files?.[0]);
                      event.target.value = "";
                    }}
                  />
                </div>

                {previewUrl && videoFile && (
                  <div className="selected-video">
                    <video
                      className="video-preview"
                      src={previewUrl}
                      controls
                      preload="metadata"
                    />
                    <div className="selected-video-info">
                      <span className="file-icon"><Film size={19} /></span>
                      <span className="selected-video-name">
                        <strong>{videoFile.name}</strong>
                        <small>{(videoFile.size / (1024 * 1024)).toFixed(2)} MB · Ready to process</small>
                      </span>
                      <button
                        type="button"
                        className="icon-button"
                        onClick={clearVideo}
                        aria-label="Remove selected video"
                        disabled={isGenerating}
                      >
                        <X size={18} />
                      </button>
                    </div>
                  </div>
                )}

                <div className="privacy-note">
                  <ShieldCheck size={16} />
                  <span>
                    Screen recording requires your browser's permission. Select
                    only the screen or window you intend to document.
                  </span>
                </div>
              </section>

              <section className="panel details-panel">
                <div className="panel-heading">
                  <div className="panel-icon"><FileText size={19} /></div>
                  <div>
                    <h3>Process details</h3>
                    <p>Give the generated instructions a clear purpose and audience.</p>
                  </div>
                </div>

                <div className="form-field">
                  <label htmlFor="process-name">Process name <span className="optional-label">Optional</span></label>
                  <input
                    id="process-name"
                    type="text"
                    placeholder="e.g. Review and export a vendor invoice"
                    value={processName}
                    onChange={(event) => setProcessName(event.target.value)}
                    maxLength={200}
                    disabled={isGenerating}
                  />
                  <span className="field-hint">Leave blank if you want the workflow to derive a name.</span>
                </div>

                <div className="form-row">
                  <div className="form-field">
                    <label htmlFor="target-audience">Target audience</label>
                    <input
                      id="target-audience"
                      type="text"
                      placeholder="e.g. New employee"
                      value={targetAudience}
                      onChange={(event) => setTargetAudience(event.target.value)}
                      maxLength={200}
                      disabled={isGenerating}
                    />
                  </div>

                  <div className="form-field">
                    <label htmlFor="department-notes">Department / system notes <span className="optional-label">Optional</span></label>
                    <input
                      id="department-notes"
                      type="text"
                      placeholder="e.g. AP team, SAP and Excel"
                      value={departmentNotes}
                      onChange={(event) => setDepartmentNotes(event.target.value)}
                      maxLength={500}
                      disabled={isGenerating}
                    />
                  </div>
                </div>
              </section>

              {errorMessage && (
                <div className="error-banner" role="alert">
                  <AlertCircle size={19} />
                  <div>
                    <strong>Something needs your attention</strong>
                    <p>{errorMessage}</p>
                  </div>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => setErrorMessage("")}
                    aria-label="Dismiss error"
                  >
                    <X size={17} />
                  </button>
                </div>
              )}

              <div className="generate-row">
                <div className="generate-explainer">
                  <Info size={16} />
                  <span>Review the generated steps before using them as a final procedure.</span>
                </div>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={!videoFile || isGenerating || isRecording}
                >
                  {isGenerating ? (
                    <>
                      <span className="button-spinner" />
                      Generating SOP...
                    </>
                  ) : (
                    <>
                      <Play size={17} fill="currentColor" />
                      Generate SOP
                    </>
                  )}
                </button>
              </div>
            </form>

            {isGenerating && (
              <section className="panel processing-panel" aria-live="polite">
                <div className="processing-animation"><Activity size={23} /></div>
                <div>
                  <h3>Working on your procedure</h3>
                  <p>
                    The API is processing the recording and preparing the
                    available workflow outputs. Processing time depends on the
                    video and local model configuration.
                  </p>
                </div>
              </section>
            )}

            {result && (
              <section className="results-section" aria-live="polite">
                <div className="section-heading result-heading">
                  <div>
                    <div className="section-kicker">02 / OUTPUT</div>
                    <h2>Your generated SOP</h2>
                    <p>Review the returned workflow and download available files.</p>
                  </div>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={resetWorkspace}
                  >
                    <RotateCcw size={15} /> New SOP
                  </button>
                </div>

                <div className="result-summary panel">
                  <div className="result-summary-top">
                    <span className="result-summary-icon"><CheckCircle2 size={22} /></span>
                    <div className="result-summary-copy">
                      <h3>{processName.trim() || "Generated procedure"}</h3>
                      <p>
                        {jobId ? `Job ID: ${jobId}` : "Processing response received"}
                      </p>
                    </div>
                    <span className={`readiness-badge ${getReadinessTone(readiness)}`}>
                      <span />
                      {READINESS_LABELS[readiness] || readiness.replaceAll("_", " ")}
                    </span>
                  </div>

                  <div className="result-metrics">
                    <div>
                      <span className="metric-value">{steps.length}</span>
                      <span className="metric-label">Workflow steps</span>
                    </div>
                    <div>
                      <span className="metric-value">{warnings.length}</span>
                      <span className="metric-label">Warnings returned</span>
                    </div>
                    <div>
                      <span className="metric-value">{generationMode ? generationMode.replaceAll("_", " ") : "Reported by API"}</span>
                      <span className="metric-label">Generation mode</span>
                    </div>
                  </div>
                </div>

                {warnings.length > 0 && (
                  <div className="warning-banner">
                    <AlertCircle size={19} />
                    <div>
                      <strong>Review before relying on this procedure</strong>
                      <ul>
                        {warnings.map((warning, index) => (
                          <li key={`${index}-${String(warning)}`}>{String(warning)}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                <div className="panel output-panel">
                  <div className="output-tabs" role="tablist" aria-label="SOP output views">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === "steps"}
                      className={activeTab === "steps" ? "output-tab active" : "output-tab"}
                      onClick={() => setActiveTab("steps")}
                    >
                      Workflow steps <span>{steps.length}</span>
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === "files"}
                      className={activeTab === "files" ? "output-tab active" : "output-tab"}
                      onClick={() => setActiveTab("files")}
                    >
                      Downloads
                    </button>
                  </div>

                  {activeTab === "steps" && (
                    <div className="steps-list">
                      {steps.length > 0 ? (
                        steps.map((step, index) => {
                          const screenshot = getStepScreenshot(step, jobId);

                          return (
                            <article className="workflow-step" key={step.step_number ?? step.step ?? index}>
                              <div className="step-number">
                                {String(step.step_number ?? step.step ?? index + 1).padStart(2, "0")}
                              </div>
                              <div className="step-content">
                                <div className="step-content-top">
                                  <h4>{getStepDescription(step)}</h4>
                                  {step.timestamp && (
                                    <span className="step-timestamp"><Clock3 size={13} /> {step.timestamp}</span>
                                  )}
                                </div>

                                {step.ui_element && (
                                  <p className="step-ui-element">
                                    <Monitor size={14} /> UI element: {step.ui_element}
                                  </p>
                                )}

                                {step.note && <p className="step-note">{step.note}</p>}


                                {screenshot && (
                                  <div className="step-screenshot">
                                    <img
                                      src={screenshot}
                                      alt={`Evidence screenshot for step ${index + 1}`}
                                      loading="lazy"
                                      onError={(event) => {
                                        event.currentTarget.style.display = "none";
                                        const fallback = event.currentTarget.nextElementSibling;
                                        if (fallback) fallback.hidden = false;
                                      }}
                                    />
                                    <p className="screenshot-unavailable" hidden>
                                      Evidence screenshot unavailable for this step.
                                    </p>
                                  </div>
                                )}

                              </div>
                            </article>
                          );
                        })
                      ) : (
                        <div className="empty-steps">
                          <CircleHelp size={25} />
                          <h3>No structured steps were found in the response</h3>
                          <p>
                            The API returned a successful response, but its
                            workflow steps were not available in the expected
                            fields. Check the API response structure before
                            assuming the procedure is complete.
                          </p>
                          <pre>{JSON.stringify(result, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === "files" && (
                    <div className="download-list">
                      {docxUrl && (
                        <a className="download-item" href={docxUrl} target="_blank" rel="noreferrer">
                          <span className="download-file-icon docx-icon"><FileText size={21} /></span>
                          <span className="download-file-copy">
                            <strong>Word document</strong>
                            <small>Editable SOP · DOCX</small>
                          </span>
                          <ArrowDownToLine size={19} />
                        </a>
                      )}

                      {markdownUrl && (
                        <a className="download-item" href={markdownUrl} target="_blank" rel="noreferrer">
                          <span className="download-file-icon markdown-icon"><FileText size={21} /></span>
                          <span className="download-file-copy">
                            <strong>Markdown document</strong>
                            <small>Text-based SOP · MD</small>
                          </span>
                          <ArrowDownToLine size={19} />
                        </a>
                      )}

                      {workflowUrl && (
                        <a className="download-item" href={workflowUrl} target="_blank" rel="noreferrer">
                          <span className="download-file-icon json-icon"><Activity size={21} /></span>
                          <span className="download-file-copy">
                            <strong>Workflow data</strong>
                            <small>Structured output · JSON</small>
                          </span>
                          <ArrowDownToLine size={19} />
                        </a>
                      )}

                      {!docxUrl && !markdownUrl && !workflowUrl && (
                        <div className="empty-downloads">
                          <Info size={22} />
                          <strong>No downloadable artifact links were returned.</strong>
                          <p>
                            The frontend needs the artifact URLs exposed by
                            the API response. The raw response is shown below
                            to help align the interface with the actual API.
                          </p>
                          <pre>{JSON.stringify(result, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </section>
            )}
          </div>

          <aside className="side-column">
            <section className="panel workflow-guide">
              <div className="side-panel-heading">
                <span className="side-heading-icon"><Activity size={18} /></span>
                <h3>How it works</h3>
              </div>

              <div className="guide-step">
                <span className="guide-number">01</span>
                <div>
                  <strong>Capture the workflow</strong>
                  <p>Record the screen or choose an existing video.</p>
                </div>
              </div>
              <div className="guide-connector" />
              <div className="guide-step">
                <span className="guide-number">02</span>
                <div>
                  <strong>Generate instructions</strong>
                  <p>The backend analyzes the recording and builds a draft.</p>
                </div>
              </div>
              <div className="guide-connector" />
              <div className="guide-step">
                <span className="guide-number">03</span>
                <div>
                  <strong>Review and export</strong>
                  <p>Check the steps and download available artifacts.</p>
                </div>
              </div>
            </section>

            <section className="panel output-guide">
              <div className="side-panel-heading">
                <span className="side-heading-icon"><FileText size={18} /></span>
                <h3>Expected outputs</h3>
              </div>
              <div className="output-guide-item">
                <span className="output-type-icon"><FileText size={17} /></span>
                <span><strong>SOP document</strong><small>Editable Word file</small></span>
              </div>
              <div className="output-guide-item">
                <span className="output-type-icon"><Activity size={17} /></span>
                <span><strong>Workflow data</strong><small>Structured steps and metadata</small></span>
              </div>
              <div className="output-guide-item">
                <span className="output-type-icon"><Monitor size={17} /></span>
                <span><strong>Supporting screenshots</strong><small>Visual context for each step</small></span>
              </div>
              <p className="side-note">
                Download options depend on what the backend returns and makes available.
              </p>
            </section>

            <section className="review-note">
              <div className="review-note-icon"><ShieldCheck size={19} /></div>
              <div>
                <strong>Human review matters</strong>
                <p>
                  Generated steps may need correction. Verify the sequence,
                  screenshots, and any sensitive information before sharing
                  the final SOP.
                </p>
              </div>
            </section>

            <div className="help-note">
              <Info size={15} />
              <span>Need help? Make sure the FastAPI server is running on port 8000.</span>
            </div>
          </aside>
        </section>
      </main>

      <footer className="app-footer">
        <span className="footer-brand"><FileText size={15} /> Screen-to-SOP</span>
        <span>Workflow documentation, made easier.</span>
        <span className="footer-status"><span className="status-dot" /> Local API integration</span>
      </footer>
    </div>
  );
}

export default App;
