# Population simulator: LangGraph people-cluster agents on local Gemma

Spawns people clusters (neighbourhoods in `config.yaml`) whose travel is decided by LangGraph agents
calling **Gemma-4-E2B** through `llama-server`. Their trips enter the live digital twin as **car
clusters**. The twin's signals, controlled by the RL policy, then decide how long each car cluster waits.

```
observe ──> decide (Gemma, JSON-schema constrained) ──> validate ──┬──> dispatch ──> POST /api/twin/trips
                                                                   └─> fallback (rule) ─┘
```

* **The LLM picks categories, not numbers.** It chooses intent ∈ {commute, errand, leisure, stay_home},
  departure ∈ {now, delay_short, delay_long}, share ∈ {low, medium, high} and gives a reason. Vehicles =
  population × `share_fraction` × `car_ratio`, split into car clusters of ≤ `car_cluster_size` vehicles,
  with departures drawn uniformly in `departure_window_sec` (seeded).
* **Feedback loop.** Every round the agent sees its route's speed, jammed links, entry backlog, an active
  disruption, and the realised delay of its previous car clusters (memory), so congestion created by the
  RL policy's signal decisions feeds back into demand.
* **Failure is visible.** If the LLM is down, times out or returns an invalid plan, a rule-based fallback
  decides instead. The trace marks it `rule_fallback`.
* **Explanations.** `POST /api/city/explain` asks Gemma to explain one RL decision in plain language. Any
  number in the reply that is not in the decision record makes the service return the deterministic
  explanation instead (`grounded: false`). This guards numbers only, not the wording.

## Population (randomised)

`population.generate: true` (default) builds the people clusters from a seed instead of a hand-written list
(`app/population.py`): 28 neighbourhoods at random points within `spread_m` (420 m) of the twin's real roads, at least
45 m off the carriageway and 110 m apart; sizes drawn from a lognormal (`size_sigma` 0.9: a few large, many small)
normalised to `total_population` (24 000); personas drawn from weighted categories; each attached to its nearest
trip entry. Names are drawn from Dehradun localities (labels only). Set `generate: false` and list `clusters` to
hand-place them instead.

## Root-cause reasoning (`POST /api/city/root-cause {cell, diagnosis?}`)

Takes the twin's deterministic root-cause trace (`/api/twin/diagnose`) and has **Groq `openai/gpt-oss-120b`**
(a reasoning model; strict JSON-schema output, `reasoning_effort: medium`) explain it. Chosen because it reasons
explicitly before answering, follows a strict schema and answers in ~5 s on Groq. Fallbacks: `openai/gpt-oss-20b` →
local Gemma → the deterministic ranking. The key comes from `GROQ_API_KEY` or `SmartCity/.env` and is never logged.

Guardrails: the planted scenario name, ground truth and the repo's action-template strings are removed from the
evidence before the call; every number in the answer is checked against the evidence at rounding-level tolerance
and unmatched ones are returned in `ungrounded_numbers` (shown as a warning in the UI). The ranking stays
deterministic: the model must say whether it agrees and why.

## Run

```bash
# llama-server (GPU): ~/llama-fork/build/bin/llama-server -m <gemma .gguf> -ngl 99 -c 16384 -np 4 --reasoning off --port 8090
cd city_sim && ../../.venv/bin/uvicorn app.server:app --port 8004      # or ../run_backends.sh start
../../.venv/bin/python -m pytest -q tests
```

Endpoints: `GET /api/city/health`, `GET /api/city/clusters`, `GET /api/city/traces`,
`POST /api/city/control {enabled, plan_now}`, `POST /api/city/explain {decision}`.
Env overrides: `TWIN_URL`, `LLM_BASE_URL`, `CITY_SIM_CONFIG`.

Each cluster's walking path (neighbourhood → corridor entry) comes from the public OSRM foot router on first
start and is cached in `data/walk_paths.json` (`walk_router_url` empty = straight lines). The dashboard animates
people walking it before their car clusters depart.

## Known limits

* Gemma-4-E2B shows low plan diversity (it mostly picks `commute / delay_short`). Demand still varies
  through clusters, memory and departure jitter, but don't read agent "behaviour" as a calibrated
  travel-demand model.
* Clusters are placed next to the twin's entry points. The twin's map anchor is set to Dehradun in the RL repo's
  `config/live.yaml` (`map_center_lat/lon`), but the corridor geometry is schematic: it does not follow real roads.
