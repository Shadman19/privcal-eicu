# PrivCal simulation addendum A (POST HOC; fixed before running it)

Written 27 September 2026 after the primary v25 simulation results were seen. It is
reported as post hoc. Motivation: in the primary simulation, a source-only binned isotonic
map performed almost as well as the pooled map, because source and target hospitals were
exchangeable. This addendum asks whether pooling adds value over the source-only map when
target hospitals differ systematically from source hospitals.

Design: identical to SIMULATION_PROTOCOL_v25.md except sigma = 0.35 and every target
hospital (determined in advance from the frozen seed-7 shuffle of the 60 synthetic site
names; the harness asserts the returned source set matches) receives an added intercept
shift delta. Scenarios: delta in {-0.7, +0.7}; R = 40 replicates each; world seed =
5000 + 1000 * scenario_index + replicate. Same estimands and summaries as v25. The key
contrast is MSE(source-only binned isotonic, true risk) - MSE(pooled, true risk) in the
0-5-death stratum, alongside the primary local-minus-pooled contrast. Both scenarios are
reported whatever their direction.
