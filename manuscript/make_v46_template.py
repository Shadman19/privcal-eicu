"""v46 = v45 + post hoc APACHE IVa secondary analysis (Wahab job 6850784; JSON 818b637e...b842)."""
from pathlib import Path

t = Path("PrivCal_SciRep_v45.template.tex").read_text()


def rep(o, n):
    global t
    assert t.count(o) == 1, o[:90]
    t = t.replace(o, n)


rep("% INTERNAL DRAFT v45", "% INTERNAL DRAFT v46")

# Abstract: add the APACHE result to the post hoc sentence and tighten wording to stay within 200 words
rep("Risk models moved to a new hospital often need recalibration, but hospitals with few deaths cannot estimate even a simple local correction reliably.",
    "Risk models moved to new hospitals often need recalibration, but hospitals with few deaths cannot reliably estimate even a simple local correction.")
rep("intensive care stays from @@H@@ hospitals in eICU, we recalibrated a text-based mortality model at @@ntgt@@ target hospitals held out from predictor training",
    "intensive care stays from @@H@@ eICU hospitals, we recalibrated a text-based mortality model at @@ntgt@@ target hospitals excluded from predictor training")
rep("and compared a 12-bin isotonic map fitted to bin summaries summed across hospitals under CKKS homomorphic encryption with a regularized local intercept.",
    "and compared a 12-bin isotonic map, fitted to hospital bin summaries summed under CKKS homomorphic encryption, with a regularized local intercept.")
rep(r"With an unweighted base model (post hoc), the difference was @@s_ub_loc_mean@@ $\times10^{-3}$ (@@s_ub_lo@@ to @@s_ub_hi@@).",
    r"Post hoc, contrasts were @@s_ub_loc_mean@@ $\times10^{-3}$ (@@s_ub_lo@@ to @@s_ub_hi@@) with an unweighted model and @@ax_loc_mean@@ $\times10^{-3}$ (@@ax_loc_lo@@ to @@ax_loc_hi@@) with recorded APACHE IVa predictions in a redefined eligible stratum.")
rep("No incremental benefit over source-only recalibration was demonstrated.", "No benefit over a source-only binned map was demonstrated.")
rep("a source-only map came close to the pooled map when targets resembled sources",
    "a source-only map nearly matched pooling when targets resembled sources")
rep("per hospital and maps matched plaintext.", "per hospital; maps matched plaintext.")
rep("Pooled calibration should be benchmarked against source-based recalibration and under alternative base-model fitting before deployment.",
    "Before deployment, pooling should be benchmarked against source-based recalibration under several base models.")

# Introduction
rep(r"Post hoc, we also examine how the comparison depends on the class weighting of the base model.",
    r"Post hoc, we also examine how the comparison depends on the class weighting of the base model and whether its pattern holds when the recorded APACHE IVa prediction, an established severity score, is recalibrated instead.")

# Results: third post hoc analysis
rep(r"Two sensitivity analyses were specified after the frozen analysis and are post hoc (Table~\ref{tab:sens}).",
    r"Three sensitivity analyses were specified after the frozen analysis and are post hoc (Table~\ref{tab:sens}); their 95\% intervals are unadjusted and descriptive, and the comparisons are not independent confirmatory tests.")
rep(r"Because this refit changes more than the probability level, it does not isolate over-prediction as the cause, and similar Brier scores do not establish equivalence.",
    r"""Because this refit changes more than the probability level, it does not isolate over-prediction as the cause, and similar Brier scores do not establish equivalence.

Third, we recalibrated the recorded APACHE IVa hospital-mortality prediction instead of the text model, keeping the frozen hospital partition and each stay's split assignment. A valid APACHE IVa prediction was recorded for @@ax_elig@@ of the @@stays@@ stays (@@ax_elig_pct@@\%) and for @@ax_cov_prim@@\% of stays at the @@nlow@@ primary hospitals. With the 0--5-death stratum redefined on eligible calibration stays (@@ax_nh@@ target hospitals, not all of them primary hospitals; @@ax_tstays@@ test stays, @@ax_obs@@\% observed mortality), APACHE IVa over-predicted before recalibration (mean predicted risk @@ax_unc@@\%); after recalibration, mean predicted risk was @@ax_pr_pool@@\% for the pooled map and @@ax_pr_loc@@\% for the local intercept. The pooled map had a mean Brier score of @@ax_b_pool@@, compared with @@ax_b_loc@@ for the regularized local intercept (difference @@ax_loc@@ $\times10^{-3}$), @@ax_b_srcbin@@ for the source-only binned map (@@ax_srcbin@@) and @@ax_b_platt@@ for source Platt scaling with a local intercept (@@ax_platt@@). The pooled map thus again outperformed the regularized local intercept, by a smaller margin than with the class-weighted text model. The contrast against source Platt scaling with a local intercept favored pooling, with an unadjusted interval above zero; the primary point estimate also favored pooling, but its interval included zero. The contrast against the source-only binned map was inconclusive. The eligible population and the stratum's hospitals differ from the primary analysis, so these results are not a controlled comparison with it, and we make no claim that the recorded score was available at the 24-hour landmark.""")

# Discussion
rep(r"that refit changed both the predictor and the calibrators.",
    r"that refit changed both the predictor and the calibrators. With the recorded APACHE IVa score, which also over-predicted in this stratum before recalibration, the local intercept brought mean predicted risk close to observed mortality; the pooled map still had a lower Brier score, by a smaller margin, and also improved on source Platt scaling with a local intercept, with unadjusted intervals above zero.")
