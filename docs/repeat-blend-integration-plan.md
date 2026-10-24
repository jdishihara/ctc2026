# Optional fixed-blend integration plan

Declared 2026-10-24 09:43 UTC after the complete offline comparison and before
integration implementation. The source experiment remains frozen at
`7a2fe81b1167bb1b355357b0d105ea91ed29cd05`. Its independent capture review is pending.

## Scope

1. Copy the exact tested `ctc/analog.py` and its model tests from the frozen
   experiment. Keep recognition disabled by default.
2. Add one explicit `--repeat-prefix-blend` switch to the guarded practice
   runner and direct launcher. It enables only `repeat_prefix=True` and
   `repeat_weight=0.5`; it exposes no coefficient search or one-hot CLI mode.
3. Validate the switch before credential reads or account I/O. Reject combining
   it with the direct launcher's nowcast mode. Preserve existing behavior when
   the switch is absent, including callers with older argument namespaces.
4. Record the selected model mode in startup diagnostics. Preserve position
   limits, rate limits, history/ownership gates, loss trigger and cleanup.
5. Add failing integration tests first: both CLI paths, constructed ensemble
   selection, absent/default behavior, invalid programmatic values, and
   nowcast conflict before I/O. Run the complete suite and independent review.
6. Retain the complete 96-pair comparison, 75 development pairs, original
   failed invocation, source/input hashes, journals and independent audits.
   Explain all four individual regressions and the training-weather overlap.

## Acceptance and operation

No integration merge until the frozen experiment's independent result audit
passes and the exact integration head is reviewed. Merging an optional switch
does not activate it or establish live profitability. Account ownership remains
unresolved; no account orders will be submitted by this integration work.

The original and corrected forward evaluators remain frozen. Any later
evaluation of the blend needs its own declared specification and sealed closed
inputs; no active future outcome or current-season history may be read.
