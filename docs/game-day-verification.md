# Game-day tool verification — October 24, 2026

This check covers local functionality of all three case tools. It does not
measure competitive returns or resume trading on the shared team account.

## Systematic equities

The reviewed competition checkout at merged PR 29 (`f8fda59`) passes all 713
Python tests. Its trading runtime remains the reviewed bounded cleanup version
from PR 28. The [readiness report](competition-readiness.md) distinguishes the
historical results, closed recorded replays and attributable live practice.

## Derivatives

The first browser attempt skipped all three tests because Chromium was missing.
After installing the browser, the next run had one pass and two failures:

- The manual workflow test assumed auto-confirm was off. The current documented
  default is on. The corrected test explicitly selects manual confirmation and
  separately verifies that automatic order submission remains off.
- The round-three test exposed an actual unit error: a message naming variance
  could be interpreted as IV because its raw number was closer to the old market
  price. A variance of 0.49 was displayed as 49% IV instead of 70%.

The initial narrow fix passes all three browser scenarios, but independent
review found related paths that required correction. Later unitless messages
lost earlier unit evidence; tied named conversions could choose an unrelated
unit; and an automatic choice survived later contradictory labels. Revoking a
choice also had to revoke its previously approved analyst-derived targets.

The corrected runtime accumulates unit evidence for each event, leaves unresolved
named choices for manual selection, and reconsiders inferred units when new
explicit evidence conflicts. It immediately clears affected analyst approvals.
This invalidation preserves manual converter choices and literal typed values.
A re-run explicitly reopens converter identification.

Both initial regressions failed before their fixes. Four additional review
regressions failed on the intermediate source. The first invalidation attempt
left a cached approval true; that failure is retained, and immediate
recomputation fixes it. The final unit suite has 152 passing tests, including
manual-choice, typed-target and re-run behavior. Typecheck passes. Production
and development builds succeed. The final browser run passes all three scenarios
with zero skips in 154.60 seconds, using source `4cc4324`. Eleven timezone tests
pass in each of UTC and New York.

Independent frozen-source review approves `4cc4324`: 26 focused tests and eleven
retained safety/ownership assertions pass, including all four initially reported
failures. No network attempts occur in those probes. The original 45-file failure
evidence is preserved alongside the 35-file final review archive. The review's
whole-worktree check saw documentation edits; runtime/test Git bytes remain
unchanged and verified. No additional performance replay was performed for that
packaging check.

Browser tests use an isolated Chromium profile and the local mock exchange on
port 5317. Their simulated submissions do not touch the competition account.
The production build targets the Cornell exchange; the development build's
localhost permissions are separate. Follow
[the derivatives game-day instructions](../derivatives-overlay/GAMEDAY.md).

The three-file production package is
[`derivatives-overlay.zip`](evidence/game-day-verification/derivatives-overlay.zip),
SHA-256 `165f1cca044367f1576d58c3cfc4b23626706b3b7bd92d31dbb03b358a31d51c`.
Unzip it and load that folder as an unpacked extension. No extension was loaded
or armed on the shared competition account during this verification.

## Mario Markets

A bounded local smoke test starts the mock exchange and desk, receives all eight
race results, and maps all 46 contracts with no unmapped symbols. Automatic
execution stays off, the mock records no trades, and both owned processes are
terminated afterward. The command-line help check also passes.

This checks startup, result ingestion and the default order setting. It does not
verify real-page prefill or establish profitable Mario pricing. Instructions:
[Mario desk README](../mario/README.md).

## Evidence

Original failures, skipped tests, corrected runs, source bindings, browser
results and local mock logs are retained in
[`evidence/game-day-verification/artifact-manifest.json`](evidence/game-day-verification/artifact-manifest.json).
No active season's published future outcomes were inspected for these checks.
