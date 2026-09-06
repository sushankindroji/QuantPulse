"use client";

import Link from "next/link";
import { Panel, PageHeader, Badge, Button, SectionLabel, Stat, EmptyState } from "@/components/Panel";
import { MetricBadge, FoldRobustnessWarning, MetricHeuristicsNote } from "@/components/MetricBadge";
import { ResearchJourney } from "@/components/ResearchJourney";
import { useActiveResearch, hasExperiment } from "@/lib/research-context";

// Signal families that exist in the research pipeline (app/domain/signals.py).
// Kept as background/explanatory context — evidence for each one (when
// available) is rendered from the actual experiment result above this list,
// not invented here.
const SIGNAL_FAMILIES = [
  ["momentum_5 / momentum_20 / momentum_50", "Directional continuation across short, medium and longer lookbacks."],
  ["mean_reversion_20 / mean_reversion_50", "Fade of price z-score extremes relative to rolling windows."],
  ["vol_adjusted_momentum_10", "Momentum scaled by short/long volatility ratio."],
  ["microstructure_proxy", "OHLC-derived close-location-in-range as a liquidity / aggression proxy."],
];

function classifyEvidence(ic: number | null | undefined, pValue: number | null | undefined, nObs: number | null | undefined, significant: boolean | null | undefined) {
  if (ic == null || Number.isNaN(ic) || nObs == null) return { label: "Insufficient sample", tone: "default" as const };
  if (nObs < 30) return { label: "Insufficient sample", tone: "default" as const };
  if (significant && Math.abs(ic) >= 0.03) return { label: "Positive evidence", tone: "good" as const };
  if (significant) return { label: "Weak evidence", tone: "warning" as const };
  return { label: "Insignificant", tone: "bad" as const };
}

