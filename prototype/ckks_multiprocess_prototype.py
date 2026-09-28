#!/usr/bin/env python3
"""Separate-process CKKS prototype for pooled 12-bin recalibration (synthetic data only).

Roles run in separate OS processes and exchange only serialized bytes:
  * key custodian: creates the CKKS context and the only secret key; publishes a public context
    (no secret key); later decrypts the single aggregate it receives.
  * hospitals (worker processes, each encrypting its own hospitals' vectors): receive only the
    public context; encrypt five vectors per hospital, exactly as in the frozen analysis:
    96 temperature-loss terms, 1 calibration count, and 12-bin counts, deaths and score sums.
  * aggregator: receives only the public context and the hospitals' ciphertexts; adds them;
    verifies that it cannot decrypt; forwards the summed ciphertexts to the custodian.
Parameters match the frozen notebook: poly modulus degree 8192, coefficient moduli 60/40/40/60,
scale 2^40.

Measured: per-hospital encryption time and ciphertext bytes (hospital to aggregator), aggregation
time, bytes aggregator to custodian, decryption time, and agreement of the decrypted aggregate and
of the resulting pooled isotonic map with a plaintext computation (test harness only; in a
deployment no party would see all plaintext vectors). This is a prototype on one machine: it does
not measure network latency and does not address collusion, malicious inputs or differencing.
"""
from __future__ import annotations
import json, os, sys, time, platform, statistics
import multiprocessing as mp
import numpy as np

POLY, COEFF, SCALE_BITS = 8192, [60, 40, 40, 60], 40
NBINS, NTEMP = 12, 96
TEMPS = np.linspace(0.25, 5.0, NTEMP)


def make_context(secret: bool):
    import tenseal as ts
    ctx = ts.context(ts.SCHEME_TYPE.CKKS, poly_modulus_degree=POLY, coeff_mod_bit_sizes=COEFF)
    ctx.global_scale = 2 ** SCALE_BITS
    return ctx


def hospital_vectors(seed: int) -> dict:
    """Synthetic calibration summaries for one hospital (no real data)."""
    r = np.random.default_rng(seed)
    n = int(np.clip(r.lognormal(np.log(450), 0.7), 130, 3000)) // 4          # calibration rows (25%)
    a = np.log(0.09 / 0.91) + 0.5 * r.normal()
    x = r.normal(size=n)
    p_true = 1 / (1 + np.exp(-(a + 1.5 * x)))
    y = (r.random(n) < p_true).astype(float)
    z = 1.2 * x + 0.8 + r.normal(scale=0.5, size=n)                             # over-predicting model logit
    p = 1 / (1 + np.exp(-z))
    b = np.minimum((p * NBINS).astype(int), NBINS - 1)
    cnt = np.bincount(b, minlength=NBINS).astype(float)
    dth = np.bincount(b, weights=y, minlength=NBINS)
    ssum = np.bincount(b, weights=p, minlength=NBINS)
    loss = np.array([np.sum(-(y * np.log(np.clip(1 / (1 + np.exp(-z / T)), 1e-12, 1))
                              + (1 - y) * np.log(np.clip(1 - 1 / (1 + np.exp(-z / T)), 1e-12, 1)))) for T in TEMPS])
    return {"loss": loss, "n": np.array([float(n)]), "cnt": cnt, "dth": dth, "ssum": ssum}


def custodian(conn_pub_out, conn_agg_in, conn_result_out):
    import tenseal as ts
    ctx = make_context(True)
    pub_bytes = ctx.serialize(save_secret_key=False)          # as in the frozen notebook
    for c in conn_pub_out:
        c.send_bytes(pub_bytes)
    msg = conn_agg_in.recv()                                   # dict name -> bytes
    t0 = time.perf_counter()
    out = {k: np.array(ts.ckks_vector_from(ctx, v).decrypt()) for k, v in msg["sums"].items()}
    t_dec = time.perf_counter() - t0
    conn_result_out.send({"decrypted": {k: v.tolist() for k, v in out.items()}, "t_decrypt_s": t_dec,
                          "public_context_bytes": len(pub_bytes)})


def hospital_worker(conn_pub_in, conn_to_agg, seeds):
    import tenseal as ts
    pub = ts.context_from(conn_pub_in.recv_bytes())
    assert not pub.is_private(), "hospital received a secret key"
    rec = []
    for s in seeds:
        v = hospital_vectors(s)
        t0 = time.perf_counter()
        enc = {k: ts.ckks_vector(pub, val.tolist()).serialize() for k, val in v.items()}
        t = time.perf_counter() - t0
        rec.append({"seed": s, "t_encrypt_s": t, "bytes": sum(len(b) for b in enc.values()),
                    "ct": enc, "plain": {k: val.tolist() for k, val in v.items()}})
    conn_to_agg.send(rec)


def aggregator(conn_pub_in, conns_from_hosp, conn_to_cust, conn_report):
    import tenseal as ts
    pub = ts.context_from(conn_pub_in.recv_bytes())
    assert not pub.is_private(), "aggregator received a secret key"
    recs = []
    for c in conns_from_hosp:
        recs.extend(c.recv())
    t0 = time.perf_counter()
    acc = {}
    for r in recs:
        for k, b in r["ct"].items():
            v = ts.ckks_vector_from(pub, b)
            acc[k] = v if k not in acc else acc[k] + v
    t_agg = time.perf_counter() - t0
    try:                                                        # the aggregator must not be able to decrypt
        acc["cnt"].decrypt(); can_decrypt = True
    except Exception:
        can_decrypt = False
    sums = {k: v.serialize() for k, v in acc.items()}
    conn_to_cust.send({"sums": sums})
    conn_report.send({"t_aggregate_s": t_agg, "aggregator_can_decrypt": can_decrypt,
                      "bytes_to_custodian": sum(len(b) for b in sums.values()),
                      "per_hospital": [{"t_encrypt_s": r["t_encrypt_s"], "bytes": r["bytes"]} for r in recs],
                      "plain_sum": {k: np.sum([r["plain"][k] for r in recs], axis=0).tolist() for k in recs[0]["plain"]}})


