"""v45 = v44 + joint Claude/Codex pre-submission review: title and framing (R1), limitation on the base model (R2, text),
threat model and secure-aggregation comparison (R3), relative Brier and predicted-risk context (R4), targeted verified
references (R5). References are reordered by first citation."""
import re
from pathlib import Path

t = Path("PrivCal_SciRep_v44.template.tex").read_text()


def rep(o, n):
    global t
    assert t.count(o) == 1, o[:90]
    t = t.replace(o, n)


rep("% INTERNAL DRAFT v44", "% INTERNAL DRAFT v45")

# R1: title as one accurate sentence (Sci Rep: <=20 words, main message)
rep(r"\title{Encrypted pooled recalibration of intensive care mortality predictions at hospitals with few observed deaths}",
    r"\title{Gains from encrypted pooled recalibration at eICU hospitals with few calibration deaths depended on base-model class weighting and comparator}")

# Introduction
rep(r"calibration often deteriorates when a model moves between hospitals with different case mix, documentation habits or outcome prevalence\cite{r3}. Recalibration with local outcome data is the standard remedy\cite{r17}.",
    r"calibration often deteriorates when a model moves between hospitals with different case mix, documentation habits or outcome prevalence\cite{r3,vancalster2019,finlayson2021}. Recalibration with local outcome data is the standard remedy\cite{r17,janssen2008}.")
rep(r"Distributed and federated calibration methods address this by exchanging aggregate statistics or model parameters\cite{r4,r5,r16,r6,r20}, and homomorphic encryption allows such statistics to be summed so that, with independent key custody and a controlled release policy, the aggregator need not see any single hospital's contribution\cite{r18,r7,r8}; our implementation demonstrates the arithmetic in a single process rather than a deployed protocol (Methods).",
    r"Federated approaches keep patient records at each hospital and exchange only model updates or statistics\cite{rieke2020}. Distributed and federated calibration methods exchange aggregate statistics or model parameters\cite{r4,r5,r16,r6,r20}, and homomorphic encryption allows such statistics to be summed so that, with independent key custody and a controlled release policy, the aggregator need not see any single hospital's contribution\cite{r18,r7,r8}. Our eICU analysis demonstrates the arithmetic in a single process, and a separate-process prototype on synthetic hospitals tests key separation and cost (Methods).")
rep(r"and we map when pooling helps and when it harms.",
    r"and we map when pooling helps and when it harms. Post hoc, we also examine how the comparison depends on the class weighting of the base model.")

# R4: Results, relative difference and predicted-risk context
rep(r"the encrypted pooled map had a mean held-out Brier score of @@bpool@@, compared with @@bloc@@", r"the encrypted pooled map had a mean held-out Brier score of @@bpool4@@, compared with @@bloc@@")
rep(r"compared with @@bloc@@ for the regularized local intercept (Fig.~\ref{fig:contrasts}a).",
    r"compared with @@bloc4@@ for the regularized local intercept, about @@prim_rel@@\% lower for pooling (Fig.~\ref{fig:contrasts}a); with an unweighted base model the difference was small (see Post hoc sensitivity analyses). Across the held-out test stays of these hospitals, the local intercept predicted @@strat_pred_loc@@\% mean risk versus @@strat_obs@@\% observed mortality.")

# R5: calibration-in-the-large definition
rep(r"calibration-in-the-large (intercept with slope fixed at 1)",
    r"calibration-in-the-large (intercept with slope fixed at 1)\cite{vancalster2016}")
rep(r"an established model-updating form \cite{r17}", r"an established model-updating form \cite{r17,janssen2008}")

# R3: threat model subsection before the prototype methods
rep(r"\subsection*{Separate-process prototype}\label{prototype-methods}",
    r"""\subsection*{Threat model}\label{threat-model}
The intended deployment has three roles: participating hospitals, an aggregator that receives and adds ciphertexts, and an independent key custodian that holds the only CKKS secret key. We assume honest-but-curious parties that follow the protocol and no collusion between the aggregator and the custodian. Before release, the aggregator observes ciphertexts, message sizes and which hospitals took part; the custodian can decrypt the pooled vectors (pooled bin counts, deaths and predicted-score sums, and the pooled temperature-loss curve), from which the pooled map is computed; and the released map is visible to its recipients. Authenticated aggregation, a minimum number of participating hospitals, decryption restricted to approved pooled sums and independently governed key custody are deployment requirements that this study did not implement. The design does not protect against collusion, against hospitals that submit false summaries, or against inference from the pooled summaries themselves, for example by differencing releases computed over overlapping sets of hospitals or from bins containing very few patients, and it provides no differential privacy guarantee. The eICU analysis emulated all roles in one process and therefore establishes arithmetic fidelity only. The separate-process prototype tests key separation and numerical fidelity on one machine, but does not establish independently governed key custody or protection against selective decryption, collusion or differencing.

\subsection*{Separate-process prototype}\label{prototype-methods}""")

# R1: Discussion framing (keeps Codex-approved sentences)
rep(r"Hospitals with very few observed deaths are where local recalibration is least reliable and where pooling is most often proposed. In eICU, an encrypted pooled isotonic map clearly beat a regularized local intercept at such hospitals,",
    r"Hospitals with very few observed deaths are where local recalibration is least reliable and where pooling is most often proposed. Whether encrypted pooling helped them depended on the comparator and on the base model. Against a strongly regularized local intercept, the prespecified comparison clearly favored the encrypted pooled isotonic map at such hospitals,")
