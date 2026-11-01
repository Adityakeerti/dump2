// Thin fetch helpers. All URLs are relative and match the Caddy routes (see vite.config.js).

export async function getJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* non-JSON error */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

export const postJSON = (url, body, headers = {}) =>
  getJSON(url, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });

export const twinControl = (body) => postJSON("/api/twin/control", body);
export const cityControl = (body) => postJSON("/api/city/control", body);
export const explainDecision = (decision) => postJSON("/api/city/explain", { decision });

// Root-cause rehearsal (the RL repo's diagnosis pipeline, mounted under the twin).
export async function runDiagnosis({ corridor, scenario, start, end, seed }, onStatus) {
  const job = await postJSON("/api/twin/diagnosis/rehearsal", {
    corridor_name: corridor, scenario_name: scenario, start_time_sec: start, end_time_sec: end, seed,
  });
  for (let i = 0; i < 240; i++) {
    const st = await getJSON(`/api/twin/diagnosis/jobs/${job.job_id}`);
    onStatus?.(st.status);
    if (st.status === "COMPLETED") return getJSON(`/api/twin/diagnosis/situations/${job.job_id}`);
    if (st.status === "ERROR") throw new Error(st.error || "diagnosis failed");
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("diagnosis timed out");
}

// The voice agent's event log is admin-only. In DEMO_MODE the agent issues dev tokens.
let agentToken = null;
export async function agentEvents(after = 0) {
  if (!agentToken) {
    const t = await postJSON("/agent/api/auth/dev-token", { user_id: "ops-dashboard", role: "admin" });
    agentToken = t.token;
  }
  try {
    return await getJSON(`/api/agent/events?after=${after}&limit=100`, { headers: { Authorization: `Bearer ${agentToken}` } });
  } catch (e) {
    if (String(e.message).startsWith("401")) agentToken = null;
    throw e;
  }
}

// Root-cause tracing: deterministic pipeline in the twin, then LLM reasoning over its evidence.
export const traceRootCause = (cell) => postJSON("/api/twin/diagnose", { cell });
export const reasonRootCause = (cell, diagnosis) => postJSON("/api/city/root-cause", { cell, diagnosis });
