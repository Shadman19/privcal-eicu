import json, glob
import numpy as np, pandas as pd
df = pd.DataFrame([json.load(open(f)) for f in sorted(glob.glob("cache/*.json"))])
cols = ["risk_local_vs_pooled","brier_local_vs_pooled","risk_local_vs_loho","brier_local_vs_loho",
        "risk_sourceiso_vs_pooled","risk_loho_vs_pooled","share_stratum_harmed_risk","risk_local_vs_pooled_all_targets"]
rows=[]
for sigma,g in df.groupby("sigma"):
    r={"sigma":sigma,"replicates":len(g),"replicates_empty_stratum":int((g.n_stratum==0).sum()),
       "mean_stratum_hospitals":round(g.n_stratum.mean(),2),"mean_targets":round(g.n_targets.mean(),1)}
    for c in cols:
        v=g[c].dropna()
        r[c]={"mean":float(v.mean()),"p2.5":float(np.percentile(v,2.5)),"p97.5":float(np.percentile(v,97.5)),
              "share_positive":float((v>0).mean()),"n":int(len(v))}
    rows.append(r)
fid={"max_he_loss_curve_err":float(df.he_err.max()),
     "max_rounded_count_err":int(df.fid_rounded_count_max_abs_error.max()),
     "max_rounded_death_err":int(df.fid_rounded_death_max_abs_error.max()),
     "max_score_sum_err":float(df.fid_decrypted_score_sum_max_abs_error.max()),
     "max_map_pred_err":float(df.fid_held_out_map_prediction_max_abs_error.max()),
     "total_map_preds_compared":int(df.fid_n_held_out_target_predictions_compared.sum()),
     "temperature_always_equal":bool(df.T_priv_equals_T_pool.all()),"runs":len(df)}
json.dump({"scenarios":rows,"ckks_fidelity":fid},open("simulation_summary_v25.json","w"),indent=2)
for r in rows:
    print(r["sigma"], r["replicates_empty_stratum"], r["mean_stratum_hospitals"],
          {k:(round(r[k]["mean"],4),round(r[k]["p2.5"],4),round(r[k]["p97.5"],4),round(r[k]["share_positive"],2)) for k in cols})
print(fid)
