"""Real-data figures for the Scientific Reports version, from the team-approved aggregate JSONs only."""
import json, hashlib, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7, "font.family": "serif", "axes.linewidth": 0.6})
R = Path(sys.argv[1] if len(sys.argv) > 1 else "approved")
man = {l.split()[1]: l.split()[0] for l in (R/"APPROVED_SHA256SUMS.txt").read_text().split("\n") if l.strip()}
J = {}
for n, h in man.items():
    b = (R/n).read_bytes(); assert hashlib.sha256(b).hexdigest() == h, n; J[n] = json.loads(b)
a = J["aggregate_publication_audit_v9.json"]; d = J["aggregate_calibration_diagnostics_seed7.json"]

# Figure 2: paired contrasts (x1e-3), positive favours the first-named (pooled) method.
rows = [("Primary: pooled vs local intercept (λ=2)", a["primary"])]
lab = {"leave_one_target_hospital_out_pooled_binned_isotonic_vs_regularized_local_intercept": "Leave-one-out pooled vs local intercept",
       "self_including_pooled_binned_isotonic_vs_source_only_binned_isotonic": "Pooled vs source-only binned map",
       "self_including_pooled_binned_isotonic_vs_source_platt_local_intercept": "Pooled vs source Platt + local intercept",
       "leave_one_target_hospital_out_pooled_binned_isotonic_vs_source_platt_local_intercept": "Leave-one-out pooled vs source Platt + local",
       "leave_one_target_hospital_out_pooled_binned_isotonic_vs_self_including_pooled_binned_isotonic": "Leave-one-out vs self-including pooled"}
for c in a["low_event_seed7_sensitivity"]:
    if c["comparison"] in lab: rows.append((lab[c["comparison"]], c))
pen = sorted(a["local_intercept_penalty_sensitivity"], key=lambda c: c["local_intercept_penalty"])
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.6), gridspec_kw={"width_ratios": [1.35, 1]})
for i, (name, c) in enumerate(rows[::-1]):
    m = 1e3*c["mean_comparator_minus_method_Brier"]; lo, hi = [1e3*x for x in c["paired_hospital_bootstrap_95_CI"]]
    col = "#1f5aa6" if lo > 0 else ("#b33" if hi < 0 else "#555")
    ax1.errorbar(m, i, xerr=[[m-lo], [hi-m]], fmt="o", ms=3, color=col, capsize=2, lw=0.8)
ax1.set_yticks(range(len(rows))); ax1.set_yticklabels([r[0] for r in rows[::-1]])
ax1.axvline(0, color="k", lw=0.5, ls=":"); ax1.set_xlabel(r"$\Delta$Brier (comparator − method), $\times10^{-3}$")
ax1.set_title(f"a  Low-event hospitals (n = {a['primary']['n_hospitals']}), seed 7", loc="left", fontsize=7)
x = [c["local_intercept_penalty"] for c in pen]; m = [1e3*c["mean_comparator_minus_method_Brier"] for c in pen]
lo = [1e3*c["paired_hospital_bootstrap_95_CI"][0] for c in pen]; hi = [1e3*c["paired_hospital_bootstrap_95_CI"][1] for c in pen]
ax2.errorbar(range(len(x)), m, yerr=[[a_-b_ for a_, b_ in zip(m, lo)], [b_-a_ for a_, b_ in zip(m, hi)]], fmt="o-", ms=3, color="#1f5aa6", capsize=2, lw=0.8)
ax2.set_xticks(range(len(x))); ax2.set_xticklabels([f"{v:g}" for v in x]); ax2.axhline(0, color="k", lw=0.5, ls=":")
ax2.set_xlabel("Local-intercept ridge penalty λ"); ax2.set_ylabel(r"$\Delta$Brier (local − pooled), $\times10^{-3}$")
ax2.set_title("b  Penalty sensitivity", loc="left", fontsize=7)
fig.tight_layout(); fig.savefig("fig2_eicu_contrasts.pdf"); fig.savefig("fig2_eicu_contrasts.png", dpi=250)

# Figure 3: held-out reliability, all seed-7 target stays (bins with <20 stays suppressed at source).
names = {"PrivCal-B (secure-agg isotonic)": ("Pooled binned isotonic (encrypted)", "#1f5aa6", "o"),
         "Global-Platt (source-only)": ("Source Platt", "#2a9d5c", "s"),
         "Local-intercept (source-T)": ("Local intercept (λ=2)", "#c0392b", "^")}
fig, ax = plt.subplots(figsize=(3.3, 3.1))
ax.plot([0, 1], [0, 1], color="k", lw=0.5, ls=":")
for k, (nm, col, mk) in names.items():
    bins = [b for b in d["target_seed7_methods"][k]["reliability_equal_width_bins"] if not b["suppressed"]]
    ax.plot([b["mean_predicted"] for b in bins], [b["observed_death_fraction"] for b in bins], marker=mk, ms=3, lw=0.8, color=col, label=nm)
t = d["target_seed7_methods"]["PrivCal-B (secure-agg isotonic)"]
ax.set_xlim(0, 0.9); ax.set_ylim(0, 0.9); ax.set_xlabel("Mean predicted risk"); ax.set_ylabel("Observed hospital mortality")
ax.set_title(f"{t['n_target_hospitals']} target hospitals, {t['n_test_stays']:,} held-out stays", fontsize=7)
ax.legend(frameon=False, fontsize=6, loc="upper left")
fig.tight_layout(); fig.savefig("fig3_reliability.pdf"); fig.savefig("fig3_reliability.png", dpi=250)
print("ok")
