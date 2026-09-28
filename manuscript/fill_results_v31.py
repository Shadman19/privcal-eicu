#!/usr/bin/env python3
"""Fill manuscript Table I and the eICU results text from team-approved aggregate JSONs (v31).

Usage:
  python fill_results_v31.py --release <dir with approved JSONs> --out results_v31.tex
  python fill_results_v31.py --pending --out results_v31.tex      # no data: every cell PENDING

Reads only aggregate JSONs (no records). Every number printed in the manuscript's eICU
section comes from this script; nothing is typed by hand. The script refuses to run if the
JSONs disagree with each other (hospital counts, cohort size, notebook hash) or if the
primary audit is not marked verified. Wording of direction follows the paired 95% interval
only: excludes 0 above -> favors pooled; excludes 0 below -> favors local; else inconclusive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

V9_SHA = "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
FILES = {
    "audit": "aggregate_publication_audit_v9.json",
    "sites": "primary_site_summary_v24.json",
    "recon": "site_row_reconciliation_v21.json",
    "promo": "stay_promotion_audit_v24.json",
    "diag": "aggregate_calibration_diagnostics_seed7.json",
    "strat": "stratum_calibration_v27.json",
}
CONTROL = {
    "self_including_pooled_binned_isotonic_vs_source_only_binned_isotonic": "srcbin",
    "self_including_pooled_binned_isotonic_vs_source_platt_local_intercept": "srcplatt",
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_regularized_local_intercept": "loto",
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_self_including_pooled_binned_isotonic": "selfinc",
    "pooled_binned_isotonic_vs_pooled_temperature": "pooltemp",
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_source_platt_local_intercept": "lotoplatt",
}
DIRECTIONAL = ["srcplatt", "loto", "lotoplatt", "srcbin", "pooltemp"]  # the five locked directional controls



class GateError(RuntimeError):
    pass


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise GateError(msg)


def k3(x: float) -> str:
    """Brier-scale difference in units of 10^-3, one decimal, LaTeX minus."""
    s = f"{1000 * x:.1f}"
    if s == "-0.0":
        s = "0.0"
    return "$-$" + s[1:] if s.startswith("-") else s


def k3f(x: float) -> str:
    """Like k3 but two decimals, for contrasts far below 0.1e-3."""
    s = f"{1000 * x:.2f}"
    if s in ("-0.00", "0.00"):
        s = "0.00"
    return "$-$" + s[1:] if s.startswith("-") else s


def ksig(x: float) -> str:
    """Two decimals with an explicit sign, for intervals that cross zero."""
    v = f"{1000 * x:+.2f}"
    return ("$-$" + v[1:]) if v.startswith("-") else v


def eff(mean: float, ci) -> str:
    """Mean [interval] in 10^-3; two decimals with explicit signs when the interval crosses zero."""
    if ci[0] < 0 < ci[1]:
        return f"{ksig(mean)} [{ksig(ci[0])}, {ksig(ci[1])}]"
    return f"{k3(mean)} {ci3(ci)}"


def ci3(ci) -> str:
    return f"[{k3(ci[0])}, {k3(ci[1])}]"


def direction(ci) -> str:
    if ci[0] > 0:
        return "favors pooling"
    if ci[1] < 0:
        return "favors the comparator"
    return "inconclusive"


CONTROL_SEEDS = {  # from the pinned auditor audit_publication_results_v9.py (1e3126e2...)
    "self_including_pooled_binned_isotonic_vs_source_platt_local_intercept": 972,
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_regularized_local_intercept": 973,
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_source_platt_local_intercept": 974,
    "self_including_pooled_binned_isotonic_vs_source_only_binned_isotonic": 975,
    "pooled_binned_isotonic_vs_pooled_temperature": 976,
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_self_including_pooled_binned_isotonic": 977,
}


def locked_seed(comparison: str) -> int:
    if comparison in CONTROL_SEEDS:
        return CONTROL_SEEDS[comparison]
    return 980 + int(round(float(comparison.rsplit("_", 1)[1]) * 10))  # penalty grid rule in the auditor


def agree(c) -> None:
    """A directional label must agree with the sign of the reported mean difference."""
    d, m = direction(c["paired_hospital_bootstrap_95_CI"]), c["mean_comparator_minus_method_Brier"]
    need(not (d == "favors pooling" and m <= 0) and not (d == "favors the comparator" and m >= 0),
         f"interval and mean disagree in sign for {c.get('comparison')}")


def cnt(v) -> str:
    return f"{v:,}" if isinstance(v, int) else str(v).replace("<", r"\textless{}")


def load(release: Path, manifest: Path) -> dict:
    """Load the six JSONs only if their SHA-256 values match the team-approved manifest.

    The manifest is `sha256sum` output for exactly the six files, made when the team approved them.
    """
    approved = {}
    for line in manifest.read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            approved[Path(name.strip().lstrip("*")).name] = digest.lower()
    need(set(approved) == set(FILES.values()), "manifest must list exactly the six approved JSON files")
    out = {}
    for key, name in FILES.items():
        p = release / name
        need(p.is_file(), f"missing {name}")
        raw = p.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == approved[name], f"{name} differs from the approved bytes")
        out[key] = json.loads(raw)
    return out


def build(J: dict) -> tuple[list[tuple[str, str, str]], dict, str]:
    a, st, rc, pr, dg, sc = (J[k] for k in ("audit", "sites", "recon", "promo", "diag", "strat"))
    P = a["primary"]
    md = a["run_metadata"]
    # Consistency gates (fail closed).
    need(md["source_notebook_sha256"] == V9_SHA, "audit notebook hash mismatch")
    need(dg["frozen_notebook_sha256"] == V9_SHA, "diagnostic notebook hash mismatch")
    need(md.get("real_ckks") is True and dg.get("real_ckks") is True, "real CKKS not confirmed")
    need(P.get("site_scores_and_interval_verified") is True, "primary not verified by auditor")
    need(P["bootstrap_resamples"] == 2000 and P["bootstrap_seed"] == 971, "bootstrap settings changed")
    n = P["n_hospitals"]
    need(st["n_hospitals"] == n and rc["n_hospitals"] == n, "hospital count mismatch across JSONs")
    need(rc.get("passed") is True, "row reconciliation failed")
    need(st["pooled_lower_Brier_hospitals"] == P["method_lower_Brier_hospitals"], "pooled-lower count mismatch")
    need(st["pooled_lower_Brier_hospitals"] + st["local_intercept_lower_Brier_hospitals"]
         + st["exactly_tied_hospitals"] == n, "site counts do not sum")
    ut = dg["unit_types"]
    need(ut["denominator_selected_stays"] == md["rows"], "cohort size mismatch (audit vs diagnostic)")
    need(ut.get("outcome_code_audit_passed") is True, "outcome code audit failed")
    # The promotion audit counts patients BEFORE the text and hospital-size filters (its "stage" field),
    # so it may exceed the final cohort but never fall below it.
    need("before text and hospital-size filters" in pr.get("stage", ""), "promotion audit stage changed")
    need(isinstance(pr["patients_at_landmark_stage"], int) and pr["patients_at_landmark_stage"] >= md["rows"],
         "landmark-stage count is smaller than the audited cohort")
    need(sc.get("hospital_set_matches_frozen_v9_primary") is True, "stratum hospital set mismatch")
    need(sc["n_stratum_hospitals"] == n, "stratum size mismatch")
    fid = dg["encrypted_plaintext_map_fidelity"]
    tf = dg["independent_temperature_denominator_fidelity"]
    need(tf.get("requires_review") is False, "temperature-denominator fidelity flagged for review")
    H, stays, deaths = md["sites"], md["rows"], ut["selected_hospital_deaths"]
    tgt = dg["target_seed7_methods"]["PrivCal-B (secure-agg isotonic)"]
    ntgt = tgt["n_target_hospitals"]
    need(ntgt == H - max(2, int(0.34 * H)), "target-hospital count inconsistent with the partition rule")

    comps = [c["comparison"] for c in a["low_event_seed7_sensitivity"]]
    need(len(comps) == 6 and len(set(comps)) == 6 and set(comps) == set(CONTROL), "the six locked comparisons are not exactly present")
    C = {CONTROL[c["comparison"]]: c for c in a["low_event_seed7_sensitivity"]}
    for c in list(C.values()) + a["local_intercept_penalty_sensitivity"]:
        need(c["n_hospitals"] == n, "control hospital count mismatch")
        need(c["bootstrap_resamples"] == 2000 and c["bootstrap_seed"] == locked_seed(c["comparison"]),
             f"bootstrap settings differ from the pinned auditor for {c['comparison']}")
        agree(c)
    agree(P)
    pen = sorted(a["local_intercept_penalty_sensitivity"], key=lambda c: float(c["comparison"].rsplit("_", 1)[1]))
    pen_lam = [c["comparison"].rsplit("_", 1)[1] for c in pen]
    need(pen_lam == ["0.5", "1", "2", "4", "8"], "penalty grid changed")
    pen_dirs = [direction(c["paired_hospital_bootstrap_95_CI"]) for c in pen]

    def ctrl(key: str) -> str:
        c = C[key]
        ci = c["paired_hospital_bootstrap_95_CI"]
        return eff(c["mean_comparator_minus_method_Brier"], ci)

    cal = dg["target_seed7_methods"]
    def reg(m):
        r = cal[m]["patient_pooled_calibration_regression"]
        return f"{r['intercept']:.2f}/{r['slope']:.2f}".replace("-", "$-$")

    def citl(m):
        v = sc[m]["patient_pooled_calibration_in_the_large_intercept"]
        return "withheld" if isinstance(v, str) else f"{v:.2f}".replace("-", "$-$")

    counts = sc["pooled_test_counts"]
    strat_counts = ("small cells withheld" if isinstance(counts, str)
                    else f"{counts['stays']:,} test stays, {counts['deaths']:,} deaths")
    promo = pr["promoted_patients_at_landmark_stage"]
    delsign = st["single_hospital_deletion"]["deletions_changing_sign_of_mean"]

    rows = [
        ("Cohort: stays, hospitals, mortality",
         f"{stays:,}; {H}; {100 * deaths / stays:.1f}\\%",
         f"{H - ntgt} source, {ntgt} target hospitals (seed 7); {pr['patients_at_landmark_stage']:,} patients at the 24-h landmark before text and hospital-size filters; {cnt(promo)} stays promoted by missing fields"),
        (r"\textbf{Primary}: pooled vs local intercept, 0--5 deaths",
         f"\\textbf{{{eff(P['mean_comparator_minus_method_Brier'], P['paired_hospital_bootstrap_95_CI'])}}}",
         f"{n} hospitals; mean Brier {P['mean_method_Brier']:.3f} pooled vs {P['mean_comparator_Brier']:.3f} local; "
         f"median {k3(P['median_comparator_minus_method_Brier'])}, IQR {k3(P['IQR_comparator_minus_method_Brier'][0])} to {k3(P['IQR_comparator_minus_method_Brier'][1])}; {direction(P['paired_hospital_bootstrap_95_CI'])}"),
        ("Hospitals pooled lower / local lower / tied",
         f"{st['pooled_lower_Brier_hospitals']} / {st['local_intercept_lower_Brier_hospitals']} / {st['exactly_tied_hospitals']}",
         f"{delsign} of {st['single_hospital_deletion']['deletions_evaluated']} single-hospital deletions reverse the sign of the mean"),
        ("Control: pooled vs source-only binned map", ctrl("srcbin"),
         "Tests pooling itself, not map flexibility; " + direction(C["srcbin"]["paired_hospital_bootstrap_95_CI"])),
        ("Control: pooled vs source Platt + local intercept", ctrl("srcplatt"),
         direction(C["srcplatt"]["paired_hospital_bootstrap_95_CI"])),
        ("Control: leave-one-target-out pooled vs local", ctrl("loto"),
         "Excludes the evaluated hospital's own summary; " + direction(C["loto"]["paired_hospital_bootstrap_95_CI"])),
        ("Control: leave-one-target-out pooled vs source Platt + local", ctrl("lotoplatt"),
         direction(C["lotoplatt"]["paired_hospital_bootstrap_95_CI"])),
        ("Control: pooled isotonic vs pooled temperature", ctrl("pooltemp"),
         direction(C["pooltemp"]["paired_hospital_bootstrap_95_CI"])),
        ("Diagnostic: leave-one-out vs self-including pooled", ctrl("selfinc"),
         "Contribution of the hospital's own labels"),
        ("Local-intercept penalty 0.5, 1, 2, 4, 8",
         ", ".join(k3(c["mean_comparator_minus_method_Brier"]) for c in pen),
         f"Intervals excluding 0: {sum(d != 'inconclusive' for d in pen_dirs)} of 5"),
        ("Calibration intercept/slope, all target stays",
         f"{reg('PrivCal-B (secure-agg isotonic)')}",
         f"Pooled map; source Platt {reg('Global-Platt (source-only)')}; local intercept "
         f"{reg('Local-intercept (source-T)')}; ideal 0/1; {ntgt} hospitals"),
        ("Calibration-in-the-large, 0--5-death stratum",
         citl("pooled_binned_isotonic"),
         f"Pooled map; local intercept {citl('local_intercept_penalty2')}; source-only binned "
         f"{citl('source_only_binned_isotonic')}; ideal 0; {strat_counts}"),
        ("CKKS vs plaintext, held-out map predictions",
         sci(fid["held_out_map_prediction_max_abs_error"]),
         f"Max abs. error over {fid['n_held_out_target_predictions_compared']:,} predictions; rounded counts and deaths "
         f"{'exact' if fid['rounded_count_max_abs_error'] == 0 and fid['rounded_death_max_abs_error'] == 0 else 'NOT exact'}; "
         f"temperature choice {'matched' if a['ckks_arithmetic']['temperature_matches_plaintext'] else 'DIFFERED'} in all {a['ckks_arithmetic']['runs']} splits"),
    ]

    pdir = direction(P["paired_hospital_bootstrap_95_CI"])
    sdir = direction(C["srcbin"]["paired_hospital_bootstrap_95_CI"])
    ctrl_dirs = {k: direction(C[k]["paired_hospital_bootstrap_95_CI"]) for k in DIRECTIONAL}
    broad = pdir == "favors pooling" and all(d == "favors pooling" for d in ctrl_dirs.values()) \
        and all(d == "favors pooling" for d in pen_dirs)
    pm = P["mean_comparator_minus_method_Brier"]
    unit = "$\\times10^{-3}$"
    pci = P["paired_hospital_bootstrap_95_CI"]
    pmean_s, pci_s = eff(pm, pci).split(" [", 1)
    peff = f"$\\Delta$Brier {pmean_s}{unit}, 95\\% interval [{pci_s}{unit}"
    lead = {
        "favors pooling": "the pooled map had lower mean Brier score than the local intercept",
        "favors the comparator": "the local intercept had lower mean Brier score than the pooled map",
        "inconclusive": ("the mean Brier score was " + ("lower" if pm > 0 else "higher" if pm < 0 else "equal")
                         + " with the pooled map than with the local intercept, but the interval included zero"),
    }[pdir]
    sm = C["srcbin"]["mean_comparator_minus_method_Brier"]
    seff = f"{eff(sm, C['srcbin']['paired_hospital_bootstrap_95_CI'])}{unit}"
    src = {
        "favors pooling": f"The pooled map also had lower mean Brier score than the source-only binned map ({seff}).",
        "favors the comparator": f"The source-only binned map had lower mean Brier score than the pooled map ({seff}).",
        "inconclusive": f"Against the source-only binned map the interval included zero ({seff}).",
    }[sdir]
    unfav = [lab for k, lab in [("srcplatt", "source Platt plus local intercept"), ("loto", "leave-one-target-out versus local intercept"),
                                ("lotoplatt", "leave-one-target-out versus source Platt plus local intercept"),
                                ("srcbin", "source-only binned map"), ("pooltemp", "pooled temperature")]
             if ctrl_dirs[k] == "favors the comparator"]
    incon = sum(d == "inconclusive" for d in ctrl_dirs.values())
    ctrl_sum = (f"Of the five prespecified directional controls, {sum(d == 'favors pooling' for d in ctrl_dirs.values())} favored pooling, "
                f"{incon} {'was' if incon == 1 else 'were'} inconclusive, and {len(unfav)} favored the comparator"
                + (f" ({'; '.join(unfav)})" if unfav else "") + ". "
                + ("All controls and penalties support the pooled map." if broad else
                   "A claim beyond the named local-intercept comparison is therefore not made."))
    nd = delsign
    doa = ut["discharge_offset_audit"]
    need(doa["missing_hospital_or_unit_offset"] == 0, "missing discharge offsets in final cohort")
    text = (
        f"The audited cohort had {stays:,} selected stays from {H} hospitals ({100 * deaths / stays:.1f}\\% hospital mortality). "
        f"In seed 7, {n} of {ntgt} target hospitals had 0--5 calibration deaths. In these hospitals {lead} "
        f"({peff}; Table~\\ref{{tab:primary}}). "
        f"Pooling gave the lower Brier score in {st['pooled_lower_Brier_hospitals']} hospitals and the local intercept in "
        f"{st['local_intercept_lower_Brier_hospitals']}; {nd if nd else 'no'} single-hospital deletion{'' if nd == 1 else 's'} reversed the sign of the mean. "
        f"{src} {ctrl_sum} "
        f"Excluding each hospital's own summary changed the contrast by {k3f(C['selfinc']['mean_comparator_minus_method_Brier'])}{unit}. "
        f"Across local-intercept penalties from 0.5 to 8 the contrast ranged from "
        f"{k3(min(c['mean_comparator_minus_method_Brier'] for c in pen))} to "
        f"{k3(max(c['mean_comparator_minus_method_Brier'] for c in pen))}{unit}. "
        + (f"In the final cohort, recorded hospital discharge preceded the 24-hour landmark in {doa['hospital_discharge_before_24_hour_landmark']:,} stays "
           f"and preceded unit discharge in {doa['hospital_discharge_before_unit_discharge']:,}; these recording inconsistencies were retained as specified. "
           if doa['hospital_discharge_before_24_hour_landmark'] or doa['hospital_discharge_before_unit_discharge'] else "")
        + f"Encrypted and plaintext maps agreed within {sci(fid['held_out_map_prediction_max_abs_error'])} on "
        f"{fid['n_held_out_target_predictions_compared']:,} held-out predictions."
    )
    abstract = (
        f"On eICU ({stays:,} stays, {H} hospitals), among {n} target hospitals with 0--5 calibration deaths, "
        f"{lead} ({peff}). Against a source-only binned map "
        + {"favors pooling": "the pooled map was also lower", "favors the comparator": "the source-only map was lower",
           "inconclusive": "the interval included zero"}[sdir]
        + ", and against source Platt scaling with a local intercept "
        + {"favors pooling": "the pooled map was also lower.", "favors the comparator": "that comparator was lower.",
           "inconclusive": "the interval included zero."}[ctrl_dirs["srcplatt"]]
    )
    disc = {
        "favors pooling": "In eICU the pooled map also beat the source-only binned map in the low-event stratum, consistent with the simulation scenario in which targets differed systematically from sources.",
        "favors the comparator": "In eICU the source-only binned map beat the pooled map in the low-event stratum, so these data give no support for pooling across hospitals beyond a source-only map.",
        "inconclusive": "In eICU the contrast with the source-only binned map was inconclusive, so these data do not establish that pooling across hospitals adds value beyond a source-only map; the simulation shows that this contrast is small when targets resemble sources.",
    }[sdir]
    cl, cp = sc["local_intercept_penalty2"]["patient_pooled_calibration_in_the_large_intercept"], \
        sc["pooled_binned_isotonic"]["patient_pooled_calibration_in_the_large_intercept"]
    if pdir == "favors pooling" and not isinstance(cl, str) and not isinstance(cp, str) and cl < cp < 0:
        disc += (f" The penalty-2 local intercept over-predicted more than the pooled map in this stratum "
                 f"(calibration-in-the-large {citl('local_intercept_penalty2')} versus {citl('pooled_binned_isotonic')}), "
                 "consistent with its shrinkage toward the over-predicting source-temperature model.")
    if ctrl_dirs["srcplatt"] == "inconclusive":
        disc += (" Against source Platt scaling with a local intercept, a stronger local comparator, the interval included zero, "
                 "so the eICU evidence does not show pooling beating a well-specified local recalibration.")
    concl = {
        "favors pooling": f"On eICU, pooled calibration had lower mean Brier score than a regularized local intercept at low-event hospitals ({k3(pm)}{unit}); the local intercept was lower in {st['local_intercept_lower_Brier_hospitals']} of {n} hospitals.",
        "favors the comparator": "On eICU, a regularized local intercept had lower mean Brier score than pooled calibration at low-event hospitals.",
        "inconclusive": "On eICU, the comparison with a regularized local intercept at low-event hospitals was inconclusive.",
    }[pdir]
    concl += " " + {"favors pooling": "Pooling also beat a source-only binned map.",
                    "favors the comparator": "A source-only binned map beat pooling.",
                    "inconclusive": "Whether pooling adds value beyond a source-only binned map was inconclusive."}[sdir]
    macros = {"EicuResultsText": text, "EicuAbstractSentence": abstract,
              "EicuDiscussion": disc, "EicuConclusion": concl}
    macros["EicuClaimScope"] = "broad" if broad else "named-comparator only"
    return rows, macros, pdir


def sci(x: float) -> str:
    if x == 0:
        return "$0$"
    m, e = f"{x:.1e}".split("e")
    return f"${m}\\times10^{{{int(e)}}}$"


PENDING_ROWS = [
    ("Cohort: stays, hospitals, mortality", r"\textbf{PENDING}", "From approved aggregate audit"),
    (r"\textbf{Primary}: pooled vs local intercept, 0--5 deaths", r"\textbf{PENDING}", "Paired $\\Delta$Brier and 95\\% interval"),
    ("Hospitals pooled lower / local lower / tied", r"\textbf{PENDING}", "Single-deletion sign stability"),
    ("Control: pooled vs source-only binned map", r"\textbf{PENDING}", "Tests pooling itself"),
    ("Control: pooled vs source Platt + local intercept", r"\textbf{PENDING}", ""),
    ("Control: leave-one-target-out pooled vs local", r"\textbf{PENDING}", ""),
    ("Control: leave-one-target-out pooled vs source Platt + local", r"\textbf{PENDING}", ""),
    ("Control: pooled isotonic vs pooled temperature", r"\textbf{PENDING}", ""),
    ("Diagnostic: leave-one-out vs self-including pooled", r"\textbf{PENDING}", ""),
    ("Local-intercept penalty 0.5, 1, 2, 4, 8", r"\textbf{PENDING}", ""),
    ("Calibration intercept/slope, all target stays", r"\textbf{PENDING}", ""),
    ("Calibration-in-the-large, 0--5-death stratum", r"\textbf{PENDING}", ""),
    ("CKKS vs plaintext, held-out map predictions", r"\textbf{PENDING}", ""),
]


def render(rows, macros, status: str) -> str:
    body = "\n".join(f"{m} & {r} & {i} \\\\" for m, r, i in rows)
    out = [f"% AUTO-GENERATED by fill_results_v31.py; status: {status}. Do not edit by hand.",
           f"\\newcommand{{\\EicuStatus}}{{{status}}}"]
    for k, v in macros.items():
        out.append(f"\\newcommand{{\\{k}}}{{{v}}}")
    out.append("\\newcommand{\\EicuTableRows}{%\n" + body + "\n}")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--release", type=Path)
    g.add_argument("--pending", action="store_true")
    ap.add_argument("--manifest", type=Path, help="sha256sum output for the six team-approved JSONs (required with --release)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.pending:
        macros = {"EicuResultsText": r"\textbf{PENDING: eICU results not yet approved; do not submit.}",
                  "EicuAbstractSentence": r"\textbf{PENDING eICU result.}",
                  "EicuDiscussion": r"\textbf{PENDING eICU discussion.}",
                  "EicuConclusion": r"\textbf{PENDING eICU conclusion.}",
                  "EicuClaimScope": "PENDING"}
        args.out.write_text(render(PENDING_ROWS, macros, "PENDING"))
        print("Wrote PENDING table")
        return
    need(args.manifest is not None, "--manifest is required with --release")
    rows, macros, pdir = build(load(args.release, args.manifest))
    args.out.write_text(render(rows, macros, "FILLED"))
    print(f"Wrote {args.out}; primary direction: {pdir}")


if __name__ == "__main__":
    main()
