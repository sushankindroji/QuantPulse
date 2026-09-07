"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Panel, Stat, SyntheticBadge, PageHeader, LoadingBlock, ErrorBanner, Badge, Button, SectionLabel, EmptyState } from "@/components/Panel";
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import Link from "next/link";
import { useActiveResearch } from "@/lib/research-context";
import CandlestickChart from "@/components/CandlestickChart";

// Chart visualization is intentionally capped — this only limits how many
// points are DRAWN, never how many rows are loaded/registered/researched.
// The full dataset (potentially 100k+ rows) is always used by the research
// engine; only this constant affects the on-screen line chart.
const CHART_POINTS = 300;

type ChartType = "line" | "candlestick";

export default function DashboardPage() {
  const active = useActiveResearch();
  const isUploaded = !!active?.dataset && active.dataset.dataset_id !== "demo" && !active.dataset.is_synthetic;
  const datasetId = isUploaded ? active!.dataset!.dataset_id : null;

  const [market, setMarket] = useState<any>(null);
  const [regimeData, setRegimeData] = useState<any>(null);
  const [regimeError, setRegimeError] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartType, setChartType] = useState<ChartType>("line");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRegimeError(null);

    // THE USER'S DATA ALWAYS WINS: if a real uploaded dataset is active,
    // fetch its actual bars and regime read. Only fall back to the demo
    // provider when there genuinely is no active uploaded dataset — never
    // as a silent default that overrides real data.
    const marketCall = datasetId
      ? api.datasetCandles(datasetId, CHART_POINTS)
      : api.marketDemo({ instrument: "GBP_CAD", timeframe: "1h", n_bars: 200 });
    const regimeCall = datasetId
      ? api.regimes({ dataset_id: datasetId })
      : api.regimes({ instrument: "GBP_CAD", timeframe: "1h", n_bars: 200 });

    Promise.all([marketCall, api.experiments(5)]).then(([m, e]) => {
      if (cancelled) return;
      setMarket(m);
      setExperiments(e.experiments ?? []);
    }).catch((e: any) => { if (!cancelled) setError(e.message || "Failed to load the market snapshot"); });

    regimeCall.then((r) => { if (!cancelled) setRegimeData(r); })
      .catch((e: any) => { if (!cancelled) setRegimeError(e.message || "Regime classification unavailable for this dataset"); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [datasetId]);

  const bars = useMemo(() => (market?.bars ?? []).map((b: any, i: number) => ({
    i, 
    close: Number(b.close), 
    open: Number(b.open ?? b.close),
    high: Number(b.high ?? b.close),
    low: Number(b.low ?? b.close),
    label: b.timestamp ?? b.time ?? String(i),
  })), [market]);
  const lastClose = market?.bars?.at(-1)?.close;
  const probs = Object.entries(regimeData?.current_probabilities ?? {}).sort((a: any, b: any) => b[1] - a[1]) as [string, number][];

  const displayInstrument = isUploaded ? active!.instrument : "GBP / CAD";
  const displayTimeframe = isUploaded ? active!.timeframe : "1h";
  const totalRows = market?.total_rows as number | undefined;
  const pointsReturned = market?.points_returned ?? bars.length;

  return (
    <div className="stack">
      <PageHeader
        kicker="Overview / Command center"
        title="Dashboard"
        description={isUploaded ? "Live snapshot of your active uploaded dataset — not the demo series." : "A calm view of the market snapshot, current regime and the latest research evidence."}
        actions={market && (isUploaded
          ? <Badge tone="good">UPLOADED DATA</Badge>
          : <SyntheticBadge isSynthetic={!!market.is_synthetic} />)}
      />
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {loading && <LoadingBlock label={isUploaded ? "Loading your uploaded dataset…" : "Syncing market, regime and research registry…"} />}

      {!loading && !market && !error && (
        <Panel><EmptyState title="No market snapshot available" description="Upload a dataset or try again." action={<Link href="/import"><Button>Go to Data Import →</Button></Link>} /></Panel>
      )}

      {!loading && market && <>
        <div className="dashboard-hero">
          <Panel className="hero-panel" eyebrow="PRIMARY INSTRUMENT">
            <div className="hero-top">
              <div><h2 className="hero-title">{displayInstrument.replace("_", " / ")}</h2><p className="hero-meta">{displayTimeframe} · {pointsReturned} of {totalRows?.toLocaleString() ?? pointsReturned} rows shown on chart</p></div>
              <Badge tone="accent">{isUploaded ? "UPLOADED DATA" : "DEMO / SYNTHETIC"}</Badge>
            </div>
            <div className="price-block"><span className="price">{lastClose != null ? Number(lastClose).toFixed(5) : "—"}</span><span className="price-note">latest close</span></div>
            
            {/* Chart type toggle */}
            <div className="chart-toggle-group">
              <button
                className={`chart-toggle-btn ${chartType === "line" ? "active" : ""}`}
                onClick={() => setChartType("line")}
                type="button"
              >
                Line
              </button>
              <button
                className={`chart-toggle-btn ${chartType === "candlestick" ? "active" : ""}`}
                onClick={() => setChartType("candlestick")}
                type="button"
              >
                Candlestick
              </button>
            </div>

            <div className="chart-shell">
              {chartType === "line" ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={bars} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid vertical={false} stroke="rgba(128,145,160,.12)" />
                    <XAxis dataKey="i" hide />
                    <YAxis domain={['dataMin','dataMax']} hide />
                    <Tooltip 
                      contentStyle={{ 
                        background: "rgba(15,19,24,.94)", 
                        border: "1px solid rgba(255,255,255,.1)", 
                        borderRadius: 10, 
                        fontSize: 10 
                      }} 
                      labelFormatter={() => "Close"} 
                      formatter={(v: any) => [Number(v).toFixed(5), "Price"]} 
                    />
                    <Line type="monotone" dataKey="close" stroke="var(--accent)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <CandlestickChart data={bars} />
              )}
            </div>
          </Panel>
          <Panel className="hero-panel hero-side" eyebrow="REGIME ENGINE">
            {regimeData ? (<>
              <div><div className="split"><span className="stat-label">Current regime</span><span className="status-pill live"><i /> CLASSIFIED</span></div><div className="regime-name">{String(regimeData.current_regime).replaceAll("_", " ")}</div><div className="regime-method">{regimeData.method}</div></div>
              <div><SectionLabel>Posterior probabilities</SectionLabel><div className="list-clean">{probs.slice(0, 4).map(([name, prob]) => <div key={name}><div className="split" style={{marginBottom:6}}><span style={{fontSize:10,textTransform:"capitalize"}}>{name.replaceAll("_", " ")}</span><span className="mono" style={{fontSize:9,color:"var(--text-3)"}}>{(prob*100).toFixed(1)}%</span></div><div className="progress-track"><div className="progress-fill" style={{width:`${Math.max(prob*100,1)}%`}} /></div></div>)}</div></div>
            </>) : (
              <div style={{color:"var(--text-3)",fontSize:10,lineHeight:1.7,padding:"12px 0"}}>{regimeError ?? "Classifying…"}</div>
            )}
          </Panel>
        </div>

        <div className="metric-grid">
          <Panel className="metric-card"><Stat label="Last close" value={lastClose != null ? Number(lastClose).toFixed(5) : "—"} tone="accent" hint="Latest available bar" /></Panel>
          <Panel className="metric-card"><Stat label="Rows loaded (full dataset)" value={totalRows != null ? totalRows.toLocaleString() : String(bars.length)} hint="Used in full by the research engine" /></Panel>
          <Panel className="metric-card"><Stat label="Points on chart" value={String(pointsReturned)} hint="Visually downsampled for rendering only" /></Panel>
          <Panel className="metric-card"><Stat label="Data source" value={isUploaded ? "Uploaded CSV" : (market.source || "—")} hint={isUploaded ? active!.instrument : (market.is_synthetic ? "Synthetic dataset" : "Market dataset")} /></Panel>
        </div>

        <div className="card-grid-2">
          <Panel title="Research pipeline" subtitle="The product flow from raw market information to evidence.">
            <div className="pipeline"><div className="pipeline-step active"><b>Market</b><small>Data snapshot</small></div><div className="pipeline-step"><b>Research</b><small>Walk-forward</small></div><div className="pipeline-step"><b>Alpha</b><small>Signal evidence</small></div><div className="pipeline-step"><b>Backtest</b><small>Net of costs</small></div><div className="pipeline-step"><b>Execution</b><small>Fill assumptions</small></div></div>
          </Panel>
          <Panel title="Recent experiments" subtitle="Live registry data, newest first" action={<Link href="/experiments"><Button variant="ghost" size="sm">Open registry →</Button></Link>}>
            {experiments.length ? <div className="list-clean">{experiments.map((e) => <div className="list-row" key={e.experiment_id}><div><strong className="link-accent mono">{e.experiment_id?.slice(0,12)}</strong><span style={{display:"block",marginTop:3}}>{e.instrument ?? "—"} · {e.data_mode ?? "—"}</span></div><div style={{textAlign:"right"}}><strong className="mono">{e.metrics?.avg_net_sharpe != null ? e.metrics.avg_net_sharpe.toFixed(3) : "—"}</strong><span style={{display:"block",marginTop:3}}>net Sharpe</span></div></div>)}</div> : <div style={{color:"var(--text-3)",fontSize:10,padding:"12px 0"}}>No research runs yet.</div>}
          </Panel>
        </div>

        {!isUploaded && (
          <Panel title="Viewing demo data"><p style={{color:"var(--text-2)",fontSize:11,lineHeight:1.8}}>This is the synthetic GBP/CAD demo series — no dataset is currently active. Upload historical data or select one in Research Lab to see your own instrument here instead.</p><div style={{marginTop:12}}><Link href="/import"><Button size="sm">Upload a dataset →</Button></Link></div></Panel>
        )}
      </>}
    </div>
  );
}
