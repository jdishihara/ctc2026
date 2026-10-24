# HTTP connection reuse experiment

The installed urllib handler explicitly sets `Connection: close` and closes its
socket after each request. The live adapter currently uses that handler for each
GET, order submission, cancellation, and conversion.

Twelve read-only clock requests were alternated between the current adapter's
transport and a persistent HTTPS connection. Six requests per mode, on one host
in one short window, gave median elapsed times of 106.35 ms and 32.42 ms.
All responses were HTTP 200; the five later persistent requests reused the same
socket. [Every observation](evidence/http-connection-reuse.json) is preserved.

This measures clock GET requests, not order acknowledgements, fills, or profit.
It motivates a separately tested optional transport. Strategy parameters and the
running frozen market evaluation remain unchanged. Live activation still
requires resolving the shared-account ownership question.

## Implemented behavior

- Reuse one connection per exchange instance, with serialized requests and full
  response-body consumption.
- Preserve HTTP error details and current account-reconciliation behavior.
- Reset a failed connection and propagate the error. Never automatically retry
  an order, cancellation, or conversion after an uncertain response.
- Preserve the existing urllib path by default; expose connection reuse as an
  explicit option for subsequent controlled validation.
- Respect configured proxies through the existing urllib path; never silently
  bypass them to obtain a faster measurement.

The opt-in flag is `--reuse-http` for both `bot/live.py` and `bot/practice.py`.
Practice records the selected transport in its action journal. The separate
reduction-only cleanup adapter continues using the default transport.
There are no automatic retries, including for GETs. A later explicit request
opens a fresh connection after an error. Redirects raise an HTTP error without
forwarding credentials or resubmitting a request to another URL.

## Verification (2026-10-24 06:25 UTC)

- The initial 405-test suite passed. After independent review, two regressions
  reproduced and fixed IPv6 proxy-host parity and connection cleanup on strategy
  startup failure. Seventeen local-server tests cover reuse, concurrent
  callers, server connection closure, HTTP error bodies, empty responses, proxy
  fallback, the unchanged default, and dropped acknowledgements/redirects that
  must not duplicate a POST.
- An integrated exchange check fetched the case and made three clock GETs using
  `LiveExchange(..., dry_run=True, reuse_http=True)`. All succeeded, with clock
  durations of 50.64, 54.21, and 126.39 ms. The
  [receipt and source hashes](evidence/http-reuse-integrated-smoke.json) preserve
  that check. An initial attempt used the wrong Python interpreter and failed
  on the `websockets` import before making a network request.
- `git diff --check` passed.

The measured durations vary even in this short window. This is an optional
transport candidate for a subsequent controlled trial, not evidence of higher
profit. No live trader was started or reconfigured for this experiment.

The integrated receipt records the source before the two review fixes. Those
fixes change proxy selection to use urllib's exact request-host representation
and extend connection cleanup over strategy initialization. They do not add any
request retries. All 407 Python tests passed after those fixes, and all 409
passed after integrating the independently reviewed loss-attribution diagnostic.