rep(r"the comparators were a binned map fitted to source hospitals alone and source Platt scaling with a local intercept, and neither base-model analysis established an incremental benefit of pooling over these source-based comparators; the intervals included zero and,",
    r"in no analysis did pooling establish an incremental benefit over a binned map fitted to source hospitals alone, and in neither text-model analysis did it establish one over source Platt scaling with a local intercept; these intervals included zero and,")
rep(r"The size of any gain also depends on how the base model was fitted:", r"The size of any gain also depends on the base model:")
rep(r"in eICU, the advantage over the local intercept largely disappeared with an unweighted base model.",
    r"in eICU, the advantage over the local intercept largely disappeared with an unweighted base model and was small when recalibrating the recorded APACHE IVa score.")
rep(r"The base model was developed for this study rather than an established severity score such as APACHE IVa, and whether the findings hold when recalibrating such a score was not tested.",
    r"The primary base model was developed for this study; the post hoc APACHE IVa analysis was restricted to stays with a valid recorded score (@@ax_elig_pct@@\%), and the time at which that score became available could not be verified.")
rep(r"The primary advantage over the local intercept depended strongly on class weighting of the base model, and both sensitivity analyses were post hoc.",
    r"The primary advantage over the local intercept depended strongly on class weighting of the base model, and all three sensitivity analyses were post hoc.")

# Conclusion
rep(r"with an unweighted base model the difference was small and its interval included zero. No incremental benefit over source-based recalibration was demonstrated in eICU.",
    r"with an unweighted base model the difference was small and its interval included zero, and with recorded APACHE IVa predictions it was small but its unadjusted interval excluded zero. No eICU analysis demonstrated an incremental benefit over a source-only binned map.")

# Methods
rep(r"we specified two sensitivity analyses in a hash-pinned script that first reproduced every primary hospital's pooled and local Brier scores from the frozen run (tolerance $10^{-9}$) and the discharge-offset counts.",
    r"we specified three sensitivity analyses. Analyses (i) and (ii) ran in a hash-pinned script that first reproduced every primary hospital's pooled and local Brier scores from the frozen run (tolerance $10^{-9}$) and the discharge-offset counts; analysis (iii) ran in a second hash-pinned script that first verified the final cohort, the seed-7 hospital partition and the primary hospital set against the frozen run.")
rep(r"Intervals use 2,000 paired hospital resamples with fixed seeds; paired changes compare each hospital's contrast with its frozen value. ", "")
rep(r"Counts of flagged stays from 1 to 19 were banded before release.",
    r"(iii) The recorded APACHE IVa hospital-mortality prediction replaced the text model as the base score (logit of the probability, clipped to $[10^{-6}, 1-10^{-6}]$); stays without exactly one APACHE IVa record, or whose prediction was missing or outside $[0, 1]$, were removed after the frozen split assignment, hospitals without eligible calibration or test stays were dropped, every recalibration method was refitted, and the 0--5-death stratum was redefined on eligible calibration stays. The study's own outcome label was used. Intervals use 2,000 paired hospital resamples with fixed seeds; paired changes compare each hospital's contrast with its frozen value. Counts of flagged stays from 1 to 19, and small counts of hospitals, were banded before release.")

# Table 4: caption and panel c
rep(r"\caption{Post hoc sensitivity analyses at the @@nlow@@ primary hospitals (0--5 calibration deaths, seed 7).",
    r"\caption{Post hoc sensitivity analyses in the stratum with 0--5 calibration deaths (seed 7).")
rep(r"\textbf{a}, Mean Brier score and contrasts with the class-weighted (primary) and unweighted base models; all maps refitted.",
    r"\textbf{a}, Mean Brier score and contrasts at the @@nlow@@ primary hospitals with the class-weighted (primary) and unweighted base models; all maps refitted.")
rep(r"\textbf{b}, Local intercept minus pooled map after removing stays with inconsistent discharge offsets.}",
    r"\textbf{b}, Local intercept minus pooled map at the same hospitals after removing stays with inconsistent discharge offsets. \textbf{c}, Recorded APACHE IVa prediction as the base score, with the stratum redefined on eligible calibration stays (@@ax_nh@@ hospitals, not all of them primary hospitals); not a controlled comparison with \textbf{a}.}")
rep(r"""@@SensRowsB@@
\bottomrule
\end{tabular}
\end{table}""",
    r"""@@SensRowsB@@
\bottomrule
\end{tabular}

\vspace{8pt}
\textbf{c}\quad\begin{tabular}[t]{@{}lrr@{}}
\toprule
Method & Mean Brier & Comparator $-$ pooled \\
\midrule
@@SensRowsC@@
\bottomrule
\end{tabular}
\end{table}""")

# Codex review of v46 text: label post hoc intervals in the Table 4 note
rep(r"two decimals with signs are shown when an interval includes zero. \textbf{a}",
    r"two decimals with signs are shown when an interval includes zero. These post hoc 95\% intervals are unadjusted and descriptive; the comparisons are not independent confirmatory tests. \textbf{a}")

# typo: missing comma in the code availability statement
rep("with dependency versions and checksums) the simulation code", "with dependency versions and checksums), the simulation code")

# accurate AI-use disclosure (Scientific Reports AI policy): tools also helped develop code and draft text
rep("were used for code review, auditing and manuscript editing under the authors' direction;", "were used for code development and review, auditing, and drafting and editing of the manuscript under the authors' direction;")

Path("PrivCal_SciRep_v46.template.tex").write_text(t)
print("template ok")
