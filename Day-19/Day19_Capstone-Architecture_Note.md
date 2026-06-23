# Day 19 Capstone Colab 2 - Architecture Note

## Goal

This notebook demonstrates an ordering agent that combines:

- Redis short-term memory for recent conversation context.
- A vector store for long-term semantic recall.
- SQLite tools for inventory and order creation.
- Redis Streams for asynchronous confirmation email jobs.
- A worker that processes queued email jobs outside the agent's main reasoning path.

## Components

### Agent Loop

The agent receives the user request, builds memory context, and chooses tools in sequence. For a successful order it follows this flow:

`recall_memory -> check_inventory -> create_order -> send_confirmation -> check_job -> remember_memory`

In live mode, Claude decides the tool calls. In offline mode, the notebook uses a scripted mock chain so the capstone can still run without an API key.

### Redis Short-Term Memory

Recent conversation turns are stored in Redis as a bounded list:

`hist:<session_id>`

Each turn is stored as JSON with role, content, and timestamp. The memory layer uses `RPUSH` and `LTRIM` so the prompt receives only the most recent turns instead of unbounded history.

### Long-Term Vector Recall

Durable facts and useful order outcomes are stored in a small local vector store. Each memory is embedded as a stable hashed bag-of-words vector and searched with cosine similarity.

The notebook exposes this through two tools:

- `recall_memory(query, k)` searches durable memories.
- `remember_memory(text, kind)` stores a new durable memory.

For production, this interface can be replaced with Chroma, FAISS, pgvector, Redis vector search, or a managed vector database using model-generated embeddings.

### Order Tools

SQLite stores inventory and orders. All database access goes through parameterized SQL.

- `check_inventory(sku)` reads product availability.
- `create_order(sku, qty)` validates stock, decrements inventory, and creates the order.

### Async Email Queue

`send_confirmation(to, order_id)` does not send email inline. It writes a job to a Redis Stream:

`emails`

The job status is tracked with:

`jobresult:<job_id>`

This keeps the agent turn fast and separates orchestration from side effects.

### Worker

The worker reads from the Redis Stream using a consumer group:

`mailers`

It processes queued email jobs, writes the final job result, and acknowledges messages with `XACK`.

## Data Flow

1. User asks to place an order.
2. Agent loads recent Redis memory and relevant vector memories.
3. Agent checks inventory.
4. Agent creates the order if stock is available.
5. Agent queues the confirmation email.
6. Worker processes the queued email.
7. Agent checks job status.
8. Agent stores a concise long-term memory about the completed order.
9. Agent appends the final response to Redis short-term memory.

## Why This Design

Short-term Redis memory keeps active conversation context fast and bounded. Vector recall keeps durable knowledge searchable without stuffing every past fact into the prompt. Redis Streams decouple slow or failure-prone side effects from the agent loop, which makes the order workflow easier to reason about and safer to extend.

## Files

- Notebook: `Day19_Capstone-Colab2_Chaining_Redis_Event_Queue.ipynb`
- Architecture note: `Day19_Capstone-Colab2_Architecture_Note.md`
