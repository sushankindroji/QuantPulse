"use client";

import Link from "next/link";
import { Panel, PageHeader, Badge, Button, SectionLabel, Stat, EmptyState } from "@/components/Panel";
import { MetricBadge, FoldRobustnessWarning, MetricHeuristicsNote } from "@/components/MetricBadge";
import { ResearchJourney } from "@/components/ResearchJourney";
import { useActiveResearch, hasExperiment } from "@/lib/research-context";

function safeAvg(values: (number | null | undefined)[]): number | null {
  const clean = values.filter((v): v is number => v != null && v === v);
  if (!clean.length) return null;
  return clean.reduce((a, b) => a + b, 0) / clean.length;
}

export default function BacktestPage() {
  const active = useActiveResearch();

  if (!active) {
    return <div className="stack">
      <ResearchJourney current="backtest"/>
      <PageHeader kicker="Research / Validation" title="Backtest" description="Understand how walk-forward performance changes once spread, slippage and latency are applied." />
      <Panel><EmptyState title="No research experiment selected" description="Run Research first — backtest evidence is produced as part of the walk-forward research run." action={<Link href="/research"><Button>Go to Research Lab →</Button></Link>} /></Panel>
    </div>;
  }

  if (!hasExperiment(active)) {
    const hasDataset = !!active.dataset && active.dataset.dataset_id !== 'demo';
    return <div className="stack">
      <ResearchJourney current="backtest"/>
      <PageHeader kicker="Research / Validation" title="Backtest" description="Understand how walk-forward performance changes once spread, slippage and latency are applied." />
      <Panel>
        {hasDataset ? (
          <EmptyState title={`${active.instrument} · ${active.timeframe} selected — no experiment yet`} description="Backtest evidence is produced as part of the walk-forward research run. Run Research on this dataset first." action={<Link href={`/research?dataset_id=${active.dataset!.dataset_id}`}><Button>Run Research on this dataset →</Button></Link>} />
        ) : (
          <EmptyState title="No research experiment selected" description="Run Research first — backtest evidence is produced as part of the walk-forward research run." action={<Link href="/research"><Button>Go to Research Lab →</Button></Link>} />
        )}
      </Panel>
    </div>;
  }

  const folds: any[] = active.full_result?.metrics?.folds ?? [];
  const hasFoldDetail = folds.length > 0;
  const lowConfidence = folds.length > 0 && folds.length < 3;

  if (!hasFoldDetail) {
    return <div className="stack">
      <ResearchJourney current="backtest"/>
      <PageHeader kicker="Research / Validation" title="Backtest" description="Understand how walk-forward performance changes once spread, slippage and latency are applied." actions={<Link href="/experiments"><Button variant="secondary" size="sm">View experiments</Button></Link>} />
      <Panel eyebrow="ACTIVE EXPERIMENT" title={active.experiment_id ?? "Unlogged run"} subtitle="Research experiment available — but only summary metrics, not per-fold backtest detail.">
        <div className="card-grid-4">
          <Stat label="Instrument" value={active.instrument} tone="accent"/>
          <Stat label="Timeframe" value={active.timeframe}/>
          <Stat label="Avg net Sharpe" value={active.metrics_summary.avg_net_sharpe!=null?active.metrics_summary.avg_net_sharpe.toFixed(3):'—'} tone={((active.metrics_summary.avg_net_sharpe??0)>0)?'good':'default'}/>
          <Stat label="Avg max drawdown" value={active.metrics_summary.avg_max_drawdown!=null?(active.metrics_summary.avg_max_drawdown*100).toFixed(2)+'%':'—'} tone="bad"/>
        </div>
      </Panel>
      <Panel title="Per-fold detail not available"><p style={{color:'var(--text-2)',fontSize:11,lineHeight:1.8}}>This experiment was selected from the registry. The backend&apos;s experiment store only persists aggregate metrics, not the per-fold risk reports (total return, Sortino, win rate, trade turnover, profit factor, cost sensitivity). Re-run this configuration in Research Lab to see the full backtest breakdown immediately after completion.</p></Panel>
    </div>;
  }

  const riskReports = folds.map(f => f.risk_report ?? {});
  const avgSharpe = safeAvg(riskReports.map(r => r.sharpe));
  const avgSortino = safeAvg(riskReports.map(r => r.sortino));
  const avgMaxDD = safeAvg(riskReports.map(r => r.max_drawdown));
  const avgHitRate = safeAvg(riskReports.map(r => r.hit_rate));
  const avgProfitFactor = safeAvg(riskReports.map(r => r.profit_factor));
  const avgCumReturn = safeAvg(riskReports.map(r => r.cumulative_return));
  const avgTurnover = safeAvg(riskReports.map(r => r.turnover));

  return <div className="stack">
    <ResearchJourney current="backtest"/>
    <PageHeader kicker="Research / Validation" title="Backtest" description="Each walk-forward fold below is itself a full backtest: signal → position sizing → execution costs → risk report. There is no separate on-demand backtest endpoint in the backend — this IS the backtest." actions={<Link href="/experiments"><Button variant="secondary" size="sm">View experiments</Button></Link>} />

    <Panel eyebrow="ACTIVE EXPERIMENT" title={active.experiment_id ?? "Unlogged run"} subtitle="Backtest evidence produced by the Research Lab walk-forward run." action={lowConfidence ? <Badge tone="bad">LOW CONFIDENCE — {folds.length} FOLD{folds.length===1?'':'S'}</Badge> : <Badge tone="good">REAL FOLD DATA</Badge>}>
      {lowConfidence && <p style={{fontSize:10,color:'var(--bad)',marginBottom:14,lineHeight:1.7}}>Only {folds.length} walk-forward fold{folds.length===1?'':'s'} were evaluated. This is not strong evidence of a stable edge — expand the dataset or research window (or reduce train/test bars) to get at least 3–5 folds before drawing conclusions.</p>}
      <div className="card-grid-4">
        <Stat label="Instrument" value={active.instrument} tone="accent"/>
        <Stat label="Timeframe" value={active.timeframe}/>
        <Stat label="Folds" value={String(folds.length)}/>
        <Stat label="Data source" value={active.full_result?.data_source ?? active.data_mode}/>
      </div>
    </Panel>

    <div className="metric-grid">
      <Panel className="metric-card"><Stat label="Avg Sharpe" value={avgSharpe!=null?avgSharpe.toFixed(3):'n/a'} tone={avgSharpe!=null&&avgSharpe>0?'good':'default'}/><div style={{marginTop:6}}><MetricBadge metric="sharpe" value={avgSharpe}/></div></Panel>
      <Panel className="metric-card"><Stat label="Avg Sortino" value={avgSortino!=null?avgSortino.toFixed(3):'n/a'}/><div style={{marginTop:6}}><MetricBadge metric="sortino" value={avgSortino}/></div></Panel>
      <Panel className="metric-card"><Stat label="Avg max drawdown" value={avgMaxDD!=null?(avgMaxDD*100).toFixed(2)+'%':'n/a'} tone="bad"/><div style={{marginTop:6}}><MetricBadge metric="max_drawdown" value={avgMaxDD}/></div></Panel>
      <Panel className="metric-card"><Stat label="Avg hit rate" value={avgHitRate!=null?(avgHitRate*100).toFixed(1)+'%':'n/a'}/><div style={{marginTop:6}}><MetricBadge metric="hit_rate" value={avgHitRate}/></div></Panel>
    </div>
    <div className="metric-grid">
      <Panel className="metric-card"><Stat label="Avg profit factor" value={avgProfitFactor!=null?avgProfitFactor.toFixed(2):'n/a'}/><div style={{marginTop:6}}><MetricBadge metric="profit_factor" value={avgProfitFactor}/></div></Panel>
      <Panel className="metric-card"><Stat label="Avg cumulative return (per fold)" value={avgCumReturn!=null?(avgCumReturn*100).toFixed(2)+'%':'n/a'}/></Panel>
      <Panel className="metric-card"><Stat label="Avg turnover" value={avgTurnover!=null?avgTurnover.toFixed(2):'n/a'}/></Panel>
      <Panel className="metric-card"><Stat label="Trade count" value="Not available for this experiment" hint="Backend reports position turnover, not discrete trade counts"/></Panel>
    </div>

    <Panel eyebrow="EVIDENCE" title="Fold-by-fold backtest report" subtitle="Out-of-sample, net of the spread/slippage/latency configured in Research Lab.">
      <FoldRobustnessWarning nFolds={folds.length}/>
      <div className="table-wrap"><table className="data-table">
        <thead><tr><th>Fold</th><th>Sharpe</th><th>Interpretation</th><th>Sortino</th><th>Max DD</th><th>Hit rate</th><th>Profit factor</th><th>Cum. return</th><th>Turnover</th><th>Leakage</th></tr></thead>
        <tbody>{folds.map((f:any)=>{const r=f.risk_report??{};return <tr key={f.fold_id}>
          <td className="mono link-accent">{f.fold_id}</td>
          <td className="mono" style={{color:r.sharpe>0?'var(--good)':r.sharpe<0?'var(--bad)':'var(--text-2)'}}>{r.sharpe!=null?r.sharpe.toFixed(3):'—'}</td>
          <td><MetricBadge metric="sharpe" value={r.sharpe}/></td>
          <td className="mono">{r.sortino!=null?r.sortino.toFixed(3):'—'}</td>
          <td className="mono">{r.max_drawdown!=null?(r.max_drawdown*100).toFixed(2)+'%':'—'}</td>
          <td className="mono">{r.hit_rate!=null?(r.hit_rate*100).toFixed(1)+'%':'—'}</td>
          <td className="mono">{r.profit_factor!=null?r.profit_factor.toFixed(2):'—'}</td>
          <td className="mono">{r.cumulative_return!=null?(r.cumulative_return*100).toFixed(2)+'%':'—'}</td>
          <td className="mono">{r.turnover!=null?r.turnover.toFixed(2):'—'}</td>
          <td>{f.leakage_check?.ok?<Badge tone="good">OK</Badge>:<Badge tone="bad">FAIL</Badge>}</td>
        </tr>;})}</tbody>
      </table></div>
      <p style={{fontSize:10,color:'var(--text-3)',lineHeight:1.7,marginTop:14}}>An equity curve and returns-by-period series are not currently serialized by <code className="mono">/api/research/run</code> (only summary risk statistics per fold are returned) — not shown here rather than approximated.</p>
      <MetricHeuristicsNote/>
    </Panel>

    <Panel eyebrow="NEXT STEP" title="Inspect execution cost sensitivity"><div style={{display:'flex',gap:10,flexWrap:'wrap'}}><Link href="/execution"><Button size="lg">Next → Execution Analysis</Button></Link></div></Panel>
  </div>;
}
