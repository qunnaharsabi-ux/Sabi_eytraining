# Implementation Plan: Rate Limiter Middleware

## Overview

Implement a TypeScript Express.js rate limiter middleware using a sliding window algorithm backed by Redis Sorted Sets. The implementation is structured as a factory function with pure helper functions to enable dependency injection and thorough unit/property-based testing with fast-check.

## Tasks

- [ ] 1. Set up project structure, dependencies, and core TypeScript interfaces
  - Initialize the TypeScript project (or add to existing) with `tsconfig.json` if not present
  - Install runtime dependencies: `express`, `redis` (or `ioredis`)
  - Install dev dependencies: `jest` (or `vitest`), `ts-jest`, `fast-check`, `@types/express`, `@types/jest`
  - Create `src/middleware/` directory structure
  - Define and export all interfaces: `RateLimiterOptions`, `Logger`, `RedisClient`, `RedisPipeline`, `RateLimitState`, `RateLimitHeaders` in `src/middleware/rateLimiter.ts`
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 2. Implement `deriveClientKey` helper
  - [ ] 2.1 Implement the `deriveClientKey` pure function in `src/middleware/deriveClientKey.ts`
    - Return the full `Authorization` header value when present on the request
    - Fall back to `req.ip` when the header is absent
    - Fall back to the string `"unknown"` when `req.ip` is also absent/undefined
    - Export the function for direct unit and property testing
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 2.2 Write property test for `deriveClientKey` (Property 1)
    - **Property 1: Client Key Derivation Priority**
    - Use `fc.string()` for the Authorization header value and `fc.ipV4()` / `fc.ipV6()` for IP addresses
    - Assert: when Authorization header is present, result equals header value
    - Assert: when Authorization header is absent, result equals `req.ip`
    - Assert: both conditions never hold simultaneously
    - Tag: `// Feature: rate-limiter-middleware, Property 1: Client Key Derivation Priority`
    - **Validates: Requirements 1.1, 1.2**
    - _Minimum 100 iterations_

  - [ ]* 2.3 Write unit tests for `deriveClientKey`
    - Test: uses Authorization header when present
    - Test: falls back to `req.ip` when Authorization absent
    - Test: uses `"unknown"` when both are absent/undefined
    - _Requirements: 1.1, 1.2_