rep(r"against a binned map fitted to source hospitals alone, and against source Platt scaling with a local intercept, the pooled map showed no incremental benefit. Because no equivalence margin was prespecified, this does not show that the methods are equivalent.",
    r"the comparators were a binned map fitted to source hospitals alone and source Platt scaling with a local intercept, and neither base-model analysis established an incremental benefit of pooling over these source-based comparators; the intervals included zero and, because no equivalence margin was prespecified, do not establish equivalence.")

# R5 + R3: Discussion practical check and secure aggregation
rep(r"rather than only against a heavily shrunken local update.",
    r"rather than only against a heavily shrunken local update. Established model-updating guidance likewise selects among simple and more extensive updates according to the data available\cite{janssen2008,vergouwe2017}.")
rep(r"and in a separate-process prototype it cost about @@pr_enc@@~s and @@pr_mb@@~MB per hospital.",
    r"and in a separate-process prototype it cost about @@pr_enc@@~s and @@pr_mb@@~MB per hospital. Secret-sharing secure aggregation solves the same summation problem without homomorphic encryption and tolerates hospitals that drop out during a round\cite{bonawitz2017}; homomorphic encryption instead lets a single aggregator add contributions without pairwise exchanges between hospitals, at the cost of relying on an independent key holder. We did not compare the two, and both release the same pooled summaries, so the inference risks described in the threat model apply to either. Adding differential privacy noise to the released aggregates would require a specific mechanism and an assessment of its effect on calibration at low-event hospitals, which we leave to future work.")

# R2 (text): limitation on the base model
rep(r"so external validation in another health system is needed.",
    r"so external validation in another health system is needed. The base model was developed for this study rather than an established severity score such as APACHE IVa, and whether the findings hold when recalibrating such a score was not tested.")

# Ethics (authors' decision, 28 Sep 2026): publicly available, de-identified, credentialed-access data; training completed
rep(r"accessed under the PhysioNet credentialed data use agreement after the required human-research training\cite{r1}.",
    r"which is publicly available to credentialed researchers through PhysioNet\cite{r1}. The first author completed the human-research training required by PhysioNet and obtained credentialed access under its data use agreement before any analysis.")
rep(r"Because only de-identified data were analysed, review by the Old Dominion University institutional review board was not sought, and individual informed consent was not required for this secondary analysis.",
    r"Because the study was a secondary analysis of publicly available, de-identified data with no contact with patients, review by the Old Dominion University institutional review board was not sought, and individual informed consent was not obtained, as the patients cannot be identified.")

# R5: verified references (Crossref-checked 28 Sep 2026)
NEW = {
 "vancalster2019": r"Van Calster B, McLernon DJ, van Smeden M, Wynants L, Steyerberg EW; Topic Group `Evaluating diagnostic tests and prediction models' of the STRATOS initiative. Calibration: the Achilles heel of predictive analytics. BMC Medicine. 2019;17:230. doi:10.1186/s12916-019-1466-7.",
 "finlayson2021": r"Finlayson SG, Subbaswamy A, Singh K, Bowers J, Kupke A, Zittrain J, Kohane IS, Saria S. The clinician and dataset shift in artificial intelligence. New England Journal of Medicine. 2021;385(3):283--286. doi:10.1056/NEJMc2104626.",
 "janssen2008": r"Janssen KJM, Moons KGM, Kalkman CJ, Grobbee DE, Vergouwe Y. Updating methods improved the performance of a clinical prediction model in new patients. Journal of Clinical Epidemiology. 2008;61(1):76--86. doi:10.1016/j.jclinepi.2007.04.018.",
 "rieke2020": r"Rieke N, Hancox J, Li W, Milletar{\`i} F, Roth HR, et al. The future of digital health with federated learning. npj Digital Medicine. 2020;3:119. doi:10.1038/s41746-020-00323-1.",
 "vancalster2016": r"Van Calster B, Nieboer D, Vergouwe Y, De Cock B, Pencina MJ, Steyerberg EW. A calibration hierarchy for risk models was defined: from utopia to empirical data. Journal of Clinical Epidemiology. 2016;74:167--176. doi:10.1016/j.jclinepi.2015.12.005.",
 "vergouwe2017": r"Vergouwe Y, Nieboer D, Oostenbrink R, Debray TPA, Murray GD, Kattan MW, Koffijberg H, Moons KGM, Steyerberg EW. A closed testing procedure to select an appropriate method for updating prediction models. Statistics in Medicine. 2017;36(28):4529--4539. doi:10.1002/sim.7179.",
 "bonawitz2017": r"Bonawitz K, Ivanov V, Kreuter B, Marcedone A, McMahan HB, Patel S, Ramage D, Segal A, Seth K. Practical secure aggregation for privacy-preserving machine learning. In: Proceedings of the 2017 ACM SIGSAC Conference on Computer and Communications Security. ACM; 2017:1175--1191. doi:10.1145/3133956.3133982.",
}
b0, b1 = t.index(r"\begin{thebibliography}"), t.index(r"\end{thebibliography}")
bib = t[b0:b1]
items = dict(re.findall(r"\\bibitem\{(\w+)\} (.*)", bib))
assert len(items) == 19
items.update(NEW)
body = t[:b0]
order = []
for grp in re.findall(r"\\cite\{([^}]*)\}", body):
    for k in grp.split(","):
        k = k.strip()
        if k not in order:
            order.append(k)
assert set(order) == set(items), (set(order) ^ set(items))
newbib = "\\begin{thebibliography}{" + str(len(order)) + "}\n" + "\n".join(f"\\bibitem{{{k}}} {items[k]}" for k in order) + "\n"
t = t[:b0] + newbib + t[b1:]
Path("PrivCal_SciRep_v45.template.tex").write_text(t)
print("template ok;", len(order), "references in first-citation order")
