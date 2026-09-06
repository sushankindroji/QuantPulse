"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Panel, PageHeader, LoadingBlock, ErrorBanner, EmptyState, Badge, Button, Stat, SectionLabel } from "@/components/Panel";
import { ResearchJourney } from "@/components/ResearchJourney";
import { useActiveResearch, setActiveResearch, buildActiveResearchFromRegistry } from "@/lib/research-context";

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const active = useActiveResearch();

  useEffect(() => {
    let c = false;
    api
      .experiments(50)
      .then((r) => {
        if (!c) setExperiments(r.experiments ?? []);
      })
      .catch((e: any) => {
        if (!c) setError(e.message || "Failed to load experiments");
      })
      .finally(() => {
        if (!c) setLoading(false);
      });
    return () => {
      c = true;
    };
  }, []);

  async function openDetail(id: string) {
    setDetailLoading(true);
    try {
      const detail = await api.experimentDetail(id);
      setSelected(detail);
      setActiveResearch(buildActiveResearchFromRegistry(detail));
    } catch (e: any) {
      setError(e.message || "Failed to load experiment detail");
    } finally {
      setDetailLoading(false);
    }
  }

  function handleDelete(id: string) {
    if (!confirm("Delete this experiment? This cannot be undone.")) {
      return;
    }
    setDeleting(id);
    api
      .deleteExperiment(id)
      .then(() => {
        setExperiments((prev) => prev.filter((exp) => exp.experiment_id !== id));
        if (selected?.experiment_id === id) {
          setSelected(null);
        }
        setError(null);
      })
      .catch((err: any) => {
        setError(err.message || "Failed to delete experiment");
      })
      .finally(() => {
        setDeleting(null);
      });
  }

  return (
    <div className="stack">
      <ResearchJourney current="experiments" />
      <PageHeader
        kicker="Research / Registry"
        title="Experiments"
        description="A durable record of walk-forward runs, their configuration and the net evidence they produced. Select a row to make it the active experiment across the app."
        actions={<Link href="/research"><Button>New Research +</Button></Link>}
      />
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {loading && (
        <Panel>
          <LoadingBlock label="Loading experiment registry…" />
        </Panel>
      )}
      {!loading && !error && (
        <>
          <div className="metric-grid">
            <Panel className="metric-card">
              <Stat label="Registered runs" value={String(experiments.length)} hint="Current API window" />
            </Panel>
            <Panel className="metric-card">
              <Stat label="Latest instrument" value={experiments[0]?.instrument ?? "—"} tone="accent" />
            </Panel>
            <Panel className="metric-card">
              <Stat
                label="Latest Sharpe"
                value={
                  experiments[0]?.metrics?.avg_net_sharpe != null
                    ? experiments[0].metrics.avg_net_sharpe.toFixed(3)
                    : "—"
                }
                tone={experiments[0]?.metrics?.avg_net_sharpe > 0 ? "good" : "default"}
              />
            </Panel>
            <Panel className="metric-card">
              <Stat label="Data mode" value={experiments[0]?.data_mode ?? "—"} hint="Latest run" />
            </Panel>
          </div>
          <Panel
            eyebrow="REGISTRY"
            title="Recent research runs"
            subtitle="Select a row to inspect detail and make it the active experiment. Full fold-level evidence (used by Alpha/Backtest/Execution) is only available for the experiment you most recently ran in this session."
          >
            {experiments.length === 0 ? (
              <EmptyState
                title="No experiments yet"
                description="Run a walk-forward research job from the Research Lab to populate the registry."
                action={
                  <Link href="/research">
                    <Button>Open Research Lab</Button>
                  </Link>
                }
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Instrument</th>
                      <th>Timeframe</th>
                      <th>Model</th>
                      <th>Data mode</th>
                      <th>Avg net Sharpe</th>
                      <th>Max DD</th>
                      <th>Folds</th>
                      <th>Created</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {experiments.map((e) => (
                      <tr
                        key={e.experiment_id}
                        onClick={() => openDetail(e.experiment_id)}
                        style={{
                          cursor: "pointer",
                          background:
                            active?.experiment_id === e.experiment_id
                              ? "rgba(125,211,252,.06)"
                              : undefined,
                        }}
                      >
                        <td className="mono link-accent">
                          {e.experiment_id?.slice(0, 12) ?? "—"}
                          {active?.experiment_id === e.experiment_id && (
                            <Badge tone="accent">ACTIVE</Badge>
                          )}
                        </td>
                        <td>{e.instrument ?? "—"}</td>
                        <td>{e.timeframe ?? "—"}</td>
                        <td>
                          <Badge>{e.model ?? "—"}</Badge>
                        </td>
                        <td>{e.data_mode ?? "—"}</td>
                        <td
                          className="mono"
                          style={{
                            color:
                              e.metrics?.avg_net_sharpe > 0
                                ? "var(--good)"
                                : e.metrics?.avg_net_sharpe < 0
                                ? "var(--bad)"
                                : "var(--text-2)",
                          }}
                        >
                          {e.metrics?.avg_net_sharpe != null
                            ? e.metrics.avg_net_sharpe.toFixed(3)
                            : "—"}
                        </td>
                        <td className="mono">
                          {e.metrics?.avg_max_drawdown != null
                            ? (e.metrics.avg_max_drawdown * 100).toFixed(2) + "%"
                            : "—"}
                        </td>
                        <td className="mono">{e.metrics?.n_folds ?? "—"}</td>
                        <td>
                          {e.created_at
                            ? new Date(e.created_at).toLocaleString()
                            : "—"}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(ev) => {
                              ev.stopPropagation();
                              handleDelete(e.experiment_id);
                            }}
                            disabled={deleting === e.experiment_id}
                            className="delete-button"
                          >
                            {deleting === e.experiment_id ? "…" : "Delete"}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
      {(selected || detailLoading) && (
        <Panel
          eyebrow="DETAIL"
          title={
            detailLoading
              ? "Loading experiment…"
              : `Experiment ${selected?.experiment_id?.slice(0, 16)}`
          }
          action={
            !detailLoading && (
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
            )
          }
        >
          {detailLoading ? (
            <LoadingBlock label="Fetching experiment detail…" />
          ) : (
            selected && (
              <div className="stack">
                <div className="card-grid-4">
                  <Stat label="Instrument" value={selected.instrument ?? "—"} tone="accent" />
                  <Stat label="Model" value={selected.model ?? "—"} />
                  <Stat label="Data mode" value={selected.data_mode ?? "—"} />
                  <Stat
                    label="Created"
                    value={
                      selected.created_at
                        ? new Date(selected.created_at).toLocaleDateString()
                        : "—"
                    }
                  />
                </div>
                <div style={{ display: "flex", gap: 9, flexWrap: "wrap" }}>
                  <Link href="/alpha">
                    <Button size="sm">Open in Alpha Explorer →</Button>
                  </Link>
                  <Link href="/backtest">
                    <Button size="sm" variant="secondary">
                      Open in Backtest →
                    </Button>
                  </Link>
                  <Link href="/execution">
                    <Button size="sm" variant="secondary">
                      Open in Execution →
                    </Button>
                  </Link>
                  <Link href="/paper">
                    <Button size="sm" variant="secondary">
                      Open in Paper Trading →
                    </Button>
                  </Link>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDelete(selected.experiment_id)}
                    disabled={deleting === selected.experiment_id}
                    className="delete-button"
                  >
                    {deleting === selected.experiment_id ? "Deleting…" : "Delete experiment"}
                  </Button>
                </div>
                <p
                  style={{
                    fontSize: 10,
                    color: "var(--text-3)",
                    lineHeight: 1.6,
                  }}
                >
                  This experiment is now your active context — those pages will load its summary metrics
                  automatically. Fold-level signal/backtest/cost detail is only available if this was the
                  experiment most recently run in Research Lab this session.
                </p>
                <SectionLabel>Returned payload</SectionLabel>
                <pre
                  style={{
                    margin: 0,
                    padding: 14,
                    borderRadius: 11,
                    border: "1px solid var(--line-soft)",
                    background: "var(--surface-soft)",
                    color: "var(--text-2)",
                    fontSize: 9,
                    lineHeight: 1.55,
                    overflow: "auto",
                    maxHeight: 420,
                  }}
                >
                  {JSON.stringify(selected, null, 2)}
                </pre>
              </div>
            )
          )}
        </Panel>
      )}
    </div>
  );
}
