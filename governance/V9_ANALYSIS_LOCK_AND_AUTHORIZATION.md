# PrivCal eICU v9 analysis lock and authorization

Complete this file **before** starting the claim-forming v9 job. The template
is intentionally `PENDING`; code generation is not human authorization. A
responsible study-team member must review the frozen estimand, source hash,
data-use conditions, and analysis role, then change only the approval fields.
Preserve the completed file unchanged. The verifier hashes the exact bytes.

```json
{
  "schema_version": "privcal_eicu_v9_lock_v1",
  "study_id": "one_pooled_calibration_eicu",
  "analysis_role": "claim_forming",
  "status": "PENDING",
  "approval_utc": null,
  "approved_by": [],
  "authorizations": {
    "analysis_plan_reviewed": false,
    "data_use_and_aggregate_release_reviewed": false,
    "authorship_and_oversight_owner_identified": false
  },
  "frozen_source": {
    "notebook": "PrivCal_eICU_reviewer_sensitivities_v9.ipynb",
    "sha256": "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
  },
  "primary_estimand": {
    "split_seed": 7,
    "backend": "tfidf_lr",
    "target_subset": "0-5 calibration deaths, inclusive",
    "unit": "target hospital",
    "aggregation": "hospital macro mean",
    "outcome_metric": "Brier score",
    "method": "self-including pooled 12-bin binned-isotonic map",
    "comparator": "fixed-penalty regularized local intercept",
    "contrast": "comparator Brier minus method Brier",
    "positive_contrast_favors": "pooled method",
    "bootstrap_resamples": 2000,
    "bootstrap_seed": 971,
    "confidence_interval": "paired hospital bootstrap percentile 95%"
  },
  "required_directional_controls": [
    "self_including_pooled_binned_isotonic_vs_source_platt_local_intercept",
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_regularized_local_intercept",
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_source_platt_local_intercept",
    "self_including_pooled_binned_isotonic_vs_source_only_binned_isotonic",
    "pooled_binned_isotonic_vs_pooled_temperature"
  ],
  "diagnostic_only_control": "leave_one_target_hospital_out_pooled_binned_isotonic_vs_self_including_pooled_binned_isotonic",
  "local_intercept_penalties": [0.5, 1.0, 2.0, 4.0, 8.0],
  "claim_rules": {
    "primary_ci_entirely_positive": "narrow lower-Brier claim may proceed only if all directional and penalty gates also pass",
    "primary_ci_crosses_zero": "report inconclusive paired result without superiority language",
    "primary_ci_entirely_negative": "report that the named local comparator had lower Brier",
    "brier_scope": "overall probability accuracy; not calibration quality or clinical benefit by itself"
  },
  "post_run_requirements": {
    "aggregate_audit_required": true,
    "held_out_calibration_diagnostics_required": true,
    "ckks_plaintext_map_fidelity_required": true,
    "cohort_selection_promotion_audit_required_before_submission": true,
    "five_splits_are_correlated_not_independent_replications": true
  }
}
```

Approval must precede `run_started_utc`. Do not backdate approval. If any
non-approval field changes, create a new lock version, obtain fresh approval,
and start a new run. Never upload this internal authorization file with the
blinded manuscript.
