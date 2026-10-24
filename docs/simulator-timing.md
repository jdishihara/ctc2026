# Historical simulator clock

`ctc.sim.Sim` now activates pending orders at their scheduled deadline, rather
than waiting for the next recorded event. A deadline strictly before a round
close executes before that close; an order due at or after the close expires.
Pending orders after the final recorded quote receive the same treatment.
Events at or beyond 2,340 seconds cannot open a fourth trading round.

When an activation and a price update have the same timestamp, the new price
arrives first. Previously resting orders match before the new activation and
consume shared ladder depth. Between updates, activations use the last recorded
price, with ladder replenishment evaluated at the actual activation time.
This remains a synthetic execution model, without real queue competition.

Regression tests cover exact deadlines, price ties, intermediate and final
closes, gaps between rounds, and terminal price frames. Independent review also
checked ladder replenishment and shared-depth priority. The full suite passed
335 committed tests on 2026-10-24 before this change was committed.

Earlier historical reports retain their original source versions. They should
not be silently relabeled as results from the corrected clock. The completed
season-241 nine-scenario cost comparison was rerun, with unchanged aggregate
profits; the old clock defect does not explain that season's historical versus
live profit gap. Equal totals at different sub-quote-interval latencies can be
valid even when execution timestamps differ.

The captured-market adapter has its own `ReplayExchange.advance` event loop.
It does not call `Sim.run`; this patch does not replace its execution model or
change the preselected captured-market scenario grid.
