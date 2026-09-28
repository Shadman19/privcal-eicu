"""Derive the v43 template from v42: post hoc sensitivity results (job 6849951), Codex-reviewed wording."""
from pathlib import Path

t = Path("PrivCal_SciRep_v42.template.tex").read_text()


def rep(old, new):
    global t
    assert t.count(old) == 1, old[:80]
    t = t.replace(old, new)


rep("% INTERNAL DRAFT v40", "% INTERNAL DRAFT v43")

# abstract: lead with frozen result, qualify immediately (Codex)
a0 = t[t.index("\\noindent Risk models moved"):t.index("\\end{abstract}")]
a1 = ("\\noindent Risk models moved to a new hospital often need recalibration, but hospitals with few deaths cannot estimate even a simple local correction reliably. "
      "Using @@stays@@ intensive care stays from @@H@@ hospitals in eICU, we recalibrated a text-based mortality model at @@ntgt@@ target hospitals held out from predictor training but contributing calibration labels, and compared a 12-bin isotonic map fitted to bin summaries summed across hospitals under CKKS homomorphic encryption with a regularized local intercept. "
      "In the @@nlow@@ hospitals with 0--5 calibration deaths, the pooled map had lower mean Brier score (difference @@prim_mean@@ $\\times10^{-3}$, 95\\% interval @@prim_lo@@ to @@prim_hi@@) and was better at @@plower@@ hospitals. "
      "With an unweighted base model (post hoc), the difference was @@s_ub_loc_mean@@ $\\times10^{-3}$ (@@s_ub_lo@@ to @@s_ub_hi@@). "
      "No incremental benefit over source-only recalibration was demonstrated. "
      "In 160 simulated health systems, a source-only map came close to the pooled map when targets resembled sources, and pooling harmed a growing share of low-event hospitals under heterogeneous prevalence. "
      "In a synthetic separate-process prototype with custodian-held keys, encryption took @@pr_enc@@~s and @@pr_mb@@~MB per hospital and maps matched plaintext. "
      "Pooled calibration should be benchmarked against source-based recalibration and under alternative base-model fitting before deployment.\n")
t = t.replace(a0, a1)

rep("these recording inconsistencies were retained as specified.",
    "these recording inconsistencies were retained as specified and removed in a post hoc sensitivity analysis (below).")

rep("\\subsection*{Calibration and discrimination}", r"""\subsection*{Post hoc sensitivity analyses}
Two sensitivity analyses were specified after the frozen analysis and are post hoc (Table~\ref{tab:sens}). First, of the stays with inconsistent discharge offsets, @@s_order_prim@@ were at the @@nlow@@ primary hospitals and @@s_order_test@@ of these were in test sets. Removing flagged stays from evaluation only gave a difference of @@s_a1@@ $\times10^{-3}$ (paired change from the frozen analysis @@s_a1chg@@). Removing them before refitting the predictor and all recalibration maps, with each remaining stay's original split assignment kept, gave @@s_a2@@ $\times10^{-3}$ at the same @@nlow@@ hospitals (paired change @@s_a2chg@@). The positive direction therefore persisted at the original hospitals. After this exclusion a few additional hospitals had 0--5 calibration deaths; they were not added to the comparison.

Second, we refitted the base model without class weighting and refitted every recalibration map. In the primary-stratum test stays (@@s_ub_tstays@@ stays, @@s_ub_obs@@\% observed mortality), mean predicted risk was @@s_ub_unc@@\% before recalibration, @@s_ub_ppool@@\% after the pooled map and @@s_ub_ploc@@\% after the local intercept, and the four methods' mean Brier scores ranged from @@s_ub_bmin@@ to @@s_ub_bmax@@. The pooled-versus-local difference fell to @@s_ub_loc@@ $\times10^{-3}$ (paired change from the class-weighted model @@s_ub_chg@@ $\times10^{-3}$), and neither source-based contrast excluded zero. The pooled map's mean Brier score was similar under the two base models (@@s_bw_pool@@ and @@s_bu_pool@@), whereas the local intercept's fell from @@s_bw_loc@@ to @@s_bu_loc@@. The advantage over the local intercept was therefore highly sensitive to class weighting; numerically, most of the attenuation came from improved local-intercept performance after the predictor and calibrators were refitted. Because this refit changes more than the probability level, it does not isolate over-prediction as the cause, and similar Brier scores do not establish equivalence.

\subsection*{Calibration and discrimination}""")

