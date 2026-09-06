"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Panel, Stat, SyntheticBadge, PageHeader, Button, ErrorBanner, LoadingBlock, Badge, SectionLabel } from "@/components/Panel";
import { MetricBadge, FoldRobustnessWarning, MetricHeuristicsNote } from "@/components/MetricBadge";
import { TIMEFRAMES, allowedResearchTimeframes, autoConfigure, validateFoldFeasibility, type AutoConfig } from "@/lib/autoconfig";
import { buildActiveResearchFromRunResult, buildActiveResearchFromDataset, setActiveResearch, type ActiveDatasetMeta } from "@/lib/research-context";
import { ResearchJourney } from "@/components/ResearchJourney";

const DEMO_DEFAULTS = { timeframe: "1h", train_bars: 1200, test_bars: 300, step_bars: 300, embargo_bars: 10, primary_horizon: 5, spread_pips: 1.2, slippage_pips: 0.3 };

function ResearchLabInner(){
 const searchParams=useSearchParams();const initialDatasetId=searchParams.get('dataset_id');
 const [datasets,setDatasets]=useState<any[]>([]),[selectedDataset,setSelectedDataset]=useState(initialDatasetId??'demo'),[running,setRunning]=useState(false),[result,setResult]=useState<any>(null),[error,setError]=useState<string|null>(null);
 const [form,setForm]=useState({...DEMO_DEFAULTS});
 const [autoInfo,setAutoInfo]=useState<AutoConfig|null>(null);
 const [advancedOpen,setAdvancedOpen]=useState(false);
 const [rangePreset,setRangePreset]=useState<'full'|'30d'|'3m'|'6m'|'1y'|'3y'|'custom'>('full');
 const [customStart,setCustomStart]=useState('');
 const [customEnd,setCustomEnd]=useState('');
 const [rangePreview,setRangePreview]=useState<any>(null);
 const [rangeLoading,setRangeLoading]=useState(false);
 const [rangeError,setRangeError]=useState<string|null>(null);
 const rangeRequestId=useRef(0);
 useEffect(()=>{
  api.datasets()
   .then(r=>{
    const next=r.datasets??[];
    setDatasets(next);
    if(initialDatasetId){
     const requested=next.find(d=>d.dataset_id===initialDatasetId);
     if(!requested){
      setSelectedDataset(initialDatasetId);
      setError(`Dataset '${initialDatasetId}' is no longer registered and cannot be run.`);
     } else if(requested.available === false){
      setSelectedDataset(initialDatasetId);
      setError(requested.availability_error || `Dataset '${initialDatasetId}' is registered but its backing file is unavailable.`);
     }
    }
   })
   .catch((e:any)=>{
    setDatasets([]);
    setError(e?.message || 'Could not load registered datasets.');
   });
 },[initialDatasetId]);
 useEffect(()=>{if(initialDatasetId)setSelectedDataset(initialDatasetId)},[initialDatasetId]);
 const active=datasets.find(d=>d.dataset_id===selectedDataset && d.available !== false);
 const activeRows:number|undefined = active ? (active.n_rows ?? active.rows) : undefined;
 const setField=(k:keyof typeof form,v:number|string)=>setForm(f=>({...f,[k]:v}));

 // When the selected dataset changes, default the research timeframe to the
 // dataset's own source timeframe (never assume 1h), and immediately make
 // it (or an explicit demo choice) the app's active dataset context so
 // Dashboard and other pages reflect it right away — before a run even
 // happens. Selecting a dataset always replaces whatever was active before.
 useEffect(()=>{
  if(selectedDataset==='demo'){
   setField('timeframe', DEMO_DEFAULTS.timeframe);
   setActiveResearch(buildActiveResearchFromDataset({dataset_id:'demo', instrument:'GBP_CAD', source_timeframe:DEMO_DEFAULTS.timeframe, is_synthetic:true}));
   return;
  }
  if(active){
   setField('timeframe', active.source_timeframe);
   setActiveResearch(buildActiveResearchFromDataset({dataset_id:active.dataset_id, instrument:active.instrument, source_timeframe:active.source_timeframe, rows:active.n_rows??active.rows, start_time:active.start_time, end_time:active.end_time, timezone:active.timezone, is_synthetic:false}));
  }
  setRangePreset('full'); setCustomStart(''); setCustomEnd(''); setRangePreview(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[selectedDataset, active?.dataset_id]);

 // Compute the effective [start, end] for the chosen preset, relative to
 // the DATASET's own latest timestamp — never the wall-clock date — per
 // "last 30 days" etc. meaning relative to the data, not today.
 const effectiveRange = (()=>{
  if(!active || rangePreset==='full') return {start:undefined as string|undefined, end:undefined as string|undefined};

  // Date inputs are date-only, so make custom end dates inclusive. Uploaded
  // datasets are normalized to UTC by the ingestion layer.
  if(rangePreset==='custom'){
   return {
    start: customStart ? `${customStart}T00:00:00.000Z` : undefined,
    end: customEnd ? `${customEnd}T23:59:59.999Z` : undefined,
   };
  }

  const days:Record<string,number> = {'30d':30,'3m':90,'6m':182,'1y':365,'3y':365*3};
  const datasetEnd = active.end_time ? new Date(active.end_time) : null;
  if(!datasetEnd || Number.isNaN(datasetEnd.getTime())) return {start:undefined, end:undefined};

  const start = new Date(datasetEnd.getTime() - days[rangePreset]*24*60*60*1000);
  // Send both bounds so preview and the final research run use exactly the
  // same window rather than relying on an implicit dataset end.
  return {start: start.toISOString(), end: datasetEnd.toISOString()};
 })();

 // Preview how many bars fall inside the chosen range. Requests are
 // sequence-guarded so a slower response for an older selection can never
 // overwrite the currently selected dataset/range.
 useEffect(()=>{
  const requestId=++rangeRequestId.current;
  if(selectedDataset==='demo' || !active){
   setRangePreview(null); setRangeError(null); setRangeLoading(false); return;
  }
  const params:{start?:string;end?:string}={};
  if(effectiveRange.start) params.start=effectiveRange.start;
  if(effectiveRange.end) params.end=effectiveRange.end;

  if(rangePreset==='custom' && (!customStart || !customEnd)){
   setRangePreview(null);
   setRangeError('Choose both a custom start date and end date.');
   setRangeLoading(false);
   return;
  }
  if(rangePreset==='custom' && customStart && customEnd && customStart>customEnd){
   setRangePreview(null);
   setRangeError('Custom start date cannot be after the end date.');
   setRangeLoading(false);
   return;
  }
  setRangeLoading(true);
  setRangeError(null);
  api.datasetRange(selectedDataset, params)
   .then(result=>{
    if(requestId!==rangeRequestId.current) return;
    setRangePreview(result);
   })
   .catch((e:any)=>{
    if(requestId!==rangeRequestId.current) return;
    setRangePreview(null);
    setRangeError(e?.name === 'AbortError' ? 'Range calculation timed out. Try again or choose another range.' : (e?.message || 'Could not calculate the selected dataset range.'));
   })
   .finally(()=>{
    if(requestId===rangeRequestId.current) setRangeLoading(false);
   });
  return ()=>{ /* sequence guard handles in-flight responses */ };
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[selectedDataset, rangePreset, customStart, customEnd, active?.dataset_id, effectiveRange.start, effectiveRange.end]);

 // Recompute the walk-forward configuration whenever the dataset or the
 // chosen research timeframe changes, using the dataset's *actual* row
 // count instead of a fixed guess.
 useEffect(()=>{
  if(selectedDataset==='demo' || !active || !activeRows){ setAutoInfo(null); return; }
  const effectiveBars = (rangePreset!=='full' && rangePreview?.bars_selected!=null) ? rangePreview.bars_selected : activeRows;
  const cfg=autoConfigure(effectiveBars, active.source_timeframe, form.timeframe);
  setAutoInfo(cfg);
  if(cfg.feasible){
   setForm(f=>({...f, train_bars:cfg.train_bars, test_bars:cfg.test_bars, step_bars:cfg.step_bars, embargo_bars:cfg.embargo_bars, primary_horizon:cfg.primary_horizon}));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[selectedDataset, active?.dataset_id, form.timeframe, rangePreset, rangePreview?.bars_selected]);

 const researchTimeframeOptions = active ? allowedResearchTimeframes(active.source_timeframe) : TIMEFRAMES as unknown as string[];

 async function run(){
  setError(null);setResult(null);
  if(selectedDataset!=='demo'){
   if(!active){ setError('The selected dataset is unavailable and cannot be run. Re-import it before running research.'); return; }
   if(rangePreset==='custom' && (!customStart || !customEnd)){ setError('Choose both a custom start date and end date.'); return; }
   if(rangePreset==='custom' && customStart && customEnd && customStart>customEnd){ setError('Custom start date cannot be after the end date.'); return; }
   if(rangePreset!=='full' && (rangeLoading || rangeError || !rangePreview)){ setError(rangeError || 'The selected research range could not be verified. Please wait for it to finish or choose another range.'); return; }
   const usable = autoInfo?.usable_bars ?? 0;
   if(autoInfo && !autoInfo.feasible){ setError(autoInfo.reason || 'This dataset is too small for walk-forward research.'); return; }
   const check = validateFoldFeasibility(usable, form.train_bars, form.test_bars, form.embargo_bars);
   if(!check.ok){ setError(check.message!); return; }
   if(rangePreset!=='full' && rangePreview && !rangePreview.sufficient_for_research){ setError(`The selected range has only ${rangePreview.bars_selected} bars, below the ${rangePreview.minimum_required_bars} needed for reliable walk-forward evaluation. Expand the selected range.`); return; }
  }
  setRunning(true);
  try{
   const body:Record<string,unknown>={...form};
   if(selectedDataset!=='demo'){
    body.dataset_id=selectedDataset;
    if(rangePreset!=='full'){
     if(effectiveRange.start)body.range_start=effectiveRange.start;
     if(effectiveRange.end)body.range_end=effectiveRange.end;
    }
   }
   const runResult=await api.runResearch(body);
   setResult(runResult);
   const datasetMeta:ActiveDatasetMeta = selectedDataset==='demo'
    ? {dataset_id:'demo', instrument:runResult.instrument, source_timeframe:runResult.timeframe, is_synthetic:true}
    : {dataset_id:selectedDataset, instrument:active?.instrument??runResult.instrument, source_timeframe:active?.source_timeframe??runResult.timeframe, rows:activeRows, start_time:active?.start_time, end_time:active?.end_time, timezone:active?.timezone, is_synthetic:false};
   setActiveResearch(buildActiveResearchFromRunResult({
    result: runResult,
    dataMode: selectedDataset==='demo' ? 'demo' : 'uploaded',
    dataset: datasetMeta,
    executionConfig: {spread_pips: form.spread_pips, slippage_pips: form.slippage_pips},
   }));
  }catch(e:any){setError(e.message||'Research run failed')}finally{setRunning(false)}
 }
 const folds=result?.metrics?.folds??[];
 return <div className="stack">
  <ResearchJourney current="research"/>
  <PageHeader kicker="Research / Experiment builder" title="Research Lab" description="Compose a reproducible walk-forward experiment. Every control below maps to the existing research API contract." actions={<SyntheticBadge isSynthetic={selectedDataset==='demo'}/>} />
  {error&&<ErrorBanner message={error} onDismiss={()=>setError(null)}/>} 
  <Panel eyebrow="01 · DATASET" title="Choose your research data" subtitle="Select one registered dataset. The selector stays compact even when many datasets are available.">
   <div className="dataset-picker">
    <div className="dataset-picker-main">
     <label className="input-label" htmlFor="research-dataset">Dataset</label>
     <select id="research-dataset" className="field dataset-select" value={selectedDataset} onChange={e=>setSelectedDataset(e.target.value)}>
      <option value="demo">Demo dataset · Synthetic</option>
      {datasets.map(d=><option key={d.dataset_id} value={d.dataset_id} disabled={d.available === false}>
       {d.instrument} · {d.source_timeframe} · {(d.n_rows??d.rows)?.toLocaleString?.()??d.n_rows??d.rows} rows · {d.dataset_id.slice(0,8)}{d.available === false ? " · UNAVAILABLE" : ""}
      </option>)}
     </select>
    </div>
    <div className="dataset-count">{datasets.length} registered {datasets.length===1?'dataset':'datasets'}</div>
   </div>
   {active&&<div className="dataset-strip">
    <span><b>Available range</b>{active.start_time?.slice(0,10) ?? '—'} → {active.end_time?.slice(0,10) ?? '—'}</span>
    <span><b>Rows</b>{activeRows?.toLocaleString() ?? '—'}</span>
    <span><b>Source timeframe</b>{active.source_timeframe}</span>
    <span><b>Timezone</b>{active.timezone??'—'}</span>
    {selectedDataset==='demo' && <SyntheticBadge isSynthetic={true}/>}
   </div>}
  </Panel>
  {active && selectedDataset!=='demo' && <Panel eyebrow="01b · DATASET RANGE" title="Research horizon" subtitle="Full dataset is the default — narrow it only if you want to test a specific period.">
   <div className="range-presets" role="group" aria-label="Research date range">
    {[['full','Full dataset'],['30d','Last 30 days'],['3m','Last 3 months'],['6m','Last 6 months'],['1y','Last 1 year'],['3y','Last 3 years'],['custom','Custom']].map(([val,label])=>
     <button key={val} type="button" onClick={()=>setRangePreset(val as any)} className={`range-preset ${rangePreset===val?'active':''}`} aria-pressed={rangePreset===val}>{label}</button>
    )}
   </div>
   {rangePreset!=='full' && effectiveRange.start && <div className="selected-range-note"><span>Selected research window</span><strong>{effectiveRange.start.slice(0,10)} → {effectiveRange.end?.slice(0,10) ?? active?.end_time?.slice(0,10) ?? '—'}</strong><small>{rangeLoading ? 'Calculating bars…' : rangeError ? rangeError : rangePreview ? `${rangePreview.bars_selected.toLocaleString()} bars will be used` : 'Range unavailable'}</small></div>}
   {rangePreset==='custom' && <div className="card-grid-4" style={{marginBottom:14}}>
    <div><label className="input-label">Start date</label><input className="field" type="date" value={customStart} onChange={e=>setCustomStart(e.target.value)}/></div>
    <div><label className="input-label">End date</label><input className="field" type="date" value={customEnd} onChange={e=>setCustomEnd(e.target.value)}/></div>
   </div>}
   {rangePreview && <div className="card-grid-4">
    <Stat label="Dataset available" value={`${rangePreview.available_start?.slice(0,10)} → ${rangePreview.available_end?.slice(0,10)}`}/>
    <Stat label="Selected" value={`${rangePreview.selected_start?.slice(0,10)} → ${rangePreview.selected_end?.slice(0,10)}`} tone="accent"/>
    <Stat label="Bars selected" value={rangePreview.bars_selected.toLocaleString()} tone={rangePreview.sufficient_for_research?'good':'bad'}/>
    <Stat label="Bars available" value={rangePreview.bars_available.toLocaleString()}/>
   </div>}
   {rangePreview?.requested_out_of_range && <p style={{fontSize:10,color:'var(--text-3)',marginTop:10}}>The requested range extends beyond the uploaded dataset — clamped to the available data shown above rather than fabricated.</p>}
   {rangePreview && !rangePreview.sufficient_for_research && <p style={{fontSize:10,color:'var(--bad)',marginTop:10}}>Insufficient data for reliable walk-forward evaluation in this range (needs ≥{rangePreview.minimum_required_bars} bars). Expand the selected range or reduce the research requirements.</p>}
  </Panel>}
  <Panel eyebrow="02 · CONFIGURATION" title="Walk-forward specification" subtitle={selectedDataset==='demo' ? "Train / test windows, prediction horizon and execution costs." : "Configuration automatically optimized for your uploaded dataset."} action={selectedDataset!=='demo' && autoInfo?.feasible ? <Badge tone="good">AUTO-CONFIGURED</Badge> : undefined}>
   {selectedDataset!=='demo' && autoInfo && !autoInfo.feasible && (
    <div className="notice-box"><SectionLabel>Not enough data for walk-forward validation</SectionLabel>
     <p>{autoInfo.reason}</p>
     <p style={{fontSize:10,color:'var(--text-3)',marginTop:6}}>This dataset has {activeRows?.toLocaleString()} rows at {active?.source_timeframe}. QuantPulse needs at least ~{autoInfo.minimum_required_rows.toLocaleString()} usable bars (after feature warm-up) at the selected research timeframe to run even one fold.</p>
    </div>
   )}
   {selectedDataset!=='demo' && autoInfo && autoInfo.feasible && (
    <div className="card-grid-4" style={{marginBottom:18}}>
     <Stat label="Usable bars" value={autoInfo.usable_bars.toLocaleString()} tone="accent"/>
     <Stat label="Train bars" value={String(autoInfo.train_bars)}/>
     <Stat label="Test bars" value={String(autoInfo.test_bars)}/>
     <Stat label="Est. folds" value={String(autoInfo.estimated_folds)} tone="good"/>
    </div>
   )}
   <div className="card-grid-4">
    <div><label className="input-label">Research timeframe</label><select className="field" value={form.timeframe} onChange={e=>setField('timeframe',e.target.value)}>{researchTimeframeOptions.map(x=><option key={x}>{x}</option>)}</select></div>
    <div><label className="input-label">Spread (pips)</label><input className="field mono" type="number" step="0.1" value={form.spread_pips} onChange={e=>setField('spread_pips',parseFloat(e.target.value))}/></div>
    <div><label className="input-label">Slippage (pips)</label><input className="field mono" type="number" step="0.1" value={form.slippage_pips} onChange={e=>setField('slippage_pips',parseFloat(e.target.value))}/></div>
    <div><label className="input-label">Primary horizon</label><input className="field mono" type="number" step="1" value={form.primary_horizon} onChange={e=>setField('primary_horizon',parseInt(e.target.value,10))}/></div>
   </div>
   <button type="button" className="link-accent" style={{fontSize:10,marginTop:16,background:'none',border:'none',cursor:'pointer',padding:0}} onClick={()=>setAdvancedOpen(o=>!o)}>{advancedOpen?'Hide advanced configuration ▲':'Advanced configuration (train / test / step / embargo bars) ▼'}</button>
   {advancedOpen&&<div className="card-grid-4" style={{marginTop:12}}>{[['train_bars','Train bars'],['test_bars','Test bars'],['step_bars','Step bars'],['embargo_bars','Embargo bars']].map(([key,label])=><div key={key}><label className="input-label">{label}</label><input className="field mono" type="number" step="1" value={form[key as keyof typeof form]} onChange={e=>setField(key as keyof typeof form,parseInt(e.target.value,10))}/></div>)}</div>}
   <div style={{display:'flex',alignItems:'center',gap:12,marginTop:22}}><Button size="lg" onClick={run} disabled={running || (selectedDataset!=='demo' && (!active || !!autoInfo && !autoInfo.feasible || rangeLoading || !!rangeError || rangePreset!=='full' && !rangePreview))}>{running?<><span className="loading-orbit" style={{width:16,height:16}}/>Running research…</>:'Run Research'}</Button>{running&&<span style={{fontSize:10,color:'var(--text-3)'}}>Walk-forward folds · regime filters · cost model</span>}</div>
  </Panel>
  {running&&<Panel eyebrow="EXECUTING" title="Research pipeline"><LoadingBlock label="Executing walk-forward research pipeline…"/></Panel>}
  {result&&!running&&<>
   <div className="metric-grid">
    <Panel className="metric-card"><Stat label="Avg net Sharpe" value={result.metrics?.avg_net_sharpe!=null?result.metrics.avg_net_sharpe.toFixed(3):'n/a'} tone={result.metrics?.avg_net_sharpe>0?'good':result.metrics?.avg_net_sharpe<0?'bad':'default'}/><div style={{marginTop:6}}><MetricBadge metric="sharpe" value={result.metrics?.avg_net_sharpe}/></div></Panel>
    <Panel className="metric-card"><Stat label="Avg max drawdown" value={result.metrics?.avg_max_drawdown!=null?(result.metrics.avg_max_drawdown*100).toFixed(2)+'%':'n/a'} tone="bad"/><div style={{marginTop:6}}><MetricBadge metric="max_drawdown" value={result.metrics?.avg_max_drawdown}/></div></Panel>
    <Panel className="metric-card"><Stat label="Walk-forward folds" value={String(folds.length)}/></Panel>
    <Panel className="metric-card"><Stat label="Experiment ID" value={result.experiment?.experiment_id?.slice(0,12)??'—'} tone="accent"/></Panel>
   </div>
   <Panel eyebrow="03 · EVIDENCE" title="Out-of-sample fold report" subtitle="Metrics below are returned by the research backend and already reflect configured costs.">
    <FoldRobustnessWarning nFolds={folds.length}/>
    <div className="table-wrap"><table className="data-table">
     <thead><tr><th>Fold</th><th>Net Sharpe</th><th>Interpretation</th><th>Sortino</th><th>Max DD</th><th>Hit Rate</th><th>Leakage</th></tr></thead>
     <tbody>{folds.map((f:any)=><tr key={f.fold_id}>
      <td className="mono link-accent">{f.fold_id}</td>
      <td className="mono" style={{color:f.risk_report?.sharpe>0?'var(--good)':f.risk_report?.sharpe<0?'var(--bad)':'var(--text-2)'}}>{f.risk_report?.sharpe?.toFixed(3)??'—'}</td>
      <td><MetricBadge metric="sharpe" value={f.risk_report?.sharpe}/></td>
      <td className="mono">{f.risk_report?.sortino?.toFixed(3)??'—'}</td>
      <td className="mono">{f.risk_report?.max_drawdown!=null?(f.risk_report.max_drawdown*100).toFixed(2)+'%':'—'}</td>
      <td className="mono">{f.risk_report?.hit_rate!=null?(f.risk_report.hit_rate*100).toFixed(1)+'%':'—'}</td>
      <td>{f.leakage_check?.ok?<Badge tone="good">OK</Badge>:<Badge tone="bad">FAIL</Badge>}</td>
     </tr>)}</tbody>
    </table></div>
    <p style={{fontSize:10,color:'var(--text-3)',lineHeight:1.7,marginTop:14}}>The displayed Sharpe is the backend&apos;s net figure after the configured spread, slippage and latency assumptions. Results shown come from the {selectedDataset==='demo'?'demo synthetic dataset':'uploaded dataset'} ({result.instrument} · {result.timeframe}).</p>
    <MetricHeuristicsNote/>
    <div style={{marginTop:16}}><a href="/alpha"><Button size="lg">Continue to Alpha Explorer →</Button></a></div>
   </Panel>
  </>}
 </div>;
}
export default function ResearchPage(){return <Suspense fallback={<LoadingBlock label="Loading Research Lab…"/>}><ResearchLabInner/></Suspense>}
