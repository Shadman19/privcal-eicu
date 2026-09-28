#!/usr/bin/env python3
"""Minimal publication extract of aggregate_review_tables_v10.json (run on the authorized host).

Releases only what the manuscript needs, to avoid reconstruction of small groups:
* per split, the pooled-vs-local-intercept contrast for (a) all target hospitals and (b) the
  0-5-death stratum, as mean and 95% interval only (no median, IQR, win counts);
* a split's pair is released only if the 0-5 stratum AND its complement (all targets minus the
  0-5 stratum) each have at least MIN_GROUP hospitals, so the implied complement mean always
  averages over at least MIN_GROUP hospitals; otherwise both rows of that split are withheld;
* the 6-15, 16-30 and 31+ strata are never released (their means could be recovered jointly);
* all-target macro Brier/NLL/ECE/aECE/AUROC per method and split, only if >= MIN_GROUP
  hospitals are valid for that metric; the valid denominator is exact if the invalid count is 0
  or >= MIN_GROUP, otherwise reported as a band.
Primary, controls and penalty tables are omitted (already released). The input hash must match
the value recorded on the host. This is a disclosure-review aid, not a formal privacy guarantee;
a responsible person must approve the exact output before release.
"""
import argparse, hashlib, json
from pathlib import Path

MIN_GROUP = 10
LOW = "00-05 local deaths"
ALL = "all target hospitals"
# Bytes of the team-approved aggregate_publication_audit_v9.json (APPROVED_SHA256SUMS.txt).
APPROVED_AUDIT_SHA256 = "cac5f258ba95d17a3e0574c798dd36cbd0898a3f13e2e32a20d153425cfd56ad"


def load_approved_primary(path: Path, expected: str = APPROVED_AUDIT_SHA256) -> dict:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise SystemExit("--approved-audit is not the approved aggregate_publication_audit_v9.json (SHA-256 mismatch)")
    return json.loads(raw)["primary"]


def extract(j: dict, source_sha: str, approved_primary: dict | None = None) -> dict:
    meta = j["run_metadata"]
    if meta.get("version") != "real_eicu_v9_reproducibility_rerun" or not meta.get("real_ckks"):
        raise SystemExit("unexpected run metadata")
    rows = {(r["split_seed"], r["stratum"]): r for r in j["five_correlated_split_strata"]}
    splits = sorted({k[0] for k in rows})
    if splits != [7, 11, 17, 23, 31]:
        raise SystemExit("expected the five designated splits")
    # Consistency with the approved seed-7 primary estimate.
    p = j["primary"]; s7 = rows[(7, LOW)]
    if s7["results_suppressed"] or s7["n_target_hospitals"] != p["n_hospitals"] or \
            abs(s7["mean_comparator_minus_method_Brier"] - p["mean_comparator_minus_method_Brier"]) > 1e-10:
        raise SystemExit("seed-7 0-5 stratum disagrees with the approved primary estimate")
    if approved_primary is not None:
        ap_ = approved_primary
        if (ap_["n_hospitals"] != p["n_hospitals"] or ap_["bootstrap_seed"] != p["bootstrap_seed"]
                or abs(ap_["mean_comparator_minus_method_Brier"] - p["mean_comparator_minus_method_Brier"]) > 1e-12
                or any(abs(x - y) > 1e-12 for x, y in zip(ap_["paired_hospital_bootstrap_95_CI"], p["paired_hospital_bootstrap_95_CI"]))):
            raise SystemExit("v10 primary block differs from the approved primary audit")
    contrasts = []
    for s in splits:
        a, lo = rows[(s, ALL)], rows[(s, LOW)]
        n_all, n_low = a["n_target_hospitals"], lo["n_target_hospitals"]
        ok = (not a["results_suppressed"] and not lo["results_suppressed"]
              and n_low >= MIN_GROUP and (n_all - n_low) >= MIN_GROUP)
        for r, name in ((a, "all target hospitals"), (lo, "0-5 calibration deaths")):
            out = {"split_seed": s, "group": name, "released": ok}
            if ok:
                ci, seed = r["paired_hospital_bootstrap_95_CI"], r["bootstrap_seed"]
                if s == 7 and name == "0-5 calibration deaths":
                    # Use the locked primary interval (seed 971), not the v10 re-bootstrap.
                    ci, seed = p["paired_hospital_bootstrap_95_CI"], p["bootstrap_seed"]
                out.update({"n_hospitals": r["n_target_hospitals"],
                            "mean_local_minus_pooled_Brier": r["mean_comparator_minus_method_Brier"],
                            "paired_hospital_bootstrap_95_CI": ci, "bootstrap_seed": seed})
            contrasts.append(out)
    metrics = []
    for r in j["target_method_macro_metrics"]:
        out = {"split_seed": r["split_seed"], "method": r["method"],
               "n_target_hospitals": r["n_target_hospitals"]}
        if r["results_suppressed"] or r["n_target_hospitals"] < MIN_GROUP:
            out["released"] = False
            metrics.append(out); continue
        out["released"] = True
        for m in ("Brier", "NLL", "ECE", "aECE", "AUROC"):
            nv, v = r[f"n_valid_{m}"], r[f"macro_{m}"]
            if v is None or nv < MIN_GROUP:
                out[f"macro_{m}"] = "withheld"; continue
            out[f"macro_{m}"] = v
            inval = r["n_target_hospitals"] - nv
            out[f"n_valid_{m}"] = nv if inval == 0 or inval >= MIN_GROUP else f"{r['n_target_hospitals']} minus 1-{MIN_GROUP - 1}"
        metrics.append(out)
    return {"purpose": "minimal publication extract of v10 correlated five-split sensitivity tables (secondary, post hoc)",
            "source_sha256": source_sha, "run_started_utc": meta.get("run_started_utc"),
            "source_notebook_sha256": meta.get("source_notebook_sha256"), "min_group_hospitals": MIN_GROUP,
            "split_contrasts": contrasts, "all_target_macro_metrics": metrics,
            "notes": ["Splits reuse patients; they are correlated sensitivity analyses, not independent replications.",
                      "Only all-target and 0-5-death contrasts are released; other death strata are withheld.",
                      "Monotone recalibration does not target discrimination; AUROC is descriptive.",
                      "Seed-7 0-5 interval is the locked primary interval (bootstrap seed 971).",
                      "No site identifier, record, or per-hospital score is included. The group-size rule limits",
                      "direct complementary-mean reconstruction only; it is not a privacy guarantee."]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--expected-sha256", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--approved-audit", type=Path, required=True,
                    help="team-approved aggregate_publication_audit_v9.json; its primary block must match v10")
    a = ap.parse_args()
    raw = a.input.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != a.expected_sha256.lower():
        raise SystemExit("input hash mismatch")
    if a.output.exists():
        raise SystemExit(f"refusing to overwrite {a.output}")
    approved = load_approved_primary(a.approved_audit)
    a.output.write_text(json.dumps(extract(json.loads(raw), sha, approved), indent=2, allow_nan=False) + "\n")
    print(f"Wrote {a.output}")


if __name__ == "__main__":
    main()
