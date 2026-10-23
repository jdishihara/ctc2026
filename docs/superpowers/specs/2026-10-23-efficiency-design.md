# Cornell bot efficiency and execution correctness

Arjun requested improvements to Jayden's existing CTC 2026 algorithm using the
official case packet. The primary objective is stronger, dependable competition
execution with measured computational improvements. No universal best strategy
or profit guarantee can be established from these research seasons.

## Evidence and constraints

- Starting revision: `f4eb4dd`, repository `jdishihara/ctc2026`.
- The downloaded PDF contains only the overview. Cornell's full packet is at
  https://docs.google.com/document/d/1XnZGvu3qPCc0abJYtkax9IyHVbx-LvUH6s1k8Y9j3Ps/edit.
- Only Systematic Equities permits bots. Its three rounds settle ten stocks and
  two ETFs; scoring is total realized plus final marked PnL.
- Position limits count same-side resting orders. Order actions are capped at
  180 per minute per team; retain the bot's 120-action budget.
- Fit only on seasons 1–450, tune on 451–525, verify on 526–600. Preserve data
  and fitted model parameters; use the existing deep and thin liquidity models.
- Keep the existing Python/NumPy model, strategy defaults, and API interface.

## Proposed work

1. Profile complete valuation calls and representative replay seasons. Reduce
   repeated array work and Python loops while preserving forecasts and trading
   decisions within floating-point tolerance. Add a reproducible benchmark and
   differential validation against the starting implementation.
2. Correct live execution state transitions: rejected/uncertain cancellations
   cannot free order capacity; failed account refreshes cannot authorize further
   orders; replacement orders require successful cancellation; paused symbols
   must cancel existing quotes. Use tests with a local exchange stub.
3. Run regression tests, compare the final replay against the baseline in both
   liquidity regimes, and report runtime, PnL, tail loss and fill counts. Keep
   performance-preserving changes distinct from fixes that change behavior.

Implementation choices above are engineering decisions under Arjun's request.
Deliver a reviewable branch and PR with reproduction commands. Live exchange
deployment and competition orders are outside this implementation session.
