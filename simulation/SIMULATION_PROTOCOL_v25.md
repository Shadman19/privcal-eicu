# PrivCal v25 supplementary simulation protocol (fixed before any simulation run)

Written 27 September 2026, before the harness was executed. SHA-256 of this file is recorded
in `protocol_sha256.txt` before the first replicate. Any later deviation is reported as such.

## Purpose
Test, with known true risks, when the frozen v9 pooled binned-isotonic map helps or harms
low-event target hospitals relative to the frozen v9 regularized local intercept. This is a
synthetic study. It uses no eICU data, does not replace the locked-v9 eICU estimand, and is
reported separately from it.

## Code under test (unchanged)
The frozen v9 notebook (SHA-256 23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75)
is hash-checked and its sections 3-4 (TenSEAL CKKS, helpers) and 6-7 (experiment functions)
are executed unmodified, except for the pinned v23 in-memory return instrumentation
(`instrument_return`, plus the leave-one-target-hospital-out maps) so predictions can be
compared with true risks. The TF-IDF logistic model, 50/25/25 within-hospital split,
0.34 source fraction, split seed 7, 12-bin pooled isotonic map, local intercept (penalty 2),
and real CKKS aggregation are those of v9.

## Synthetic world (per replicate)
- H = 60 hospitals; sizes n_h = round(exp(N(log 450, 0.8))) clipped to [130, 3000].
- Hospital intercept a_h = logit(0.09) + sigma * N(0, 1).
- Patient severity x ~ N(0, 1); true risk p = sigmoid(a_h + 1.5 x); outcome y ~ Bernoulli(p).
- Text: 300 synthetic diagnosis/treatment tokens with loadings w_k ~ N(0, 1). Token k is present
  with probability sigmoid(-3 + 0.8 w_k x + d_hk), where d_hk ~ N(0, 0.3) is a hospital
  documentation shift (cross-site drift). Two fixed tokens are always present.
- Scenarios: sigma in {0, 0.35, 0.7, 1.0} (between-hospital prevalence heterogeneity).
- R = 40 replicates per scenario; world seed = 1000 * scenario_index + replicate.

## Estimands (per replicate, target hospitals with 0-5 calibration deaths, all local labels)
- Primary (simulation): hospital-macro mean of
  dRisk = MSE(local intercept, true risk) - MSE(pooled isotonic, true risk) on test rows.
  Positive favors pooling. This measures absolute-risk accuracy directly.
- Secondary: hospital-macro dBrier = Brier(local) - Brier(pooled) (the v9 eICU estimand form);
  the same contrasts for leave-one-target-hospital-out pooled vs local and for source-only
  binned isotonic vs pooled; share of stratum hospitals with dRisk < 0 (harmed by pooling).
- Arithmetic: CKKS vs plaintext max absolute errors (pooled loss curve, rounded counts,
  score sums, held-out map predictions), using the pinned v23 fidelity functions.

## Summaries
Per scenario: mean across replicates of each hospital-macro contrast, 2.5th and 97.5th
percentiles across replicates, share of replicates with a positive contrast, mean stratum size.
Replicates with no stratum hospitals are counted and excluded from contrast means.
All scenarios are reported, whatever their direction. No scenario is added or dropped after
results are seen.