- [ ] 3. Implement `buildRateLimitHeaders` helper
  - [ ] 3.1 Implement the `buildRateLimitHeaders` pure function in `src/middleware/buildRateLimitHeaders.ts`
    - Accept a `RateLimitState` argument (`limit`, `requestCount`, `oldestTimestampMs`, `nowMs`)
    - Compute `X-RateLimit-Limit` as `String(limit)`
    - Compute `X-RateLimit-Remaining` as `String(Math.max(0, limit - requestCount))`
    - Compute `X-RateLimit-Reset`: if `oldestTimestampMs` is non-null use `floor(oldestTimestampMs / 1000) + 60`, otherwise `floor(nowMs / 1000) + 60`
    - Return a `RateLimitHeaders` object
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 3.2 Write property test for `buildRateLimitHeaders` — Remaining formula (Property 4)
    - **Property 4: Remaining Header Formula**
    - Use `fc.integer({ min: 0, max: 200 })` for `requestCount`
    - Assert: `X-RateLimit-Remaining` equals `String(Math.max(0, 100 - requestCount))` for all inputs
    - Tag: `// Feature: rate-limiter-middleware, Property 4: Remaining Header Formula`
    - **Validates: Requirements 4.2**
    - _Minimum 100 iterations_

  - [ ]* 3.3 Write property test for `buildRateLimitHeaders` — Reset formula (Property 5)
    - **Property 5: Reset Header Formula**
    - Use `fc.integer({ min: 1, max: 10 })` for set size and arrays of `fc.date()` for timestamps
    - Assert: when `oldestTimestampMs` is non-null, header equals `String(Math.floor(oldestTimestampMs / 1000) + 60)`
    - Assert: when `oldestTimestampMs` is null, header equals `String(Math.floor(nowMs / 1000) + 60)`
    - Tag: `// Feature: rate-limiter-middleware, Property 5: Reset Header Formula`
    - **Validates: Requirements 4.3, 4.4**
    - _Minimum 100 iterations_

  - [ ]* 3.4 Write unit tests for `buildRateLimitHeaders`
    - Test: Limit header always equals `"100"`
    - Test: Remaining decreases linearly for counts below 100
    - Test: Remaining clamps to `"0"` for counts >= 100
    - Test: Reset uses oldest timestamp when window is non-empty
    - Test: Reset uses `now + 60` when window is empty (`oldestTimestampMs` is null)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 4. Implement the `createRateLimiter` middleware factory
  - [ ] 4.1 Implement the Redis pipeline execution logic in `src/middleware/rateLimiter.ts`
    - Import `deriveClientKey` and `buildRateLimitHeaders`
    - Generate a unique member string using millisecond timestamp plus a 4-hex-char nonce: `"<ts>:<nonce>"`
    - Build and execute a five-command pipeline: `ZADD`, `ZREMRANGEBYSCORE` (prune window), `ZCARD`, `ZRANGE 0 0 WITHSCORES` (for reset time), `EXPIRE 70`
    - Extract `Request_Count` from pipeline result index 2; guard against `null` (treat as 0)
    - Extract `oldestTimestampMs` from pipeline result index 3; guard against `null`/empty (treat as `null`)
    - Apply defaults: `limit = 100`, `windowMs = 60000`, `ttlSeconds = 70`
    - _Requirements: 2.2, 2.3, 2.6, 5.1, 5.2, 5.3_

  - [ ] 4.2 Implement the allow/block decision and response logic
    - Call `buildRateLimitHeaders` with current state and set all three `X-RateLimit-*` headers on the response
    - If `Request_Count < limit`: call `next()` and return
    - If `Request_Count >= limit`: set status 429, set `Content-Type: application/json`, send the 429 JSON body with the `message` field, and do NOT call `next()`
    - _Requirements: 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3_

  - [ ] 4.3 Implement fail-open error handling
    - Wrap the pipeline execution in `try/catch`
    - On any Redis error: call `logger.error('Rate limiter Redis error', { error: err.message, clientKey })`, call `next()`, and return without setting any `X-RateLimit-*` headers
    - Do NOT forward the error to `next(err)` — this is the fail-open contract
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 5. Checkpoint — verify core implementation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Write property-based and unit tests for the middleware
  - [ ] 6.1 Write property test for allow/block decision (Property 2)
    - **Property 2: Allow/Block Decision Threshold**
    - Use `fc.integer({ min: 0, max: 200 })` for `Request_Count`; mock pipeline to return that count
    - Assert: count < 100 → `next()` is called and 429 is NOT sent
    - Assert: count >= 100 → HTTP 429 is returned and `next()` is NOT called
    - Tag: `// Feature: rate-limiter-middleware, Property 2: Allow/Block Decision Threshold`
    - **Validates: Requirements 2.1, 2.4, 2.5, 3.1**
    - _Minimum 100 iterations_

  - [ ]* 6.2 Write property test for sliding window pruning invariant (Property 3)
    - **Property 3: Sliding Window Pruning Invariant**
    - Use an array of `fc.integer()` timestamps and `fc.date()` for `now_ms`
    - Simulate `ZREMRANGEBYSCORE` logic and assert no remaining member has score < `(now_ms - 60000)`
    - Tag: `// Feature: rate-limiter-middleware, Property 3: Sliding Window Pruning Invariant`
    - **Validates: Requirements 2.3**
    - _Minimum 100 iterations_

  - [ ]* 6.3 Write property test for fail-open behavior (Property 6)
    - **Property 6: Fail-Open Behavior**
    - Use any request shape; mock pipeline `exec` to throw an error
    - Assert: `next()` is called, no `X-RateLimit-*` headers are set, 429 is not returned
    - Tag: `// Feature: rate-limiter-middleware, Property 6: Fail-Open Behavior`
    - **Validates: Requirements 6.1, 6.2, 6.3**
    - _Minimum 100 iterations_

  - [ ]* 6.4 Write unit tests for the allow path (count < 100)
    - Use the mock pipeline pattern from the design's `mockPipeline` / `mockRedis` pattern
    - Test: `next()` is called
    - Test: `X-RateLimit-Limit` is set to `"100"`
    - Test: `X-RateLimit-Remaining` is set to `String(100 - count)`
    - Test: `X-RateLimit-Reset` is set correctly
    - _Requirements: 2.4, 4.1, 4.2, 4.3, 7.1, 7.3_

  - [ ]* 6.5 Write unit tests for the block path (count >= 100)
    - Test: status 429 is returned
    - Test: `Content-Type` is `application/json`
    - Test: JSON body contains the `message` field
    - Test: `X-RateLimit-*` headers are still set correctly on 429 responses
    - Test boundary: count = 99 → allow; count = 100 → block
    - _Requirements: 2.5, 3.1, 3.2, 3.3, 3.4, 7.2, 7.3_

  - [ ]* 6.6 Write unit tests for Redis pipeline commands
    - Test: `ZADD` is called with the correct millisecond timestamp as score
    - Test: `ZREMRANGEBYSCORE` is called with `-inf` and `(now_ms - 60000)` as bounds
    - Test: `ZCARD` is called once per request
    - Test: `EXPIRE` is called with a 70-second TTL
    - _Requirements: 2.2, 2.3, 2.6, 5.2, 5.3_

  - [ ]* 6.7 Write unit tests for fail-open behavior
    - Test: `next()` is called when Redis throws
    - Test: no `X-RateLimit-*` headers are set on Redis error
    - Test: `logger.error` is called with error details
    - _Requirements: 6.1, 6.2, 6.3, 7.4_

  - [ ]* 6.8 Write unit tests for edge cases
    - Test: first request for a client (empty set → reset = now + 60)
    - Test: Authorization header takes precedence over IP when both are present
    - Test: `req.ip` undefined → Client_Key falls back to `"unknown"`
    - _Requirements: 1.1, 1.2, 4.4, 7.5_

- [ ] 7. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- All tests mock the Redis client as shown in the design; no live Redis instance is required
- The property tests require `fast-check ^3.x` and run a minimum of 100 iterations each
- Each task references specific requirements for traceability
- Checkpoints (tasks 5 and 7) ensure incremental validation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2", "3.3", "3.4", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8"] }
  ]
}
```
