# ChatGPT unauthenticated mobile-chat journey

**Case:** `chatgpt-unauthenticated-mobile-chat-2026-07-21`  
**Status before exact run:** `PENDING_BOUNDED_PUBLIC_INTERACTION`  
**Parent passive audit:** PR `#106` at `2407be212e19a393fcd0d8dd33d9fe444aea663b`

## Question

Can a signed-out user on ChatGPT mobile web submit one benign prompt, observe a streaming/completed response, and retain a usable composer at normal and compact height without horizontal overflow or a visible broken state?

## Bounded scenario

The runner opens `https://chatgpt.com/` with an Android mobile user-agent and a `412×915` viewport. It first proves the public signed-out state by requiring a visible login action and rejecting an account-like state.

It then performs exactly one product action sequence:

1. enter the benign prompt `Reply with exactly: MOBILE WEB OK`;
2. press the visible Send control once;
3. observe whether a Stop control appears during generation;
4. wait for assistant output to become stable;
5. capture the completed state;
6. resize to `412×520` and capture compact-height continuity.

## Safety and privacy boundary

The scenario:

- submits one non-sensitive public prompt;
- does not log in or access an account;
- does not read or expose private conversations;
- does not upload files;
- does not request microphone or camera permission;
- does not call application APIs directly;
- does not bypass a challenge or access control;
- does not fuzz, load test or perform security testing;
- does not persist raw response text.

Persisted message evidence contains only role, length and SHA-256 digest. Screenshots contain only the public test prompt and its public response.

## Evidence captured

- exact route and HTTP state;
- normal and compact viewport geometry;
- composer and visible-control geometry;
- message count, role, text length and SHA-256;
- streaming Stop-control observation;
- response-completion stability;
- scroll distance and horizontal overflow;
- console warnings/errors, uncaught page errors and first-party HTTP error metadata;
- screenshots for initial, drafted, streaming, completed and compact states when available.

## Decision rule

`UNAUTHENTICATED_MOBILE_CHAT_PASS` requires:

- one prompt submission only;
- a visible assistant response containing the requested harmless response fragment;
- no login or account state;
- completion or stable response observation;
- preserved compact-height composer state without horizontal overflow.

A detector signal is not automatically a product defect. Event/telemetry aborts, ancestor-container overlap and generic target-size counts remain subject to the adjudication already established in PR `#106`.

## Authority boundary

The result is an audit artifact only. It does not authorise external reporting, a security claim, deployment, delivery or merge.
