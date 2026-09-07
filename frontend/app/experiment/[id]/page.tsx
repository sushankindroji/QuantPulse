"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Panel, PageHeader, LoadingBlock, ErrorBanner, Button, Stat, SectionLabel, Badge } from "@/components/Panel";
import { useActiveResearch, setActiveResearch, buildActiveResearchFromRegistry } from "@/lib/research-context";

export default function ExperimentDetailPage() {
  const params = useParams();
  const experimentId = params.id as string;
  const [experiment, setExperiment] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    
    async function loadExperiment() {
      try {
        const detail = await api.experimentDetail(experimentId);
        if (!cancelled) {
          setExperiment(detail);
          setActiveResearch(buildActiveResearchFromRegistry(detail));
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e.message || "Failed to load experiment detail");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadExperiment();
    return () => {
      cancelled = true;
    };
  }, [experimentId]);

  async function handleDelete() {
    if (!confirm("Delete this experiment? This cannot be undone.")) {
      return;
    }
    
    setDeleting(true);
    try {
      await api.deleteExperiment(experimentId);
      // Redirect back to experiments list
      window.location.href = "/experiments";
    } catch (e: any) {
      setError(e.message || "Failed to delete experiment");
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="stack">
        <PageHeader
          kicker="Research / Detail"
          title="Experiment"
          description="Loading experiment data…"
        />
        <Panel>
          <LoadingBlock label="Loading experiment…" />
        </Panel>
      </div>
    );
  }

  if (error || !experiment) {
    return (
      <div className="stack">
        <PageHeader
          kicker="Research / Detail"
          title="Experiment"
          description="Unable to load experiment"
        />
        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        <Panel>
          <div style={{ padding: "20px 0", color: "var(--text-2)" }}>
            <p>The experiment could not be found or loaded.</p>
            <div style={{ marginTop: "16px" }}>
              <Link href="/experiments">
                <Button>Back to Experiments</Button>
              </Link>
            </div>
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="stack">
      <PageHeader
        kicker="Research / Detail"
        title={`Experiment ${experiment.experiment_id?.slice(0, 16)}`}
        description="Detailed view of walk-forward research run"
        actions={
          <Link href="/experiments">
            <Button variant="secondary" size="sm">
              Back to Registry
            </Button>
          </Link>
        }
      />

      <div className="card-grid-4">
        <Panel className="metric-card">
          <Stat label="Instrument" value={experiment.instrument ?? "—"} tone="accent" />
        </Panel>
        <Panel className="metric-card">
          <Stat label="Timeframe" value={experiment.timeframe ?? "—"} />
        </Panel>
        <Panel className="metric-card">
          <Stat label="Model" value={experiment.model ?? "—"} />
        </Panel>
        <Panel className="metric-card">
          <Stat label="Data mode" value={experiment.data_mode ?? "—"} />
        </Panel>
      </div>

      <div className="card-grid-4">
        <Panel className="metric-card">
          <Stat
            label="Avg net Sharpe"
            value={
              experiment.metrics?.avg_net_sharpe != null
                ? experiment.metrics.avg_net_sharpe.toFixed(3)
                : "—"
            }
            tone={experiment.metrics?.avg_net_sharpe > 0 ? "good" : "default"}
          />
        </Panel>
        <Panel className="metric-card">
          <Stat
            label="Max drawdown"
            value={
              experiment.metrics?.avg_max_drawdown != null
                ? (experiment.metrics.avg_max_drawdown * 100).toFixed(2) + "%"
                : "—"
            }
          />
        </Panel>
        <Panel className="metric-card">
          <Stat label="Walk-forward folds" value={String(experiment.metrics?.n_folds ?? "—")} />
        </Panel>
        <Panel className="metric-card">
          <Stat
            label="Created"
            value={
              experiment.created_at
                ? new Date(experiment.created_at).toLocaleDateString()
                : "—"
            }
          />
        </Panel>
      </div>

      <Panel
        eyebrow="ACTIONS"
        title="Use this experiment"
        subtitle="Make this experiment active and navigate to analysis pages"
      >
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
            onClick={handleDelete}
            disabled={deleting}
            className="delete-button"
          >
            {deleting ? "Deleting…" : "Delete experiment"}
          </Button>
        </div>
      </Panel>

      <Panel eyebrow="DATA" title="Experiment configuration and metrics">
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
          {JSON.stringify(experiment, null, 2)}
        </pre>
      </Panel>
    </div>
  );
}
