# Executable entry-price bounds

The previous aggressive-order code forced its limit to cross the displayed
touch, even if doing so exceeded the fair-value price allowed by its edge floor.
For example, with fair value 101 and a 98/102 market, it could buy at 102. The
mirror case could sell below its own fair value.

New risk must now preserve the configured edge at its limit price. A reversal
whose opening leg lacks that edge may flatten the old position, but may not
open the opposite position. Genuine position reductions retain their existing
execution handling. Risk is classified from reconciled positions after a
cancellation, so fills during cancellation cannot turn a reduction into an
unprotected addition.

Outstanding orders are checked before unchanged-target and uncertainty gates.
This includes partially filled orders and pending simulated activations. If a
side's total remaining quantity can cross through flat, every limit on that
side must meet its bound, since execution order is uncertain. A matching
tracked passive quote retains its documented fractional edge floor. Invalid
or unbounded entry limits are canceled. Cancellation must succeed, preserve
competition identity, and leave usable account state before replacement.

When a target needs a new order, existing orders on either side are canceled
and reconciled even if their signed quantities net to zero. This prevents a
new order from turning an older reduction into unprofitable new exposure.

Independent review reproduced the defects and checked the fixes. The full
isolated-branch suite passes 362 tests. Before/after comparisons on completed
recordings and fixed historical development scenarios are still required to
describe the performance effect. Execution correctness does not guarantee
that the model's fair value is accurate or that a season will be profitable.
