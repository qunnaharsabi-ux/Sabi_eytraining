# Requirements Document

## Introduction

This document specifies the requirements for a rate limiter middleware component for an Express.js API. The middleware enforces per-client request limits using a sliding window algorithm backed by Redis Sorted Sets. It identifies clients by their Authorization token when present, falling back to the client IP address. When a client exceeds its quota, the middleware returns HTTP 429 Too Many Requests. Standard rate-limit response headers are included on every response so clients can self-throttle. Error handling ensures the API continues to function even when the Redis connection is unavailable.

## Glossary

- **Middleware**: An Express.js function with the signature `(req, res, next)` that intercepts HTTP requests before they reach route handlers.
- **Rate_Limiter**: The middleware component described in this document.
- **Client**: The entity making HTTP requests, identified either by Authorization token or IP address.
- **Client_Key**: The unique string used to identify a Client for rate-limiting purposes; derived from the Authorization header value or the client IP address.
- **Window**: The 60-second sliding time interval within which request counts are tracked.
- **Request_Count**: The number of requests a Client has made within the current Window.
- **Limit**: The maximum number of requests permitted per Client per Window (100).
- **Redis**: The external in-memory data store used to persist sliding window state.
- **Sorted_Set**: A Redis data structure that maps string members to floating-point scores; used to store per-request timestamps for the sliding window.
- **Reset_Time**: The Unix timestamp (in seconds) at which the oldest request in the current window will expire, i.e., when the count drops by at least one.
- **Authorization_Header**: The HTTP `Authorization` request header whose value, when present, serves as the Client_Key.

---

## Requirements

### Requirement 1: Client Identification

**User Story:** As an API operator, I want each client to be identified by its Authorization token when one is provided, so that authenticated users share a per-token quota rather than a per-IP quota.

#### Acceptance Criteria

1. WHEN an HTTP request contains an `Authorization` header, THE Rate_Limiter SHALL derive the Client_Key from the full value of that header.
2. WHEN an HTTP request does not contain an `Authorization` header, THE Rate_Limiter SHALL derive the Client_Key from the client's IP address as reported by the Express.js `req.ip` property.
3. THE Rate_Limiter SHALL use the Client_Key exclusively to look up and update the Client's request count in Redis.

---

### Requirement 2: Sliding Window Rate Limiting

**User Story:** As an API operator, I want each client to be limited to 100 requests per 60-second sliding window, so that short bursts of traffic within that window are counted fairly and not reset artificially by a fixed clock boundary.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL allow a maximum of 100 requests per Client per 60-second sliding Window.
2. WHEN a request arrives, THE Rate_Limiter SHALL record the request timestamp as a member of the Client's Redis Sorted_Set with the current Unix timestamp in milliseconds as both the member value and its score.
3. WHEN a request arrives, THE Rate_Limiter SHALL remove all Sorted_Set members whose score is older than `(current_time_ms - 60000)` before computing the Request_Count.
4. WHEN the Request_Count for a Client is less than the Limit, THE Rate_Limiter SHALL allow the request to proceed to the next Express.js handler.
5. WHEN the Request_Count for a Client equals or exceeds the Limit, THE Rate_Limiter SHALL block the request and return an HTTP 429 response.
6. THE Rate_Limiter SHALL set a Redis TTL of 70 seconds on each Client's Sorted_Set to ensure automatic cleanup of idle keys.

---

### Requirement 3: HTTP 429 Response

**User Story:** As an API client developer, I want to receive a well-formed HTTP 429 response when I exceed the rate limit, so that my application can detect throttling and implement retry logic.

#### Acceptance Criteria

1. WHEN the Request_Count for a Client equals or exceeds the Limit, THE Rate_Limiter SHALL respond with HTTP status code 429.
2. WHEN responding with HTTP 429, THE Rate_Limiter SHALL set the `Content-Type` response header to `application/json`.
3. WHEN responding with HTTP 429, THE Rate_Limiter SHALL include a JSON body with a `message` field containing a human-readable explanation of the rate limit violation.
4. WHEN responding with HTTP 429, THE Rate_Limiter SHALL include the `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers with values appropriate to the current state.

---

### Requirement 4: Rate Limit Response Headers

**User Story:** As an API client developer, I want rate limit information in every response, so that my application can proactively manage request pacing without waiting for a 429.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL set the `X-RateLimit-Limit` response header to the integer value `100` on every response it processes.
2. THE Rate_Limiter SHALL set the `X-RateLimit-Remaining` response header to the number of requests the Client may still make within the current Window, calculated as `max(0, Limit - Request_Count)`.
3. THE Rate_Limiter SHALL set the `X-RateLimit-Reset` response header to the Unix timestamp in seconds at which the oldest recorded request will expire from the Window (i.e., the Reset_Time).
4. WHEN no prior requests have been recorded for a Client, THE Rate_Limiter SHALL set `X-RateLimit-Reset` to the current Unix timestamp plus 60 seconds.

---

### Requirement 5: Redis Sorted Set Implementation

**User Story:** As a backend engineer, I want the sliding window to be implemented with Redis Sorted Sets, so that the algorithm is accurate across multiple API server instances without shared in-process state.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL store per-Client sliding window state in a Redis Sorted_Set keyed by the Client_Key.
2. WHEN recording a new request, THE Rate_Limiter SHALL use a Redis pipeline or transaction to atomically execute the following operations: ZADD the current timestamp, ZREMRANGEBYSCORE of expired members, ZCARD to obtain the Request_Count, and EXPIRE to refresh the TTL.
3. THE Rate_Limiter SHALL use the current time in milliseconds as the score for each Sorted_Set member to support sub-second precision in the sliding window.

---

### Requirement 6: Redis Connection Failure Handling

**User Story:** As an API operator, I want the API to remain available when Redis is unreachable, so that a caching-layer outage does not cause a complete API outage.

#### Acceptance Criteria

1. IF a Redis operation throws an error, THEN THE Rate_Limiter SHALL log the error using the application logger without exposing internal details to the API caller.
2. IF a Redis operation throws an error, THEN THE Rate_Limiter SHALL allow the request to proceed to the next Express.js handler rather than returning an error response.
3. IF a Redis operation throws an error, THEN THE Rate_Limiter SHALL NOT set `X-RateLimit-Limit`, `X-RateLimit-Remaining`, or `X-RateLimit-Reset` headers on the response.

---

### Requirement 7: Unit Test Coverage

**User Story:** As a backend engineer, I want comprehensive unit tests for the rate limiter middleware, so that regressions are caught before deployment.

#### Acceptance Criteria

1. THE Test_Suite SHALL include unit tests that verify the Rate_Limiter allows requests when the Request_Count is below the Limit.
2. THE Test_Suite SHALL include unit tests that verify the Rate_Limiter blocks requests and returns HTTP 429 when the Request_Count equals or exceeds the Limit.
3. THE Test_Suite SHALL include unit tests that verify the correct `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` header values are set for both allowed and blocked requests.
4. THE Test_Suite SHALL include unit tests that verify the Rate_Limiter falls back gracefully when a simulated Redis error occurs, allowing the request to proceed without rate limit headers.
5. THE Test_Suite SHALL include unit tests that verify Client_Key derivation: Authorization header takes precedence over IP address when both are present.
6. THE Test_Suite SHALL mock the Redis client to avoid requiring a live Redis instance during unit test execution.
