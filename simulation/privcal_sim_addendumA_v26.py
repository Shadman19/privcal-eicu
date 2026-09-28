#!/usr/bin/env python3
"""Post hoc addendum A (see SIMULATION_ADDENDUM_A_v26.md): systematic source-target shift."""
import json, os, time
from pathlib import Path
import numpy as np
import privcal_sim_v25 as base

SOURCE = {"hospital_00","hospital_04","hospital_06","hospital_10","hospital_12","hospital_16",
          "hospital_19","hospital_20","hospital_22","hospital_24","hospital_26","hospital_28",
          "hospital_32","hospital_36","hospital_37","hospital_47","hospital_53","hospital_54",
          "hospital_57","hospital_59"}
DELTAS = [-0.7, 0.7]
SIGMA = 0.35
CACHE = Path(__file__).resolve().parent / "cache_addendumA"

def make_world_shift(delta):
    def mw(sigma, seed):
        rng = np.random.default_rng(seed)
        sizes = np.clip(np.round(np.exp(rng.normal(np.log(450), 0.8, base.H))), 130, 3000).astype(int)
        a = np.log(0.09 / 0.91) + sigma * rng.normal(size=base.H)
        for h in range(base.H):
            if f"hospital_{h:02d}" not in SOURCE:
                a[h] += delta
        w = rng.normal(size=base.VOCAB)
        rows, pid = [], 0
        for h in range(base.H):
            d = rng.normal(0, 0.3, base.VOCAB)
            x = rng.normal(size=sizes[h])
            p = 1 / (1 + np.exp(-(a[h] + 1.5 * x)))
            y = rng.binomial(1, p)
            present = rng.random((sizes[h], base.VOCAB)) < 1 / (1 + np.exp(-(-3 + 0.8 * np.outer(x, w) + d)))
            for i in range(sizes[h]):
                toks = " ".join(f"dx{k:03d}" for k in np.flatnonzero(present[i]))
                rows.append((pid, f"hospital_{h:02d}", f"diagnosis: icu admission monitoring {toks}", int(y[i]), float(p[i])))
                pid += 1
        import pandas as pd
        df = pd.DataFrame(rows, columns=["patientunitstayid", "site", "text", "label", "p_true"])
        df["row_id"] = np.arange(len(df))
        return df
    return mw

def main():
    os.environ.setdefault("PYTHONHASHSEED", "0")
    CACHE.mkdir(exist_ok=True)
    scope = base.frozen_scope()
    orig = scope["run_one_split"]
    def checked(*a, **k):
        res = orig(*a, **k)
        assert set(res["SOURCE"]) == SOURCE, "source set differs from the pre-declared one"
        return res
    scope["run_one_split"] = checked
    for j, delta in enumerate(DELTAS):
        base.make_world = make_world_shift(delta)
        for r in range(base.R):
            f = CACHE / f"d{j}_r{r:02d}.json"
            if f.exists():
                continue
            t0 = time.time()
            out = base.one_replicate(scope, SIGMA, 5000 + 1000 * j + r)
            out["delta"] = delta
            out["seconds"] = round(time.time() - t0, 1)
            f.write_text(json.dumps(out))
            print(f"delta={delta} r={r} stratum={out['n_stratum']} dRisk={out.get('risk_local_vs_pooled')} srcIso-pooled={out.get('risk_sourceiso_vs_pooled')}", flush=True)

if __name__ == "__main__":
    main()
