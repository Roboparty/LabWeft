# Synthetic research notes

This is a UI and state-management fixture, not scientific evidence.

## Questions
Q-history: What changes when history_length moves from 0 to 3?
Q-aux: With history enabled, what is the incremental effect of prediction_weight=0.1?
Q-hardware: Should a new hardware-only ablation be recommended again?

## Demonstration-only researcher decision
The synthetic researcher has already reviewed GPU-A and GPU-B under the same
implementation, dataset, precision, budget and evaluation protocol. For this
fixture only, they accept reuse of the hardware judgment for the explicitly
recorded scope. This note does NOT establish statistical equivalence and does
not apply to real hardware or any real research project.

Reopen if implementation, precision, data, effective budget, or evaluation
protocol changes, or new contradictory evidence appears. A new training seed
is replication, not a reason to repeat the hardware ablation.
