import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
S=json.load(open("simulation_summary_v25.json"))["scenarios"]
sig=[s["sigma"] for s in S]
plt.rcParams.update({"pdf.fonttype":42,"ps.fonttype":42,"font.size":7,"font.family":"serif","axes.linewidth":0.6,"xtick.major.width":0.6,"ytick.major.width":0.6})
fig,(a,b)=plt.subplots(1,2,figsize=(3.5,1.75),constrained_layout=True)
for key,col,lab,dx,mk in [("risk_local_vs_pooled","#2a78d6","0–5-death targets",-0.018,"o"),
                          ("risk_local_vs_pooled_all_targets","#eb6834","All targets",0.018,"s")]:
    m=[s[key]["mean"]*1e3 for s in S]; lo=[s[key]["p2.5"]*1e3 for s in S]; hi=[s[key]["p97.5"]*1e3 for s in S]
    x=[v+dx for v in sig]
    a.errorbar(x,m,yerr=[[mm-l for mm,l in zip(m,lo)],[h-mm for mm,h in zip(m,hi)]],fmt=mk,ms=3.5,color=col,
               elinewidth=0.9,capsize=1.5,label=lab,markeredgecolor="white",markeredgewidth=0.5)
a.axhline(0,color="#8a8984",lw=0.6,zorder=0)
a.set_xlabel(r"Hospital prevalence SD $\sigma$ (logit)"); a.set_ylabel(r"$\Delta$ risk MSE ($\times10^{-3}$)")
a.set_xticks(sig); a.legend(frameon=False,fontsize=6,loc="lower left",handletextpad=0.2)
for sp in ("top","right"): a.spines[sp].set_visible(False); b.spines[sp].set_visible(False)
a.grid(axis="y",color="#e6e5df",lw=0.4)
h=[s["share_stratum_harmed_risk"]["mean"]*100 for s in S]
b.bar(sig,h,width=0.2,color="#2a78d6")
for x,v in zip(sig,h): b.text(x,v+1.5,f"{v:.0f}%",ha="center",fontsize=6)
b.set_xticks(sig); b.set_ylim(0,60); b.set_xlabel(r"$\sigma$"); b.set_ylabel("0–5-death hospitals\nharmed by pooling (%)")
b.grid(axis="y",color="#e6e5df",lw=0.4); b.set_axisbelow(True)
fig.savefig("fig_sim_boundary_v25.pdf"); fig.savefig("fig_sim_boundary_v25.png",dpi=250)
