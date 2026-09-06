"use client";

import Link from "next/link";
import { Panel, PageHeader, Badge, Button, Stat, EmptyState } from "@/components/Panel";
import { TERM_DEFINITIONS } from "@/components/MetricBadge";
import { ResearchJourney } from "@/components/ResearchJourney";
import { useActiveResearch } from "@/lib/research-context";

export default function MicrostructurePage() {
  const active = useActiveResearch();
  const features = [['microstructure_proxy','Close location in range','OHLC-derived aggression / liquidity proxy.'],['Order book','Native C++ engine','L2-style reconstruction for finer fill studies.'],['Execution impact','Research integration','Feeds cost-aware evaluation where supported.']];

  return <div className="stack">
    <ResearchJourney current="microstructure"/>
    <PageHeader kicker="Research / Market mechanics" title="Microstructure" description="Technical context for the price, liquidity and execution features already exposed by the QuantPulse backend, applied to the active dataset where possible." />

    {active ? (
      <Panel eyebrow="ACTIVE DATASET" title={active.dataset?.dataset_id==='demo' ? 'Demo (synthetic)' : (active.dataset?.dataset_id ?? active.instrument)} subtitle="Microstructure proxies below describe this dataset's actual OHLCV bars.">
        <div className="card-grid-4">
          <Stat label="Instrument" value={active.instrument} tone="accent"/>
          <Stat label="Timeframe" value={active.timeframe}/>
          <Stat label="Rows" value={active.dataset?.rows!=null?active.dataset.rows.toLocaleString():'—'}/>
          <Stat label="Data mode" value={active.data_mode}/>
        </div>
      </Panel>
    ) : (
      <Panel><EmptyState title="No dataset selected" description="Upload data or run research to see dataset-specific microstructure context." action={<Link href="/import"><Button>Go to Data Import →</Button></Link>} /></Panel>
    )}

    <Panel eyebrow="MARKET MECHANICS" title="What QuantPulse actually models" subtitle="No synthetic order-book values are invented in this interface.">
      <div className="card-grid-3">{features.map(([name,tag,desc])=><div className="list-row" key={name}><div><strong>{name}</strong><span style={{display:'block',marginTop:5}}>{desc}</span></div><Badge tone={name==='Order book'?'accent':'default'}>{tag}</Badge></div>)}</div>
    </Panel>

    <div className="card-grid-2">
      <Panel title="OHLC microstructure proxy" subtitle="Available on every compatible bar dataset"><div style={{fontSize:28,letterSpacing:'-.05em'}} className="mono link-accent">close / range</div><p style={{color:'var(--text-3)',fontSize:10,lineHeight:1.6,marginTop:8}}>A compact proxy derived from where the close sits inside the high–low range. This is an <strong>OHLC-derived proxy</strong>, not actual order-book data — the uploaded/demo data contains OHLCV bars only, never true bid/ask depth.</p></Panel>
      <Panel title="Native order book" subtitle="For experiments requiring finer fill fidelity"><div className="pipeline"><div className="pipeline-step"><b>Book</b><small>L2 state</small></div><div className="pipeline-step active"><b>Impact</b><small>Fill study</small></div><div className="pipeline-step"><b>Execution</b><small>Simulation</small></div></div><p style={{color:'var(--text-3)',fontSize:10,lineHeight:1.6,marginTop:8}}>This is <strong>actual order-book data</strong> only when the native C++ engine is used directly — it is not connected to the standard walk-forward research API used by Research Lab.</p></Panel>
    </div>

    <Panel title="Microstructure proxy definition" subtitle="What the OHLC-derived proxy actually measures — and what it does not.">
      <div style={{fontSize:10,color:'var(--text-2)',lineHeight:1.8}}>
        <p><strong>Definition:</strong> {TERM_DEFINITIONS.microstructure_proxy.short}</p>
        <p style={{marginTop:8,color:'var(--warn)'}}><strong>⚠ Important caveat:</strong> {TERM_DEFINITIONS.microstructure_proxy.detail}</p>
        <p style={{marginTop:8}}>This proxy is used as the <code className="mono">microstructure_proxy</code> signal in the research pipeline. Its Information Coefficient and significance are evaluated exactly like any other signal — against the same walk-forward folds and forward-return targets — so its predictive value (if any) is empirically tested rather than assumed.</p>
      </div>
    </Panel>

    <Panel title="Data quality note"><p style={{color:'var(--text-2)',fontSize:11,lineHeight:1.8}}>
      {active?.data_mode==='demo'
        ? "Regime detection for the demo dataset can be inspected live via the Dashboard's /api/regimes call."
        : "Regime information for uploaded-dataset experiments is computed internally per walk-forward fold (app/domain/regimes.py) but is not currently included in /api/research/run's JSON response, so it is not shown here rather than approximated."}
    </p></Panel>

    <Panel eyebrow="NEXT STEP" title="Continue the research journey"><div style={{display:'flex',gap:10,flexWrap:'wrap'}}><Link href="/paper"><Button size="lg">Next → Paper Trading</Button></Link></div></Panel>
  </div>;
}
