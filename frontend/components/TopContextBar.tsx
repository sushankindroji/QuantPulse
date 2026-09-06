"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useActiveResearch } from "@/lib/research-context";

type ApiStatus = "checking" | "online" | "offline";

/** Replaces the previously hardcoded "GBP_CAD / 1H" strip in the persistent
 * top bar with whatever is actually active — an uploaded dataset, an
 * explicit demo selection, or an honest "no active dataset" state. This is
 * the one piece of global chrome visible on every page, so it's the
 * clearest place a stale hardcoded instrument could mislead the user. */
function useApiStatus(): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api
        .health()
        .then(() => {
          if (!cancelled) setStatus("online");
        })
        .catch(() => {
          if (!cancelled) setStatus("offline");
        });
    };
    check();
    const interval = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return status;
}

function ApiStatusPill({ status }: { status: ApiStatus }) {
  const label = status === "online" ? "ONLINE" : status === "offline" ? "OFFLINE" : "CHECKING";
  const color = status === "online" ? "var(--good)" : status === "offline" ? "var(--bad)" : "var(--text-3)";
  return (
    <span>
      API <i style={{ color }}>{label}</i>
    </span>
  );
}

export function TopContextBar() {
  const active = useActiveResearch();
  const apiStatus = useApiStatus();
  const isUploaded = !!active?.dataset && active.dataset.dataset_id !== "demo" && !active.dataset.is_synthetic;

  if (!active) {
    return (
      <div className="top-context">
        <div><span className="context-dot" /> QUANT RESEARCH ENVIRONMENT</div>
        <div className="context-right"><span>NO ACTIVE DATASET</span><span className="context-divider" /><ApiStatusPill status={apiStatus} /></div>
      </div>
    );
  }

  return (
    <div className="top-context">
      <div><span className="context-dot" /> QUANT RESEARCH ENVIRONMENT</div>
      <div className="context-right">
        <span>{active.instrument}</span>
        <b>{active.timeframe}</b>
        <span className="context-divider" />
        <span style={{ opacity: 0.75 }}>{isUploaded ? "UPLOADED" : "DEMO"}</span>
        <span className="context-divider" />
        <ApiStatusPill status={apiStatus} />
      </div>
    </div>
  );
}
