"""Supplementary Methods (text moved verbatim from the main Methods) and Supplementary Table S3 (prototype)."""
import json, hashlib, statistics as st
from pathlib import Path

PROTO_SHA = "3823b9a9e725180c40fdc458d65f80136a4b90a18cd0882c79aa3b9f2d84ea70"
raw = Path("proto/ckks_prototype_results.json").read_bytes()
assert hashlib.sha256(raw).hexdigest() == PROTO_SHA, "prototype results hash mismatch"
P = json.loads(raw)
M = json.load(open("supp_methods_moved.json"))

rows = []
for H in sorted({r["H"] for r in P["runs"]}):
    rs = [r for r in P["runs"] if r["H"] == H]
    assert all((not r["aggregator_can_decrypt"]) and r["rounded_counts_deaths_exact"] and r["temperature_choice_equal"] for r in rs)
    med = lambda k: st.median(r[k] for r in rs)
    mx = max(r["pooled_map_max_abs_diff"] for r in rs)
    m, e = f"{mx:.1e}".split("e")
    rows.append(f"{H} & {len(rs)} & {med('encrypt_s_per_hospital_median'):.3f} & {med('bytes_per_hospital')/1e6:.2f} & "
                f"{med('aggregate_s'):.2f} & {med('decrypt_s'):.3f} & {med('wall_s'):.1f} & ${m}\\times10^{{{int(e)}}}$ & No \\\\")
pk = P["packed_variant"]; env = P["environment"]
tex = r"""\documentclass[10pt]{article}
\usepackage[margin=2.2cm]{geometry}\usepackage{mathptmx}\usepackage{booktabs}\usepackage{hyperref}
\pagestyle{plain}
\begin{document}
\noindent{\large\textbf{Supplementary Methods}}\par\medskip
\noindent These details were moved from the main Methods for readability; the analysis is unchanged.

\subsection*{S1. Local comparators}
""" + M["local"] + r"""

\subsection*{S2. Bootstrap edge cases}
""" + M["boot"] + r"""The primary stratum contained 26 hospitals, so these edge cases did not arise in the reported eICU analysis.

\subsection*{S3. Encryption scope of the eICU run}
""" + M["enc"] + r"""

\subsection*{S4. Disclosure control for released aggregates}
""" + M["disc"] + r"""

\subsection*{S5. Separate-process prototype}
Roles ran in separate operating-system processes (Python multiprocessing, spawn start method) and exchanged only serialized bytes through pipes. The key custodian created a CKKS context (polynomial modulus degree 8,192; coefficient moduli 60/40/40/60 bits; scale $2^{40}$, as in the frozen notebook) and sent hospitals and the aggregator a public context serialized without the secret key; both checked that the received context was not private. Synthetic hospitals were generated as in the main simulation (calibration sets of about a quarter of 130 to 3,000 stays; an over-predicting base model), and each encrypted its 96 temperature-loss terms, calibration count, and 12-bin counts, deaths and score sums as five CKKS vectors. The aggregator summed the ciphertexts, attempted to decrypt one sum (which failed in every run), and sent the sums to the custodian. A plaintext sum computed by the test harness was used only to check the decrypted aggregates and the resulting weighted isotonic map on a 1,000-point grid. Environment: """ + f"{env['cpus']} CPU cores, Python {env['python']}, TenSEAL {env['tenseal']}" + r""".

\clearpage
\noindent\textbf{Supplementary Table S3.} Separate-process CKKS prototype on synthetic hospitals (medians over replicates).\par\smallskip
\noindent\footnotesize\begin{tabular}{@{}rrrrrrrrr@{}}
\toprule
Hospitals & Reps & Encrypt (s/hosp.) & MB/hosp. & Aggregate (s) & Decrypt (s) & Total (s) & Max map diff. & Agg. decrypts \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}\par\smallskip
\noindent{\footnotesize In every run, rounded counts and deaths equalled the plaintext sums and the temperature choice matched plaintext. MB/hosp.: ciphertext bytes sent by one hospital (five vectors). Total: wall time including process start-up. Packing all """ + f"{pk['values']} values into one ciphertext gave {pk['bytes_median']/1e6:.2f} MB and {pk['encrypt_s_median']:.3f} s per hospital (median of {pk['reps']})" + r""". One machine; no network latency, collusion, malicious-input or differencing evaluation.}
\end{document}
"""
Path("SupplementaryMethods_TableS3.tex").write_text(tex)
print("written")
