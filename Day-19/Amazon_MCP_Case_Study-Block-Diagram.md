The four diagrams map directly to the case study's design axes:

Diagram 1 — Trust boundary & topology shows the structural fact that you're always dealing with two separately-governed servers from day one, and why the SP-API server's placement (self-hosted vs. third-party) is the most consequential decision in the whole architecture.

Diagram 2 — Human-in-the-loop gate captures the three-tier risk classification: autonomous reads, auto-with-logging reversible writes, and hard-gated money/Buy Box operations. The repricer gets its own box because it's the highest-frequency, highest-danger tool and must be built as a constrained instrument with hard floor/ceiling limits.

Diagram 3 — Authorization granularity shows how SP-API tokens are scoped to least-privilege roles, with a Restricted Data Token minted only on demand for PII-bearing tools. The agency fan-out pattern (one app credential, per-client isolation) limits blast radius to a single account on any compromise.

Diagram 4 — Transport, state, discovery & governance covers the operational decisions: async report job modeling (not fake synchronous calls), quota-aware throttling, event subscriptions over polling, static pinned discovery as a security control, and the prompt-injection fence around untrusted Amazon content (reviews, buyer messages).