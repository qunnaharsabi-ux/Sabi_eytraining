Original Problem
Multi-agent pipeline only printed raw text — no way to debug failures or track progress.

Step 1 — Correlation IDs 
Goal: Tag every event with a run ID and agent ID.
Key changes:
Added trace_id (one per run) and span_id (one per agent) using uuid
Replaced progress_listener with make_listener() closure to carry trace_id


Step 2 — Progress & Pace ✅
Goal: Know how far the pipeline has gone, how fast, and how long each agent took.
Key changes:
Added steps_done counter inside closure → pipeline % and throughput
Added agent_start timer in Orchestrator → per-agent duration