export default function AlphaExplorerPage() {
  const active = useActiveResearch();

  if (!active) {
    return <div className="stack">
      <ResearchJourney current="alpha"/>
      <PageHeader kicker="Research / Signal evidence" title="Alpha Explorer" description="A research-facing view of the signal families evaluated by QuantPulse. Evidence comes from walk-forward experiment reports." />
      <Panel>
        <EmptyState title="No research experiment selected" description="Run Research first, or open a past run from the Experiments registry." action={<Link href="/research"><Button>Go to Research Lab →</Button></Link>} />
      </Panel>
    </div>;
  }

  if (!hasExperiment(active)) {
    const hasDataset = !!active.dataset && active.dataset.dataset_id !== 'demo';
    return <div className="stack">
      <ResearchJourney current="alpha"/>
      <PageHeader kicker="Research / Signal evidence" title="Alpha Explorer" description="A research-facing view of the signal families evaluated by QuantPulse. Evidence comes from walk-forward experiment reports." />
      <Panel>
        {hasDataset ? (
          <EmptyState title={`${active.instrument} · ${active.timeframe} selected — no experiment yet`} description="Run Research on this dataset to generate signal evidence." action={<Link href={`/research?dataset_id=${active.dataset!.dataset_id}`}><Button>Run Research on this dataset →</Button></Link>} />
        ) : (
          <EmptyState title="No research experiment selected" description="Run Research first, or open a past run from the Experiments registry." action={<Link href="/research"><Button>Go to Research Lab →</Button></Link>} />
        )}
      </Panel>
    </div>;
  }

  const folds: any[] = active.full_result?.metrics?.folds ?? [];
  const hasFoldDetail = folds.length > 0;
  const lowConfidence = folds.length > 0 && folds.length < 3;

  // Aggregate signal_reports across folds (name -> per-fold IC results),
  // using ONLY what the backend actually returned per fold.
  const bySignal = new Map<string, { ic: number; p_value: number; n_obs: number; significant_at_5pct: boolean }[]>();
  for (const f of folds) {
    for (const sr of f.signal_reports ?? []) {
      const arr = bySignal.get(sr.name) ?? [];
      arr.push({ ic: sr.ic, p_value: sr.p_value, n_obs: sr.n_obs, significant_at_5pct: sr.significant_at_5pct });
      bySignal.set(sr.name, arr);
    }
  }

  const dateRange = active.research_window?.start && active.research_window?.end
    ? `${active.research_window.start.slice(0,10)} → ${active.research_window.end.slice(0,10)}${active.research_window.is_full_dataset===false ? ' (subset)' : ''}`
    : (active.dataset?.start_time && active.dataset?.end_time
      ? `${active.dataset.start_time.slice(0,10)} → ${active.dataset.end_time.slice(0,10)}`
      : (active.full_result ? "See experiment detail" : "Not available for this experiment"));

  return <div className="stack">
    <ResearchJourney current="alpha"/>
    <PageHeader kicker="Research / Signal evidence" title="Alpha Explorer" description="A research-facing view of the signal families evaluated by QuantPulse. Evidence comes from walk-forward experiment reports." actions={<Link href="/research"><Button size="sm">Run new research →</Button></Link>} />

    <Panel eyebrow="ACTIVE EXPERIMENT" title={active.experiment_id ?? "Unlogged run"} subtitle={active.source==='run' ? "From your most recent Research Lab run" : "Selected from the Experiments registry"} action={active.full_result ? <Badge tone="good">FULL EVIDENCE</Badge> : <Badge tone="warning">SUMMARY ONLY</Badge>}>
      <div className="card-grid-4">
        <Stat label="Dataset" value={active.dataset?.dataset_id==='demo' ? 'Demo (synthetic)' : (active.dataset?.dataset_id?.slice(0,10) ?? '—')} tone="accent"/>
        <Stat label="Instrument" value={active.instrument}/>
        <Stat label="Timeframe" value={active.timeframe}/>
        <Stat label="Date range" value={dateRange}/>
      </div>
    </Panel>

    {!hasFoldDetail && (
      <Panel eyebrow="NOTICE" title="Fold-level signal evidence not available">
        <p style={{color:'var(--text-2)',fontSize:11,lineHeight:1.8}}>
          This experiment was selected from the registry, which only stores aggregate metrics
          (avg net Sharpe, avg max drawdown, fold count) — the backend&apos;s experiment store does not
          persist per-fold signal evidence. To see Information Coefficient, p-value, significance and
          fold-level stability for every signal, run this configuration again from Research Lab; the
          detailed evidence is available immediately after a run completes.
        </p>
        <div className="card-grid-4" style={{marginTop:14}}>
          <Stat label="Avg net Sharpe" value={active.metrics_summary.avg_net_sharpe!=null?active.metrics_summary.avg_net_sharpe.toFixed(3):'—'} tone={((active.metrics_summary.avg_net_sharpe??0)>0)?'good':'default'}/>
          <Stat label="Avg max drawdown" value={active.metrics_summary.avg_max_drawdown!=null?(active.metrics_summary.avg_max_drawdown*100).toFixed(2)+'%':'—'} tone="bad"/>
          <Stat label="Folds" value={active.metrics_summary.n_folds!=null?String(active.metrics_summary.n_folds):'—'}/>
          <Stat label="Data mode" value={active.data_mode}/>
        </div>
      </Panel>
    )}

    {hasFoldDetail && (
      <Panel eyebrow="SIGNAL EVIDENCE" title="Per-signal Information Coefficient" subtitle="Averaged across walk-forward folds. IC and significance are exactly as returned by the research backend." action={lowConfidence ? <Badge tone="bad">LOW CONFIDENCE — {folds.length} FOLD{folds.length===1?'':'S'}</Badge> : undefined}>
        {lowConfidence && <p style={{fontSize:10,color:'var(--bad)',marginBottom:14,lineHeight:1.7}}>Only {folds.length} walk-forward fold{folds.length===1?'':'s'} back this signal evidence — not enough to judge stability across market conditions. Treat these IC values as preliminary.</p>}
        <FoldRobustnessWarning nFolds={folds.length}/>
        <div className="table-wrap"><table className="data-table">
          <thead><tr><th>Signal</th><th>Avg IC</th><th>IC Interpretation</th><th>Avg p-value</th><th>p-value</th><th>Folds significant</th><th>Fold consistency</th><th>Evidence</th></tr></thead>
          <tbody>
            {Array.from(bySignal.entries()).map(([name, results]) => {
              const validIcs = results.map(r=>r.ic).filter(v=>v==v);
              const avgIc = validIcs.length ? validIcs.reduce((a,b)=>a+b,0)/validIcs.length : NaN;
              const validP = results.map(r=>r.p_value).filter(v=>v==v);
              const avgP = validP.length ? validP.reduce((a,b)=>a+b,0)/validP.length : NaN;
              const sigCount = results.filter(r=>r.significant_at_5pct).length;
              const totalNobs = results.reduce((a,r)=>a+(r.n_obs??0),0);
              const signAgree = validIcs.length ? validIcs.filter(v => Math.sign(v) === Math.sign(avgIc)).length : 0;
              const consistency = validIcs.length ? `${signAgree}/${validIcs.length} folds agree` : "—";
              const ev = classifyEvidence(avgIc, avgP, totalNobs, sigCount > 0);
              return <tr key={name}>
                <td className="mono">{name}</td>
                <td className="mono" style={{color: avgIc>0?'var(--good)':avgIc<0?'var(--bad)':'var(--text-2)'}}>{Number.isNaN(avgIc)?'—':avgIc.toFixed(4)}</td>
                <td><MetricBadge metric="ic" value={Number.isNaN(avgIc)?null:avgIc}/></td>
                <td className="mono">{Number.isNaN(avgP)?'—':avgP.toFixed(4)}</td>
                <td><MetricBadge metric="p_value" value={Number.isNaN(avgP)?null:avgP}/></td>
                <td className="mono">{sigCount}/{results.length}</td>
                <td>{consistency}</td>
                <td><Badge tone={ev.tone}>{ev.label}</Badge></td>
              </tr>;
            })}
            {bySignal.size===0 && <tr><td colSpan={8} style={{color:'var(--text-3)',fontSize:10,padding:14}}>No signal reports were returned for this experiment&apos;s folds.</td></tr>}
          </tbody>
        </table></div>
        <p style={{fontSize:10,color:'var(--text-3)',lineHeight:1.7,marginTop:14}}>Alpha decay across horizons and regime-conditional performance are computed internally by the backtest engine but are not currently serialized by <code className="mono">/api/research/run</code> — they show as unavailable rather than being estimated here.</p>
        <MetricHeuristicsNote/>
      </Panel>
    )}

    <Panel eyebrow="NEXT STEP" title="Take this experiment to Backtest" subtitle="The same active experiment carries over automatically.">
      <div style={{display:'flex',gap:10,flexWrap:'wrap'}}><Link href="/backtest"><Button size="lg">Run Backtest →</Button></Link><Link href="/experiments"><Button variant="secondary" size="sm">View in registry</Button></Link></div>
    </Panel>

    <Panel title="Signal catalog" subtitle="Definitions already present in the research pipeline (background context).">
      <div className="stack">{SIGNAL_FAMILIES.map(([name, desc], i) => <div className="list-row" key={name}><div style={{display:"flex",gap:12,alignItems:"flex-start"}}><span className="mono" style={{fontSize:9,color:"var(--accent)",paddingTop:2}}>0{i+1}</span><div><strong className="mono">{name}</strong><span style={{display:"block",marginTop:5,lineHeight:1.5}}>{desc}</span></div></div><Badge tone="default">RESEARCH</Badge></div>)}</div>
    </Panel>
  </div>;
}
