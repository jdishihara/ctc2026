# Confirm season identity before loading history

## Reproduction and scope

The direct launcher (`python -m bot.live`) initialized the strategy before its
first account refresh. A newly constructed exchange had no competition ID, so
the strategy retained `None`. After feed replay or streamed news populated the
model, the first quote callback saw the confirmed account ID as a season change
and reset the model. The session still remembered the consumed news sequences,
so those messages would not normally be processed again.

This was independently reproduced with complete synthetic weather history:
reported rounds `[1, 2, 3]` became `[]` after the first complete quote batch.
The new serialized-client diagnostic also rejected all 48 scenarios on closed
captures 241–243 for incomplete history; it did not produce valid P&L results.
Those diagnostic results are not evidence of a strategy return.

The supervised `PracticeSession` already refreshes before initializing its
strategy. This issue does not explain the earlier supervised practice loss or
change attribution of the one clean completed live trial.

## Change

The direct launcher now refreshes the account first and requires both a complete
account snapshot (`state_ready`) and a nonempty string competition ID before
constructing or initializing the strategy. An unavailable snapshot or unusable
ID raises `RuntimeError` before replay, session construction, or subscription.
The outer launcher closes its HTTP connection on this failure. Retry by
restarting after the account endpoint is available.

This also prevents the failed-first-refresh followed by first-valid-ID handoff:
no partially initialized session is created. Normal subsequent season changes
continue through the existing session logic. Strategy parameters, forecast
logic, sizing, and submission guards are unchanged.

## Verification

Nine new regression cases failed before the fix. They cover analog and nowcast
strategies, recorded-history and streamed-history startup, and unavailable,
missing, blank, whitespace-only, and nonstring initial IDs. The history tests
invoke real session and strategy quote processing and assert that all three
reports, history readiness, and matching strategy/account identity survive.
External networking is denied and order submissions use dry-run mode.

The HTTP integration fixture supplies valid account responses. Its cleanup
test checks both initial-account failure and strategy-construction failure,
including connection closure and GET-only startup traffic.

The integrated branch based on teammate main `46fbc3f` passes **507 Python
tests**. Independent review passed 39 focused tests and five additional
failure-path checks with networking denied, with no blocking findings.

This is a startup correctness fix. A new execution replay and further
attributable live trials are still required to assess profitability.
