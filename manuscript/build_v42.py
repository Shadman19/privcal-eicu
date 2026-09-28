"""Build Sci Rep v41: approved JSONs (hash-checked) plus the two v40 candidate JSONs (pinned hashes)."""
import json, hashlib, re, sys, math
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

# ---- v40 candidate outputs (Wahab job 6849883); pinned hashes ----
CAND = {"v10_publication_extract.json": "5035ef7b40e97e2b8caae526a61a9fba9028dc80568d67c186ed55c6d9e974ac",
        "cohort_characteristics_v40.json": "cd8052d739e3bce32fc95952b2c97bb492ecb48e0756825b96bc481570494289"}
def cand(name):
    raw = (Path("candidates") / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CAND[name], f"hash mismatch: {name}"
    return json.loads(raw)
X, CO = cand("v10_publication_extract.json"), cand("cohort_characteristics_v40.json")
assert CO["reconciled_with_approved_v9_results"] and CO["primary_hospital_set_verified"] and CO["linear_reconstruction_screen_passed"]
g = CO["groups"]; GA, GS, GT = g["all_stays"], g["source_hospitals"], g["target_hospitals"]
assert GA["stays"] == stays and GA["hospitals"] == H and GT["hospitals"] == ntgt and GA["vital_status"]["died_in_hospital"] == deaths
sc7 = [c for c in X["split_contrasts"] if c["split_seed"] == 7 and c["group"] == "0-5 calibration deaths"][0]
assert (sc7["n_hospitals"], sc7["mean_local_minus_pooled_Brier"], sc7["paired_hospital_bootstrap_95_CI"], sc7["bootstrap_seed"]) == \
       (P["n_hospitals"], P["mean_comparator_minus_method_Brier"], P["paired_hospital_bootstrap_95_CI"], P["bootstrap_seed"])
assert all(c["released"] for c in X["split_contrasts"])
low = [c for c in X["split_contrasts"] if c["group"] == "0-5 calibration deaths"]
alls = [c for c in X["split_contrasts"] if c["group"] == "all target hospitals"]
W = "withheld_small_cell"
def pct(n, d): return f"{n:,} ({100*n/d:.1f})"
def cell(grp, comp, k):
    v = grp[comp][k]; return "--" if v == W else pct(v, grp["stays"])
def q3(x): return f"{x[0]} [{x[1]}, {x[2]}]"
rowsC = [("Stays", *(f"{G['stays']:,}" for G in (GA, GS, GT))),
         ("Hospitals", *(str(G["hospitals"]) for G in (GA, GS, GT))),
         ("Died in hospital, n (\\%)", *(cell(G, "vital_status", "died_in_hospital") for G in (GA, GS, GT))),
         ("Female, n (\\%)", *(cell(G, "sex", "female") for G in (GA, GS, GT))),
         ("Age, years, median [Q1, Q3]", *(q3(G["age_years_median_q1_q3"]) for G in (GA, GS, GT))),
         ("Age recorded below 90, n (\\%)", *(cell(G, "age_recorded", "under_90") for G in (GA, GS, GT))),
         ("Age 90 or more (top-coded), n (\\%)", *(cell(G, "age_recorded", "top_coded_90_plus") for G in (GA, GS, GT))),
         ("Age missing, n (\\%)", *(cell(G, "age_recorded", "missing") for G in (GA, GS, GT)))]
for k in sorted(GA["unittype"], key=lambda k: -GA["unittype"][k] if GA["unittype"][k] != W else 0):
    rowsC.append((f"Unit: {k.replace('icu','ICU').replace('csICU','CSICU').replace('ccu-ctICU','CCU-CTICU').replace('ctICU','CTICU').replace('mICU','MICU').replace('sICU','SICU')}", *(cell(G, "unittype", k) for G in (GA, GS, GT))))
for k in sorted(GA["unitstaytype"], key=lambda k: -GA["unitstaytype"][k] if GA["unitstaytype"][k] != W else 0):
    rowsC.append((f"Unit stay: {k}", *(cell(G, "unitstaytype", k) for G in (GA, GS, GT))))
rowsC.append(("24-h text, words, median [Q1, Q3]", *(q3(G["predictor_text_words_median_q1_q3"]) for G in (GA, GS, GT))))
def ci3(c):
    m = c["mean_local_minus_pooled_Brier"]; lo, hi = c["paired_hospital_bootstrap_95_CI"]
    return f"{F.k3(m)} [{F.k3(lo)}, {F.k3(hi)}]"
splitrows = []
for s in (7, 11, 17, 23, 31):
    l = [c for c in low if c["split_seed"] == s][0]; a_ = [c for c in alls if c["split_seed"] == s][0]
    splitrows.append(f"{s}{'$^*$' if s == 7 else ''} & {l['n_hospitals']} & {ci3(l)} & {a_['n_hospitals']} & {ci3(a_)} \\\\")
gap = 0.0
for s in (7, 11, 17, 23, 31):
    d = {r["method"]: r for r in X["all_target_macro_metrics"] if r["split_seed"] == s}
    b = d["PrivCal-B (secure-agg isotonic)"]["macro_Brier"]
    gap = max(gap, abs(b - d["Global-BinnedIsotonic (source-only)"]["macro_Brier"]), abs(b - d["Global-Platt (source-only)"]["macro_Brier"]))
lm = [c["mean_local_minus_pooled_Brier"] for c in low]; am = [c["mean_local_minus_pooled_Brier"] for c in alls]
assert all(c["paired_hospital_bootstrap_95_CI"][0] > 0 for c in low)
V.update({
 "age_src": str(GS["age_years_median_q1_q3"][0]), "age_tgt": str(GT["age_years_median_q1_q3"][0]),
 "fem_src": f"{GS['female_percent']:.1f}", "fem_tgt": f"{GT['female_percent']:.1f}",
 "mort_src": f"{GS['hospital_mortality_percent']:.1f}", "mort_tgt": f"{GT['hospital_mortality_percent']:.1f}",
 "words_src": str(GS["predictor_text_words_median_q1_q3"][0]), "words_tgt": str(GT["predictor_text_words_median_q1_q3"][0]),
 "spl_nmin": str(min(c["n_hospitals"] for c in low)), "spl_nmax": str(max(c["n_hospitals"] for c in low)),
 "spl_min": F.k3(min(lm)), "spl_max": F.k3(max(lm)), "spl_all_min": F.k3(min(am)), "spl_all_max": F.k3(max(am)),
 "spl_macro_gap": f"{math.ceil(gap*1e5)/100:.2f}",  # upper bound, rounded up from unrounded JSON values
 "CohortRows": "\n".join(" & ".join(r) + " \\\\" for r in rowsC),
 "CohortNote": "Percentages use the column's stays. --: withheld, not zero or missing. A category with 1--19 stays in any column is withheld in every column, together with one complementary category; here, the two age categories other than below 90 years. Female excludes unknown. 24-h text: words of diagnosis and treatment text used by the model.",
 "SplitRows": "\n".join(splitrows),
})

aucs = {}
for s_ in (7, 11, 17, 23, 31):
    d = {r["method"]: r for r in X["all_target_macro_metrics"] if r["split_seed"] == s_}
    for m in ("PrivCal-B (secure-agg isotonic)", "Global-BinnedIsotonic (source-only)"):
        aucs.setdefault(m, []).append(d[m]["macro_AUROC"])
    assert d["PrivCal-B (secure-agg isotonic)"]["n_valid_AUROC"] == "92 minus 1-9"
V.update({"auc_pool_min": f"{min(aucs['PrivCal-B (secure-agg isotonic)']):.3f}", "auc_pool_max": f"{max(aucs['PrivCal-B (secure-agg isotonic)']):.3f}",
          "auc_src_min": f"{min(aucs['Global-BinnedIsotonic (source-only)']):.3f}", "auc_src_max": f"{max(aucs['Global-BinnedIsotonic (source-only)']):.3f}",
          "auc_nlo": "83", "auc_nhi": "91"})
_old = "patients at the 24-h landmark before text and hospital-size filters"
V["EicuTableRows_fix"] = _old

# ---- separate-process CKKS prototype (synthetic; pinned hash) ----
_PR = Path("proto/ckks_prototype_results.json").read_bytes()
assert hashlib.sha256(_PR).hexdigest() == "3823b9a9e725180c40fdc458d65f80136a4b90a18cd0882c79aa3b9f2d84ea70", "prototype results hash mismatch"
PRJ = json.loads(_PR); runs = PRJ["runs"]
assert all((not r["aggregator_can_decrypt"]) and r["rounded_counts_deaths_exact"] and r["temperature_choice_equal"] for r in runs)
import statistics as _st
def _sci(x):
    m, e = f"{x:.1e}".split("e"); return f"${m}\\times10^{{{int(e)}}}$"
agg = lambda h: _st.median(r["aggregate_s"] for r in runs if r["H"] == h)
st_ctx = _st.median(r["public_context_bytes"] for r in runs)
V.update({"pr_runs": str(len(runs)), "pr_hmin": str(min(r["H"] for r in runs)), "pr_hmax": str(max(r["H"] for r in runs)),
          "pr_mapdiff": _sci(max(r["pooled_map_max_abs_diff"] for r in runs)),
          "pr_enc": f"{_st.median(r['encrypt_s_per_hospital_median'] for r in runs):.3f}",
          "pr_mb": f"{_st.median(r['bytes_per_hospital'] for r in runs)/1e6:.2f}",
          "pr_agg10": f"{agg(10):.2f}", "pr_agg50": f"{agg(50):.2f}", "pr_agg139": f"{agg(139):.2f}", "pr_agg250": f"{agg(250):.2f}",
          "pr_ctxmb": f"{st_ctx/1e6:.2f}",
          "pr_dec": f"{_st.median(r['decrypt_s'] for r in runs):.2f}",
          "pr_packn": str(PRJ["packed_variant"]["values"]), "pr_packmb": f"{PRJ['packed_variant']['bytes_median']/1e6:.2f}",
          "pr_cpus": str(PRJ["environment"]["cpus"]), "pr_py": PRJ["environment"]["python"], "pr_ts": PRJ["environment"]["tenseal"]})
V["EicuTableRows"] = "\n".join(f"{m} & {r} & {i} \\\\" for m, r, i in rows)
assert V["EicuTableRows"].count(_old) == 1
V["EicuTableRows"] = V["EicuTableRows"].replace(_old, "selected unit stays with a unit-discharge offset of at least 24 h, before text and hospital-size filters")
del V["EicuTableRows_fix"]
src = Path("PrivCal_SciRep_v42.template.tex").read_text()
missing = set(re.findall(r"@@(\w+)@@", src)) - set(V)
assert not missing, missing
out = re.sub(r"@@(\w+)@@", lambda m: V[m.group(1)], src)
Path("PrivCal_SciRep_v42.tex").write_text(out)
print("built; primary direction:", pdir)