def pooled_map(cnt, dth, ssum):
    from sklearn.isotonic import IsotonicRegression
    keep = np.round(cnt) > 0
    x, y, w = ssum[keep] / cnt[keep], dth[keep] / cnt[keep], cnt[keep]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(x, y, sample_weight=w)
    grid = np.linspace(0.0005, 0.9995, 1000)
    return iso.predict(grid)


def run_once(H: int, n_workers: int = 2, base_seed: int = 1000):
    ctx = mp.get_context("spawn")
    pub_pairs = [ctx.Pipe(duplex=False) for _ in range(n_workers + 1)]      # custodian -> workers, aggregator
    h2a = [ctx.Pipe(duplex=False) for _ in range(n_workers)]
    a2c, c2r, a2r = ctx.Pipe(duplex=False), ctx.Pipe(duplex=False), ctx.Pipe(duplex=False)
    seeds = [base_seed + i for i in range(H)]
    chunks = [seeds[i::n_workers] for i in range(n_workers)]
    procs = [ctx.Process(target=custodian, args=([p[1] for p in pub_pairs], a2c[0], c2r[1]))]
    procs += [ctx.Process(target=hospital_worker, args=(pub_pairs[i][0], h2a[i][1], chunks[i])) for i in range(n_workers)]
    procs += [ctx.Process(target=aggregator, args=(pub_pairs[-1][0], [c[0] for c in h2a], a2c[1], a2r[1]))]
    t0 = time.perf_counter()
    for p in procs: p.start()
    agg = a2r[0].recv(); cust = c2r[0].recv()
    for p in procs: p.join()
    wall = time.perf_counter() - t0
    dec = {k: np.array(v) for k, v in cust["decrypted"].items()}
    plain = {k: np.array(v) for k, v in agg["plain_sum"].items()}
    L = {"loss": NTEMP, "n": 1, "cnt": NBINS, "dth": NBINS, "ssum": NBINS}
    err = {k: float(np.max(np.abs(dec[k][:L[k]] - plain[k]))) for k in plain}
    rounded_exact = bool(np.all(np.round(dec["cnt"][:NBINS]) == plain["cnt"]) and np.all(np.round(dec["dth"][:NBINS]) == plain["dth"]))
    t_idx_enc = int(np.argmin(dec["loss"][:NTEMP])); t_idx_plain = int(np.argmin(plain["loss"]))
    m_enc = pooled_map(np.round(dec["cnt"][:NBINS]), np.round(dec["dth"][:NBINS]), dec["ssum"][:NBINS])
    m_pln = pooled_map(plain["cnt"], plain["dth"], plain["ssum"])
    ph = agg["per_hospital"]
    return {"H": H, "wall_s": wall,
            "encrypt_s_per_hospital_median": statistics.median(r["t_encrypt_s"] for r in ph),
            "encrypt_s_per_hospital_max": max(r["t_encrypt_s"] for r in ph),
            "bytes_per_hospital": ph[0]["bytes"], "bytes_per_hospital_all_equal": len({r["bytes"] for r in ph}) == 1,
            "aggregate_s": agg["t_aggregate_s"], "bytes_aggregator_to_custodian": agg["bytes_to_custodian"],
            "decrypt_s": cust["t_decrypt_s"], "public_context_bytes": cust["public_context_bytes"],
            "aggregator_can_decrypt": agg["aggregator_can_decrypt"],
            "max_abs_error": err, "rounded_counts_deaths_exact": rounded_exact,
            "temperature_choice_equal": t_idx_enc == t_idx_plain,
            "pooled_map_max_abs_diff": float(np.max(np.abs(m_enc - m_pln)))}


if __name__ == "__main__":
    Hs = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else "10,50,139,250".split(","))]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    import tenseal
    res = {"purpose": "separate-process CKKS prototype, synthetic hospitals only",
           "params": {"poly_modulus_degree": POLY, "coeff_mod_bit_sizes": COEFF, "scale_bits": SCALE_BITS,
                      "vectors_per_hospital": {"loss": NTEMP, "n": 1, "cnt": NBINS, "dth": NBINS, "ssum": NBINS}},
           "environment": {"python": platform.python_version(), "tenseal": tenseal.__version__,
                           "cpu": platform.processor() or platform.machine(), "cpus": os.cpu_count()},
           "runs": []}
    for H in Hs:
        for rep in range(reps):
            r = run_once(H, base_seed=1000 + 10000 * rep)
            r["rep"] = rep
            res["runs"].append(r)
            print(json.dumps({k: r[k] for k in ("H", "rep", "wall_s", "encrypt_s_per_hospital_median", "bytes_per_hospital",
                                                  "aggregate_s", "decrypt_s", "aggregator_can_decrypt",
                                                  "rounded_counts_deaths_exact", "temperature_choice_equal", "pooled_map_max_abs_diff")}), flush=True)
    json.dump(res, open("ckks_prototype_results.json", "w"), indent=2)
