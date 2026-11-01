# Civic simulator: residents → complaint portal → Municipal / Police agents → RL root-cause investigation

A synthetic city (6×6 blocks, 9 wards, 360 residents) where hidden infrastructure faults and crime sources
produce symptoms. Residents report what they see to a complaint portal. The portal routes each complaint to one of
two department agents, the **Municipal Corporation** (roads, water, sewer, waste, streetlights) or the **Police**
(crime, traffic). A learned policy decides, each tick, **which asset each department inspects or repairs**, so the
city reaches the root cause instead of patching symptoms. Everything is labelled **SIMULATED**.

```
hidden causes ──► symptoms on blocks ──► residents report ──► complaint portal ──► routed to department
 (leak, sewer        (spread along pipe       (persona, ward        (taxonomy from            │
  blockage, waste     trees / routes /         under-reporting)      complaint_module)        ▼
  route, feeder,      feeders, over time)                                         tracer: candidates + evidence
  crime den) + random                                                                        │
  potholes, traffic                                                                          ▼
                     ◄──────────── inspect / repair / wait ◄──── RL policy (Double DQN, shared by both depts)
```

## What RL does here, and what it does not

The CitySense design doc says RL must not decide causes. This module follows that rule:

* **The deterministic tracer** (`app/tracer.py`) reads only public data: the complaint log, the work log, the
  infrastructure maps and the mechanism table. For every asset it measures how well the asset's zone explains recent
  complaints: coverage, lift over the city average, and whether the asset's own block reported first. It proposes
  candidate actions (`inspect` / `repair` per asset, plus `wait`).
* **The RL policy** (`app/dqn.py`, `app/train.py`) learns the *investigation and dispatch strategy*: which
  candidate to act on, when to inspect before repairing, when a symptom fix is worth a crew, and when to wait.
