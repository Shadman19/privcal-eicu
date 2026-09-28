#!/usr/bin/env python3
"""PrivCal v25 supplementary simulation (synthetic data only; see SIMULATION_PROTOCOL_v25.md).

Runs the frozen v9 seed-7 experiment function, unmodified apart from the pinned v23
in-memory return instrumentation, on synthetic hospitals with known true risks.
Results are cached per replicate in JSON so an interrupted run resumes.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
V9 = HERE / "PrivCal_eICU_reviewer_sensitivities_v9.ipynb"
V9_SHA = "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
sys.path.insert(0, str(HERE))
from run_diagnostics_seed7_v23 import encrypted_plaintext_fidelity, instrument_return  # noqa: E402

SIGMAS = [0.0, 0.35, 0.7, 1.0]
R = int(os.environ.get("SIM_R", 40))
H, VOCAB = 60, 300
CACHE = HERE / "cache"


def frozen_scope() -> dict:
    raw = V9.read_bytes()
    if hashlib.sha256(raw).hexdigest() != V9_SHA:
        raise RuntimeError("Frozen v9 notebook hash mismatch")
    src = "\n".join("".join(c["source"]) for c in json.loads(raw)["cells"] if c["cell_type"] == "code")
    cut = lambda a, b: src[src.index(a):src.index(b)]
    imports = cut("import os, re, json", "# ----------------------------------------------------------------"
                  "----------------------------\n# 2. Configuration")
    cfg = cut("CFG = dict(", 'if os.environ.get("PYTHONHASHSEED")')
    ckks_helpers = cut("# 3. Required CKKS arithmetic", "# 5. Load eICU")
    experiments = cut("# 6. BioClinicalBERT", "# 8. Figure generation")
    experiments = instrument_return(experiments)
    old = "return dict(parts=parts,"
    assert experiments.count(old) == 1
    experiments = experiments.replace(old, "return dict(loho_maps=loho_maps, iso_source=iso_source, parts=parts,")
    scope = {"__name__": "privcal_sim"}
    for block in (imports, "DEFAULT_EICU=''\n" + cfg, ckks_helpers):
        exec(compile(block, str(V9), "exec"), scope)
    scope["CFG"]["outdir"] = str(HERE / "unused_outdir")
    exec(compile(experiments, str(V9), "exec"), scope)
    return scope


def make_world(sigma: float, seed: int):
    rng = np.random.default_rng(seed)
    sizes = np.clip(np.round(np.exp(rng.normal(np.log(450), 0.8, H))), 130, 3000).astype(int)
    a = np.log(0.09 / 0.91) + sigma * rng.normal(size=H)
    w = rng.normal(size=VOCAB)
    rows, pid = [], 0
    for h in range(H):
        d = rng.normal(0, 0.3, VOCAB)
        x = rng.normal(size=sizes[h])
        p = 1 / (1 + np.exp(-(a[h] + 1.5 * x)))
        y = rng.binomial(1, p)
        present = rng.random((sizes[h], VOCAB)) < 1 / (1 + np.exp(-(-3 + 0.8 * np.outer(x, w) + d)))
        for i in range(sizes[h]):
            toks = " ".join(f"dx{k:03d}" for k in np.flatnonzero(present[i]))
            rows.append((pid, f"hospital_{h:02d}", f"diagnosis: icu admission monitoring {toks}", int(y[i]), float(p[i])))
            pid += 1
    df = pd.DataFrame(rows, columns=["patientunitstayid", "site", "text", "label", "p_true"])
    df["row_id"] = np.arange(len(df))
    return df


def one_replicate(scope: dict, sigma: float, seed: int) -> dict:
    world = make_world(sigma, seed)
    scope["data"] = world[["row_id", "patientunitstayid", "site", "text", "label"]].copy()
    scope["SITES"] = sorted(world["site"].unique())
    res = scope["run_one_split"]("tfidf_lr", 7, make_figures=False)
    parts, T_src = res["parts"], res["T_src"]
    sig, fri = scope["sigmoid"], scope["fit_regularized_intercept"]
    ptrue = world.set_index("row_id")["p_true"]
    rows = []
    for s in res["TARGET"]:
        pc = parts[s]
        deaths = int(pc["y_calib"].sum())
        truth = ptrue.loc[pc["test"]["row_id"].values].to_numpy()
        y = pc["y_test"]
        z = pc["logit_test"]
        off = fri(pc["logit_calib"] / T_src, pc["y_calib"], 2.0)
        preds = {
            "local": sig(z / T_src + off),
            "pooled": res["predict_fn"]("PrivCal-B (secure-agg isotonic)", s, "test"),
            "loho": res["loho_maps"][s].predict(sig(z)),
            "source_iso": res["iso_source"].predict(sig(z)),
        }
        rec = {"deaths": deaths, "n_test": int(len(y))}
        for k, p in preds.items():
            rec[f"mse_{k}"] = float(np.mean((p - truth) ** 2))
            rec[f"brier_{k}"] = float(np.mean((p - y) ** 2))
        rows.append(rec)
    t = pd.DataFrame(rows)
    st = t[t.deaths <= 5]
    out = {"sigma": sigma, "seed": seed, "n_targets": int(len(t)), "n_stratum": int(len(st)),
           "he_err": float(res["he_err"]), "T_priv_equals_T_pool": bool(res["T_priv"] == res["T_pool"])}
    out.update({f"fid_{k}": v for k, v in encrypted_plaintext_fidelity(res, scope).items() if k != "scope"})
    if len(st):
        for name, a, b in [("risk_local_vs_pooled", "mse_local", "mse_pooled"),
                           ("brier_local_vs_pooled", "brier_local", "brier_pooled"),
                           ("risk_local_vs_loho", "mse_local", "mse_loho"),
                           ("brier_local_vs_loho", "brier_local", "brier_loho"),
                           ("risk_sourceiso_vs_pooled", "mse_source_iso", "mse_pooled"),
                           ("risk_loho_vs_pooled", "mse_loho", "mse_pooled")]:
            out[name] = float((st[a] - st[b]).mean())
        out["share_stratum_harmed_risk"] = float(((st.mse_local - st.mse_pooled) < 0).mean())
        # Full target set, for context (descriptive).
        out["risk_local_vs_pooled_all_targets"] = float((t.mse_local - t.mse_pooled).mean())
    return out


def main() -> None:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    CACHE.mkdir(exist_ok=True)
    scope = frozen_scope()
    only = os.environ.get("SIM_ONLY")  # e.g. "0:0" for a timing test
    for k, sigma in enumerate(SIGMAS):
        for r in range(R):
            if only and only != f"{k}:{r}":
                continue
            f = CACHE / f"s{k}_r{r:02d}.json"
            if f.exists():
                continue
            t0 = time.time()
            out = one_replicate(scope, sigma, 1000 * k + r)
            out["seconds"] = round(time.time() - t0, 1)
            f.write_text(json.dumps(out))
            print(f"sigma={sigma} r={r} stratum={out['n_stratum']} "
                  f"dRisk={out.get('risk_local_vs_pooled')} {out['seconds']}s", flush=True)


if __name__ == "__main__":
    main()
