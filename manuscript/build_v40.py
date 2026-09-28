"""Build the Scientific Reports manuscript: every eICU number comes from the approved JSONs (hash-checked)."""
import json, hashlib, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "v31"))
import fill_results_v31 as F

R = Path("approved")
J = F.load(R, R / "APPROVED_SHA256SUMS.txt")          # hash-checked against the approved manifest
rows, macros, pdir = F.build(J)                          # runs every consistency gate
a, st, pr, dg, sc = J["audit"], J["sites"], J["promo"], J["diag"], J["strat"]
P, md, ut = a["primary"], a["run_metadata"], dg["unit_types"]
C = {F.CONTROL[c["comparison"]]: c for c in a["low_event_seed7_sensitivity"]}
pen = sorted(a["local_intercept_penalty_sensitivity"], key=lambda c: c["local_intercept_penalty"])
tm = dg["target_seed7_methods"]
def e(c): return F.eff(c["mean_comparator_minus_method_Brier"], c["paired_hospital_bootstrap_95_CI"])
def reg(m): r = tm[m]["patient_pooled_calibration_regression"]; return r["intercept"], r["slope"]
def f2(x): return f"{x:.2f}".replace("-", "$-$")
H, stays, deaths = md["sites"], md["rows"], ut["selected_hospital_deaths"]
ntgt = tm["PrivCal-B (secure-agg isotonic)"]["n_target_hospitals"]
V = {
 "stays": f"{stays:,}", "H": str(H), "nsrc": str(H - ntgt), "ntgt": str(ntgt), "deaths": f"{deaths:,}",
 "mort": f"{100*deaths/stays:.1f}", "landmark": f"{pr['patients_at_landmark_stage']:,}",
 "promoted": str(pr["promoted_patients_at_landmark_stage"]),
 "nlow": str(P["n_hospitals"]), "prim": e(P), "prim_mean": F.k3(P["mean_comparator_minus_method_Brier"]),
 "prim_lo": F.k3(P["paired_hospital_bootstrap_95_CI"][0]), "prim_hi": F.k3(P["paired_hospital_bootstrap_95_CI"][1]),
 "prim_median": F.k3(P["median_comparator_minus_method_Brier"]),
 "iqr_lo": F.k3(P["IQR_comparator_minus_method_Brier"][0]), "iqr_hi": F.k3(P["IQR_comparator_minus_method_Brier"][1]),
 "bpool": f"{P['mean_method_Brier']:.3f}", "bloc": f"{P['mean_comparator_Brier']:.3f}",
 "plower": str(st["pooled_lower_Brier_hospitals"]), "llower": str(st["local_intercept_lower_Brier_hospitals"]),
 "tied": str(st["exactly_tied_hospitals"]), "delflip": str(st["single_hospital_deletion"]["deletions_changing_sign_of_mean"]),
 "loto": e(C["loto"]), "srcbin": e(C["srcbin"]), "srcplatt": e(C["srcplatt"]), "lotoplatt": e(C["lotoplatt"]),
 "pooltemp": e(C["pooltemp"]), "selfinc": e(C["selfinc"]),
 "pen_lo": F.k3(pen[0]["mean_comparator_minus_method_Brier"]), "pen_hi": F.k3(pen[-1]["mean_comparator_minus_method_Brier"]),
 "pen05": e(pen[0]),
 "citl_pool": f2(sc["pooled_binned_isotonic"]["patient_pooled_calibration_in_the_large_intercept"]),
 "citl_loc": f2(sc["local_intercept_penalty2"]["patient_pooled_calibration_in_the_large_intercept"]),
 "citl_src": f2(sc["source_only_binned_isotonic"]["patient_pooled_calibration_in_the_large_intercept"]),
 "strat_stays": f"{sc['pooled_test_counts']['stays']:,}", "strat_deaths": str(sc["pooled_test_counts"]["deaths"]),
 "strat_obs": f"{100*sc['pooled_test_counts']['deaths']/sc['pooled_test_counts']['stays']:.1f}",
 "strat_pred_pool": f"{100*sc['pooled_binned_isotonic']['patient_pooled_mean_predicted']:.1f}",
 "strat_pred_loc": f"{100*sc['local_intercept_penalty2']['patient_pooled_mean_predicted']:.1f}",
 "strat_pred_src": f"{100*sc['source_only_binned_isotonic']['patient_pooled_mean_predicted']:.1f}",
 "cal_pool_i": f2(reg("PrivCal-B (secure-agg isotonic)")[0]), "cal_pool_s": f2(reg("PrivCal-B (secure-agg isotonic)")[1]),
 "cal_platt_i": f2(reg("Global-Platt (source-only)")[0]), "cal_platt_s": f2(reg("Global-Platt (source-only)")[1]),
 "cal_loc_i": f2(reg("Local-intercept (source-T)")[0]), "cal_loc_s": f2(reg("Local-intercept (source-T)")[1]),
 "tstays": f"{tm['PrivCal-B (secure-agg isotonic)']['n_test_stays']:,}", "tdeaths": f"{tm['PrivCal-B (secure-agg isotonic)']['n_test_deaths']:,}",
 "ckks_map": F.sci(dg["encrypted_plaintext_map_fidelity"]["held_out_map_prediction_max_abs_error"]),
 "ckks_n": f"{dg['encrypted_plaintext_map_fidelity']['n_held_out_target_predictions_compared']:,}",
 "ckks_loss": F.sci(a["ckks_arithmetic"]["max_abs_pooled_loss_error"]), "ckks_runs": str(a["ckks_arithmetic"]["runs"]),
 "d24": str(ut["discharge_offset_audit"]["hospital_discharge_before_24_hour_landmark"]),
 "dunit": str(ut["discharge_offset_audit"]["hospital_discharge_before_unit_discharge"]),
}
V["EicuTableRows"] = "\n".join(f"{m} & {r} & {i} \\\\" for m, r, i in rows)
src = Path("PrivCal_SciRep_v40.template.tex").read_text()
missing = set(re.findall(r"@@(\w+)@@", src)) - set(V)
assert not missing, missing
out = re.sub(r"@@(\w+)@@", lambda m: V[m.group(1)], src)
Path("PrivCal_SciRep_v40.tex").write_text(out)
print("built; primary direction:", pdir)