* **A root cause is confirmed only by a field result**: an inspection or repair in the simulation found the fault.
  `app/diagnosis.py` then reports where it is, when residents first noticed, why (the layer's mechanism), how it
  spread, and which complaints went to the *other* department. For example, police theft complaints whose cause is
  a municipal streetlight feeder. Unconfirmed candidates are listed as `HYPOTHESIS`.

## LLM reasoning (same pattern and guardrails as city_sim)

LLMs explain and critique; they never decide. Confirmation still comes only from a field inspection or repair.

| Endpoint | Model | What it does |
|---|---|---|
| `POST /api/civic/root-cause {asset_name}` | Groq `openai/gpt-oss-120b` (strict JSON schema, reasoning trace) → `gpt-oss-20b` → local Gemma → deterministic summary | Reviews one confirmed root cause or hypothesis: step-by-step reasoning with cited evidence, where and when it started, agreement with the system, alternatives (incl. background noise), how the departments' policy did, actions with owners, caveats, calibrated confidence. Cached per root cause (per tick for hypotheses). |
| `POST /api/civic/explain {action_id}` | local Gemma | Explains one crew decision from what the policy saw: the chosen candidate's features and Q-value vs the next-best alternatives. |
| (live loop) | local Gemma | Citizen agents write a few complaints per tick in their own words (`app/agents.py`). |

Guardrails (`app/reasoning.py`, `tests/test_reasoning.py`): evidence is built from the portal, the work log and the
public maps only, and a test checks that no ground-truth field (cause type, onset, identified tick) is ever sent;
every number in a root-cause answer is checked against the evidence at rounding tolerance and unmatched ones are
returned in `ungrounded_numbers` (shown as a warning); a decision explanation that mentions a number absent from the
decision record is replaced by the deterministic explanation. The Groq key comes from `GROQ_API_KEY` or
`SmartCity/.env` and is never logged. The model settings live under `live.root_cause` in `config.yaml`, which the
config hash excludes, so changing them does not invalidate the trained checkpoint.

## The world

| Layer (department) | Hidden cause | Where the symptoms appear |
|---|---|---|
| water main tree (Municipal) | `water_main_leak` | low pressure in every block downstream of the leak, potholes over it, traffic jams on arterials |
| sewer tree (Municipal) | `sewer_blockage` | overflow and smell **upstream** of the blockage, spreading one hop per tick |
| waste routes (Municipal) | `missed_waste_route` | garbage on the whole route, then stray animals, then choked drains |
| streetlight feeders (Municipal) | `streetlight_feeder_fault` | dark streets, then theft and harassment that the **Police** receive |
| crime premises (Police) | `crime_hotspot` | theft, disorder and harassment around it, spreading outward |
| road, traffic (both) | none: random potholes, background traffic | symptom-only work: patch potholes, deploy a traffic marshal |

Background noise in every category, random potholes and per-ward under-reporting are on in every episode. Symptom-only
actions (local desilting, patrols, marshals) hide symptoms for a few ticks, which is why chasing complaints looks like
it works. Every number is an assumption in `config.yaml`.

## Agents from the main pipeline

* **Complaint taxonomy and routing** mirror `complaint_module`'s intake classifier (`pothole / garbage / streetlight /
  drainage` → its department names), extended with police categories.
* **Portal bridge** (`live.portal_bridge`, off by default): forwards a few municipal complaints per tick to
  `complaint_module`'s `POST /api/complaints`. That module's Municipal Intake Agent, guardrail and worker dispatcher then
  run on them. Each forwarded complaint triggers that service's LLM calls, which is why the bridge is off by default.
* **Citizen agents** (`app/agents.py`): a LangGraph graph built like `city_sim`'s, `observe → write (local Gemma) →
  validate → [fallback]`. The simulator decides what happened, where and when. The LLM only rewrites a few complaints
  per tick in the resident's words. Text with digits is rejected (a resident must not invent counts or dates), and the
  template is kept on any failure. Training never calls an LLM.

## Run

```bash
cd civic_sim
PY=../../.venv/bin/python                                  # SmartCity venv (numpy, fastapi, langgraph)
OMP_NUM_THREADS=1 $PY -m app.train                         # ~8 min CPU, writes data/civic_dqn.npz
OMP_NUM_THREADS=1 $PY -m app.evaluate                      # writes reports/civic_rl_results.{md,json}
$PY -m pytest -q                                           # 34 tests
../../.venv/bin/uvicorn app.server:app --port 8005         # or ../run_backends.sh start
```

`OMP_NUM_THREADS=1` matters: the networks are tiny, and multi-threaded BLAS made training many times slower.

**UI**: the dashboard's **Civic Sim** page (`http://localhost:5173/#civic`, needs `cd ../dashboard && npm run dev`) shows the
city in 3D on the same MapLibre + deck.gl stack as the traffic twin. `http://localhost:8005/` is a minimal fallback view.

Endpoints (port 8005): `GET /api/civic/health | map | state | complaints | diagnosis | traces | last_episode`,
`POST /api/civic/control {running, policy, step}`, `POST /api/civic/reset {seed, scenario}`. `scenario` is a list of
cause ids, `[]` for a control episode, or `null` for random. `last_episode` reveals the previous episode's ground truth
next to its diagnosis.

## RL formulation

* **State/action**: per department, up to 71 candidates (top assets per layer by zone mass, by lift and by score, ×
  inspect/repair, + wait). Each candidate is a 30-feature vector, listed in `tracer.feature_names`.
* **Q-network**: Q(s, a) = MLP(features of a), with one network shared by both departments (department one-hot
  feature), like the corridor DQN shares one network across junctions. Double DQN targets over the next state's valid
  candidates, Huber loss, Adam, written in NumPy (`app/dqn.py`, gradient-checked in tests) because the SmartCity venv
  has no torch.
* **Reward (team)**: −0.1 per severity-weighted new complaint, −crew cost per inspection/repair, −penalty for repairing
  a healthy asset, +bonus when a true root cause is first confirmed, +bonus when it is removed.
* **Training**: 1200 episodes on seeds `seed..seed+1199`, 1–2 random causes each. The first 150 episodes follow the
  tracer (teacher-forced, to put successful diagnoses in the replay buffer), then ε-greedy from 1.0 to 0.05 over 900 episodes.
* **Evaluation**: held-out seeds from 300000 (seeds from 100000 were used once to pick 1200 over 600 training
  episodes and are not reported), identical across policies (paired), one scenario per cause type plus
  `mixed` and `control`. Baselines: `tracer` (deterministic ranking: inspect the best candidate, repair once
  confirmed), `complaint_count` (repair whatever has the most complaints on its own block, i.e. today's practice),
  and `random`.

Results: `reports/civic_rl_results.md`.

## Known limits

* Synthetic city, hand-written mechanism table, assumed rates. Nothing here is validated against real complaints.
* Inspections never give false positives; misses are configured per layer. Real inspections are noisier.
* "Started" is when residents first complained in the zone, not the true onset, and a background complaint can make
  it look too early.
* One crew action per department per tick. Real departments run many crews in parallel.
* The tracer is a strong baseline because it is built on the same evidence features. Read the RL-vs-tracer numbers
  as measured. Do not assume RL wins.
