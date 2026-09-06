const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ status: string }>("/health"),
  instruments: () => req<{ primary: string; secondary: string[] }>("/api/instruments"),
  marketDemo: (params: { instrument?: string; timeframe?: string; n_bars?: number } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return req<{ source: string; is_synthetic: boolean; bars: any[] }>(`/api/market/demo?${q}`);
  },
  datasetRange: async (datasetId: string, params: { start?: string; end?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    try {
      return await req<{
        dataset_id: string;
        instrument: string;
        source_timeframe: string;
        available_start: string;
        available_end: string;
        selected_start: string | null;
        selected_end: string | null;
        bars_selected: number;
        bars_available: number;
        requested_out_of_range: boolean;
        sufficient_for_research: boolean;
        minimum_required_bars: number;
      }>(`/api/datasets/${datasetId}/range${q ? `?${q}` : ""}`, { signal: controller.signal });
    } finally {
      window.clearTimeout(timeout);
    }
  },
  datasetCandles: (datasetId: string, limit = 500) =>
    req<{
      dataset_id: string;
      instrument: string;
      source_timeframe: string;
      is_synthetic: boolean;
      source: string;
      total_rows: number;
      points_returned: number;
      bars: any[];
    }>(`/api/datasets/${datasetId}/candles?limit=${limit}`),
  regimes: (params: { instrument?: string; timeframe?: string; n_bars?: number; dataset_id?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return req<{
      method: string;
      current_regime: string;
      current_probabilities: Record<string, number>;
      source: string;
      is_synthetic?: boolean;
    }>(`/api/regimes?${q}`);
  },
  runResearch: (body: Record<string, unknown>) =>
    req<any>("/api/research/run", { method: "POST", body: JSON.stringify(body) }),
  experiments: (limit = 50) => req<{ experiments: any[] }>(`/api/experiments?limit=${limit}`),
  experimentDetail: (id: string) => req<any>(`/api/experiments/${id}`),
  deleteExperiment: (id: string) =>
    req<{ status: string; experiment_id: string }>(`/api/experiments/${id}`, { method: "DELETE" }),
  datasets: (limit = 100) => req<{ datasets: any[] }>(`/api/datasets?limit=${limit}`),
  datasetDetail: (id: string) => req<any>(`/api/datasets/${id}`),
  uploadDataset: async (file: File, instrument?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (instrument) form.append("instrument", instrument);
    const res = await fetch(`${API_URL}/api/datasets/upload`, { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) {
      const err: any = new Error(typeof body.detail === "string" ? body.detail : body.detail?.message || "Upload failed");
      err.detail = body.detail;
      err.status = res.status;
      throw err;
    }
    return body as {
      dataset_id: string;
      instrument: string;
      source_timeframe: string;
      rows: number;
      start_time: string;
      end_time: string;
      columns: string[];
      timezone: string;
      content_hash: string;
      warnings: { code: string; message: string; severity: string }[];
      data_confidence: {
        status: "DATA_READY" | "DATA_READY_WITH_CLEANING" | "DATA_NEEDS_REVIEW" | "DATA_REJECTED";
        uploaded_rows: number;
        usable_rows: number;
        removed_rows: number;
        detected_instrument: string | null;
        detected_timeframe: string;
        data_source: string;
      };
    };
  },
};