rep("The calibration diagnostics show why: with few events, the local intercept stays close to an over-predicting base model, whereas the binned map corrects the probability scale.",
    "In the primary low-event hospitals, the class-weighted pipeline's local-intercept predictions averaged @@strat_pred_loc@@\\% risk against @@strat_obs@@\\% observed mortality, while pooled and source-only binned predictions averaged @@strat_pred_pool@@\\% and @@strat_pred_src@@\\%. This is consistent with a calibration problem for the strongly regularized local comparator, but does not isolate its cause. A post hoc refit with an unweighted base model brought the local intercept within $1\\times10^{-3}$ of the pooled map while the pooled map's accuracy was essentially unchanged; that refit changed both the predictor and the calibrators.")
rep("rather than only against a heavily shrunken local update.",
    "rather than only against a heavily shrunken local update. The size of any gain also depends on how the base model was fitted: in eICU, the advantage over the local intercept largely disappeared with an unweighted base model.")
rep("and a small fraction of stays had inconsistent discharge offsets that were retained and whose presence in the primary stratum was not assessed.",
    "and a small fraction of stays had inconsistent discharge offsets; removing them in post hoc analyses left the direction of the primary contrast unchanged at the original hospitals.")
rep("The hospital bootstrap treats the fitted pipeline as fixed",
    "The primary advantage over the local intercept depended strongly on class weighting of the base model, and both sensitivity analyses were post hoc. The hospital bootstrap treats the fitted pipeline as fixed")
rep("In conclusion, encrypted pooled recalibration improved probabilistic accuracy over a regularized local intercept at hospitals with few observed deaths, with arithmetic that matched plaintext.",
    "In conclusion, encrypted pooled recalibration improved probabilistic accuracy over a regularized local intercept at hospitals with few observed deaths when the base model was class-weighted, with arithmetic that matched plaintext; with an unweighted base model the difference was small and its interval included zero.")

rep("\\subsection*{Supplementary simulation with known risks}\\label{simulation-methods}",
    r"""\textit{Post hoc sensitivity analyses.} After the frozen analysis, we specified two sensitivity analyses in a hash-pinned script that first reproduced every primary hospital's pooled and local Brier scores from the frozen run (tolerance $10^{-9}$) and the discharge-offset counts. (i) Stays whose recorded hospital discharge preceded the 24-hour landmark or unit discharge were removed either from test sets only or before refitting the predictor and all recalibration maps, with each remaining stay's original seed-7 assignment kept; contrasts were evaluated at the original @@nlow@@ primary hospitals. (ii) The base logistic model was refitted without class weighting, all other settings unchanged, and every recalibration method was refitted. Intervals use 2,000 paired hospital resamples with fixed seeds; paired changes compare each hospital's contrast with its frozen value. Counts of flagged stays from 1 to 19 were banded before release.

\subsection*{Supplementary simulation with known risks}\label{simulation-methods}""")

TAB = r"""\begin{table}[p]
\caption{Post hoc sensitivity analyses at the @@nlow@@ primary hospitals (0--5 calibration deaths, seed 7). Differences are comparator minus pooled Brier ($\times10^{-3}$; positive favors pooling) with paired hospital-bootstrap 95\% intervals; two decimals with signs are shown when an interval includes zero. \textbf{a}, Mean Brier score and contrasts with the class-weighted (primary) and unweighted base models; all maps refitted. \textbf{b}, Local intercept minus pooled map after removing stays with inconsistent discharge offsets.}
\label{tab:sens}
\centering\footnotesize
\textbf{a}\quad\begin{tabular}[t]{@{}lrrrr@{}}
\toprule
 & \multicolumn{2}{c}{Mean Brier} & \multicolumn{2}{c}{Comparator $-$ pooled} \\
Method & Weighted & Unweighted & Weighted & Unweighted \\
\midrule
@@SensRowsA@@
\bottomrule
\end{tabular}

\vspace{2pt}
{\scriptsize Paired change in local minus pooled, unweighted minus weighted: @@s_ub_chg@@ $\times10^{-3}$. Scores within $1\times10^{-3}$ do not establish equivalence.}

\vspace{8pt}
\textbf{b}\quad\begin{tabular}[t]{@{}lrr@{}}
\toprule
Analysis & Local $-$ pooled & Change from frozen \\
\midrule
@@SensRowsB@@
\bottomrule
\end{tabular}
\end{table}

"""
i = t.index("\\begin{figure}[p]\n")
t = t[:i] + TAB + t[i:]
Path("PrivCal_SciRep_v43.template.tex").write_text(t)
print("template ok")
