"""Supplementary Table S2: all-target hospital-macro metrics, all methods and five split seeds (from the pinned v10 extract)."""
import json, hashlib
from pathlib import Path
SHA = "5035ef7b40e97e2b8caae526a61a9fba9028dc80568d67c186ed55c6d9e974ac"
raw = Path("candidates/v10_publication_extract.json").read_bytes()
assert hashlib.sha256(raw).hexdigest() == SHA, "hash mismatch"
X = json.loads(raw)
ORDER = [("Uncalibrated", "Uncalibrated"),
         ("PrivCal-B (secure-agg isotonic)", "Pooled binned isotonic (CKKS-summed statistics)"),
         ("PrivCal-A (secure-agg T)", "Pooled temperature (CKKS-summed statistics)"),
         ("Global-BinnedIsotonic (source-only)", "Source-only binned isotonic"),
         ("Global-Platt (source-only)", "Source-only Platt"),
         ("Global-T (source-only)", "Source-only temperature"),
         ("Per-site T (oracle)", "Per-hospital temperature (reference)"),
         ("Per-site isotonic (oracle)", "Per-hospital isotonic (reference)")]
MET = ("Brier", "NLL", "ECE", "aECE", "AUROC")
methods = {r["method"] for r in X["all_target_macro_metrics"]}
assert methods == {m for m, _ in ORDER}, methods
denoms = set()
rows = []
for s in (7, 11, 17, 23, 31):
    d = {r["method"]: r for r in X["all_target_macro_metrics"] if r["split_seed"] == s}
    rows.append(f"\\midrule\n\\multicolumn{{6}}{{@{{}}l}}{{\\textit{{Split seed {s}{' (primary)' if s == 7 else ''}}}}} \\\\")
    for m, label in ORDER:
        r = d[m]
        assert r["released"] and r["n_target_hospitals"] == 92
        vals = []
        for k in MET:
            v = r[f"macro_{k}"]; assert v != "withheld"
            vals.append(f"{v:.4f}" if k in ("Brier", "NLL") else f"{v:.3f}")
            denoms.add((k, str(r[f"n_valid_{k}"])))
        rows.append(f"{label} & " + " & ".join(vals) + " \\\\")
den = {k: sorted({v for kk, v in denoms if kk == k}) for k in MET}
assert all(len(v) == 1 for v in den.values()), den
n0, band = den["AUROC"][0].split(" minus ")
lo_, hi_ = band.split("-")
auroc_band = f"{int(n0) - int(hi_)} to {int(n0) - int(lo_)}"
note = ("Hospital-macro means over the 92 target hospitals of each split (each hospital weighted equally), computed on held-out test stays. "
        "Brier: mean squared error of predicted risk. NLL: negative log likelihood. ECE: 12-bin equal-width expected calibration error. "
        "aECE: 12-bin equal-mass adaptive ECE. AUROC: area under the receiver operating characteristic curve. "
        f"Valid-hospital denominators: Brier, NLL, ECE and aECE {den['Brier'][0]} in every split; AUROC {auroc_band} hospitals "
        "(hospitals without both outcomes in the test set are excluded; the exact count is banded). "
        "The splits reuse patients and hospitals; all cross-method and cross-split comparisons are descriptive. "
        "Monotone recalibration does not target discrimination. Per-hospital maps are fitted on each hospital's own calibration labels and are shown for reference only.")
tex = r"""\documentclass[10pt]{article}
\usepackage[margin=2cm]{geometry}\usepackage{mathptmx}\usepackage{booktabs}
\pagestyle{empty}
\begin{document}
\noindent\textbf{Supplementary Table S2.} All-target hospital-macro test metrics by recalibration method and split seed (eICU).\par\medskip
\noindent\small\begin{tabular}{@{}lrrrrr@{}}
\toprule
Method & Brier & NLL & ECE & aECE & AUROC \\
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}\par\medskip
\noindent{\footnotesize """ + note + r"""}
\end{document}
"""
Path("SupplementaryTableS2_macro_metrics.tex").write_text(tex)
print("S2 written", den)
