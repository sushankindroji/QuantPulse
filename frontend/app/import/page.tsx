"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Panel, PageHeader, Button, ErrorBanner, Badge, Stat, SectionLabel } from "@/components/Panel";
import { buildActiveResearchFromDataset, setActiveResearch, type ActiveDatasetMeta } from "@/lib/research-context";

type Preview = Awaited<ReturnType<typeof api.uploadDataset>>;

export default function ImportDataPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<{ code: string; message: string; severity: string }[]>([]);
  const [needsInstrument, setNeedsInstrument] = useState(false);
  const [instrumentInput, setInstrumentInput] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const doUpload = useCallback(
    async (file: File, instrument?: string) => {
      setUploading(true);
      setError(null);
      setIssues([]);
      setNeedsInstrument(false);
      try {
        const result = await api.uploadDataset(file, instrument);
        setPreview(result);
        setPendingFile(null);
        const datasetMeta: ActiveDatasetMeta = {
          dataset_id: result.dataset_id,
          instrument: result.instrument,
          source_timeframe: result.source_timeframe,
          rows: result.rows,
          start_time: result.start_time,
          end_time: result.end_time,
          timezone: result.timezone,
          is_synthetic: false,
        };
        setActiveResearch(buildActiveResearchFromDataset(datasetMeta));
      } catch (e: any) {
        if (e.detail?.needs_instrument) {
          setNeedsInstrument(true);
          setPendingFile(file);
          setError(e.detail.message);
        } else if (e.detail?.issues) {
          setIssues(e.detail.issues);
          setError(e.detail.message);
        } else {
          setError(e.message || "Upload failed");
        }
      } finally {
        setUploading(false);
      }
    },
    []
  );

  const onFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const file = files[0];
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setNeedsInstrument(false);
      setPendingFile(null);
      setError("Only CSV files are supported.");
      return;
    }
    doUpload(file);
  };

  return (
    <div className="stack">
      <PageHeader
        kicker="Data / Ingestion"
        title="Data Import"
        description="Bring historical market data into QuantPulse. Validation stays on the existing backend; this interface simply makes the workflow clearer."
      />
      {error && !needsInstrument && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {issues.length > 0 && (
        <Panel title="Validation issues">
          <div className="list-clean">
            {issues.map((x, i) => (
              <div className="list-row" key={i}>
                <Badge tone={x.severity === "error" ? "bad" : "warning"}>{x.severity}</Badge>
                <span style={{ color: "var(--text-2)", fontSize: 10 }}>{x.message}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}
      {!preview && (
        <>
          <Panel eyebrow="STEP 01 · UPLOAD" title="Historical market data" subtitle="CSV · standard OHLCV exports · automatic schema detection">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                onFiles(e.dataTransfer.files);
              }}
              className={`upload-zone ${dragOver ? "drag" : ""} ${uploading ? "busy" : ""}`}
            >
              <div className="upload-icon">{uploading ? <div className="loading-orbit" /> : <span>↑</span>}</div>
              <div className="upload-title">{uploading ? "Validating & preparing dataset…" : "Drop your CSV here"}</div>
              <div className="upload-sub">
                or{" "}
                <button onClick={() => inputRef.current?.click()} disabled={uploading}>
                  browse files
                </button>
              </div>
              <div className="upload-meta">Files are sent to the existing dataset validation API. No internal filesystem paths are exposed.</div>
              <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => onFiles(e.target.files)} />
            </div>
            {needsInstrument && pendingFile && (
              <div className="notice-box">
                <SectionLabel>Instrument required</SectionLabel>
                <p>{error}</p>
                <div style={{ display: "flex", gap: 9, marginTop: 10 }}>
                  <input
                    className="field"
                    placeholder="GBP_CAD or EURUSD"
                    value={instrumentInput}
                    onChange={(e) => setInstrumentInput(e.target.value)}
                  />
                  <Button onClick={() => doUpload(pendingFile, instrumentInput.trim() || undefined)} disabled={!instrumentInput.trim() || uploading}>
                    Confirm
                  </Button>
                </div>
              </div>
            )}
          </Panel>
          <Panel eyebrow="WORKFLOW" title="Ingestion pipeline">
            <div className="pipeline">
              <div className="pipeline-step active">
                <b>Upload</b>
                <small>CSV selected</small>
              </div>
              <div className="pipeline-step">
                <b>Validate</b>
                <small>Schema + quality</small>
              </div>
              <div className="pipeline-step">
                <b>Register</b>
                <small>Dataset ID</small>
              </div>
              <div className="pipeline-step">
                <b>Configure</b>
                <small>Research Lab</small>
              </div>
              <div className="pipeline-step">
                <b>Research</b>
                <small>Walk-forward</small>
              </div>
            </div>
          </Panel>
        </>
      )}
      {preview && (
        <Panel
          eyebrow="STEP 02 · READY"
          title="Dataset registered"
          subtitle="Validated and available to the Research Lab"
          action={
            <Badge
              tone={
                preview.data_confidence.status === "DATA_READY"
                  ? "good"
                  : preview.data_confidence.status === "DATA_READY_WITH_CLEANING"
                  ? "warning"
                  : preview.data_confidence.status === "DATA_NEEDS_REVIEW"
                  ? "warning"
                  : "bad"
              }
            >
              {preview.data_confidence.status.replace(/_/g, " ")}
            </Badge>
          }
        >
          <div className="card-grid-4">
            <Stat label="Instrument" value={preview.instrument} tone="accent" />
            <Stat label="Usable rows" value={preview.data_confidence.usable_rows.toLocaleString()} />
            <Stat label="Timeframe" value={preview.source_timeframe} />
            <Stat label="Timezone" value={preview.timezone || "—"} />
          </div>
          {preview.data_confidence.removed_rows > 0 && (
            <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--surface-2)", borderRadius: 6, border: "1px solid var(--line-soft)" }}>
              <div className="split" style={{ marginBottom: 6 }}>
                <SectionLabel>Data cleaning summary</SectionLabel>
                <Badge tone="warning">ROWS REMOVED</Badge>
              </div>
              <div style={{ fontSize: 10, color: "var(--text-2)", lineHeight: 1.8 }}>
                <b>{preview.data_confidence.uploaded_rows.toLocaleString()}</b> rows uploaded → <b>{preview.data_confidence.usable_rows.toLocaleString()}</b> usable →{" "}
                <b style={{ color: "var(--warn)" }}>{preview.data_confidence.removed_rows.toLocaleString()}</b> removed
                {preview.data_confidence.removed_rows > preview.data_confidence.uploaded_rows * 0.05
                  ? " (more than 5% of data removed — review warnings below)"
                  : " (duplicates, invalid OHLC, or gaps)"}
              </div>
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <Badge tone={preview.data_confidence.data_source === "UNKNOWN" ? "default" : "good"}>
              SOURCE:{" "}
              {preview.data_confidence.data_source === "FOREX_SOFTWARE"
                ? "FOREX SOFTWARE / FSB"
                : preview.data_confidence.data_source === "DUKASCOPY"
                ? "DUKASCOPY"
                : "UNKNOWN / CUSTOM"}
            </Badge>
          </div>
          <div style={{ marginTop: 20, paddingTop: 17, borderTop: "1px solid var(--line-soft)" }}>
            <div className="split">
              <SectionLabel>Coverage</SectionLabel>
              <span className="mono" style={{ fontSize: 9, color: "var(--text-3)" }}>
                {preview.start_time?.slice(0, 19)} → {preview.end_time?.slice(0, 19)}
              </span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {preview.columns.map((c) => (
                <Badge key={c}>{c}</Badge>
              ))}
            </div>
          </div>
          {preview.warnings.length > 0 && (
            <div style={{ marginTop: 17, paddingTop: 15, borderTop: "1px solid var(--line-soft)" }}>
              <SectionLabel>Validation notes</SectionLabel>
              {preview.warnings.map((w, i) => (
                <p key={i} style={{ fontSize: 10, color: w.severity === "error" ? "var(--bad)" : "var(--warn)", margin: "5px 0" }}>
                  • {w.message}
                </p>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 9, flexWrap: "wrap", marginTop: 22 }}>
            <Button size="lg" onClick={() => router.push(`/research?dataset_id=${preview.dataset_id}`)}>
              Continue to Research Configuration →
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setPreview(null);
                setError(null);
                setIssues([]);
              }}
            >
              Upload different file
            </Button>
          </div>
        </Panel>
      )}
      <Panel eyebrow="SOURCE" title="Historical data source" subtitle="Forex Software is the recommended source — it provides long historical series in one file.">
        <div className="card-grid-2">
          <div>
            <SectionLabel>Forex Software / FSB (recommended)</SectionLabel>
            <ol style={{ paddingLeft: 18, color: "var(--text-2)", fontSize: 10, lineHeight: 1.9 }}>
              <li>
                Open{" "}
                <a className="link-accent" href="https://forexsb.com/historical-forex-data" target="_blank" rel="noreferrer">
                  Forex Strategy Builder Historical Data
                </a>
                .
              </li>
              <li>Download the full historical export for your pair (files up to ~200,000 bars are supported).</li>
              <li>
                Upload the file as-is — separate Date/Time columns and numeric-period filenames (e.g. <code className="mono">EURUSD1440.csv</code>) are auto-detected.
              </li>
              <li>Optionally narrow the research window afterwards with the Dataset Range selector below — no need to re-download a shorter file.</li>
            </ol>
          </div>
          <div>
            <SectionLabel>Dukascopy (also supported)</SectionLabel>
            <ol style={{ paddingLeft: 18, color: "var(--text-2)", fontSize: 10, lineHeight: 1.9 }}>
              <li>
                Open{" "}
                <a className="link-accent" href="https://www.dukascopy.com/swiss/english/marketwatch/historical/" target="_blank" rel="noreferrer">
                  Dukascopy Historical Data Export
                </a>
                .
              </li>
              <li>Select a currency pair and date range.</li>
              <li>Export as CSV and upload it here.</li>
            </ol>
          </div>
        </div>
      </Panel>
    </div>
  );
}
