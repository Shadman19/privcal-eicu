#!/usr/bin/env python3
"""Adversarial tests for cohort_characteristics_v40.build on synthetic data (no eICU records)."""
import numpy as np
import pandas as pd
import cohort_characteristics_v40 as C

W = "withheld_small_cell"


def make(unit_by_site, deaths_calib, n_per_site=60, extra_sites=0, seed=0):
    """unit_by_site: {site: list of (unittype, count)}; deaths_calib: {target site: calibration deaths}."""
    rng = np.random.default_rng(seed)
    rows, pid = [], 0
    for site, spec in unit_by_site.items():
        for unit, k in spec:
            for _ in range(k):
                rows.append({"patientunitstayid": pid, "site": site, "label": int(rng.random() < 0.3),
                             "unittype": unit}); pid += 1
    data = pd.DataFrame(rows)
    patient = pd.DataFrame({"patientunitstayid": data.patientunitstayid,
                            "age": rng.integers(20, 95, len(data)).astype(str),
                            "gender": rng.choice(["Female", "Male"], len(data)),
                            "unittype": data.unittype, "unitstaytype": "admit"})
    data = data.drop(columns="unittype")
    data["text"] = "diagnosis: sepsis treatment: antibiotics fluids"
    target = list(deaths_calib)
    sites = list(unit_by_site)
    parts = {s: {"y_calib": np.array([1] * deaths_calib[s] + [0] * 5), "y_test": np.array([0, 1])} for s in target}
    return {"data": data, "SITES": sites}, {"parts": parts, "TARGET": target}, patient


def check_invariants(rep):
    g = rep["groups"]
    for comp in ("vital_status", "age_recorded", "sex", "unittype", "unitstaytype"):
        cats = set().union(*(g[k][comp].keys() for k in g))
        for cat in cats:
            states = {g[k][comp].get(cat, 0) == W for k in g if cat in g[k][comp]}
            assert len(states) == 1, f"{comp}/{cat} withheld in some columns but not others"
        for k in g:
            vals = g[k][comp]
            nw = sum(v == W for v in vals.values())
            assert nw != 1, f"{k}/{comp}: a single withheld cell is recoverable from the stay total"
            if nw == 0:
                assert sum(vals.values()) == g[k]["stays"]
            for v in vals.values():
                assert v == W or v == 0 or v >= C.MIN_CELL


def base():
    # 3 source, 4 target (2 with 0-5 calibration deaths); each site 60 stays.
    u = {f"s{i}": [("micu", 40), ("sicu", 20)] for i in range(3)}
    u.update({f"t{i}": [("micu", 40), ("sicu", 20)] for i in range(4)})
    return u, {"t0": 2, "t1": 5, "t2": 9, "t3": 12}


def test_no_primary_stratum_column():
    u, d = base()
    rep = C.build(*make(u, d))
    assert set(rep["groups"]) == {"all_stays", "source_hospitals", "target_hospitals"}
    print("ok   public table has only all / source / target columns")


def test_small_in_target_only():
    u, d = base()
    u["t0"].append(("cticu", 10)); u["s1"].append(("cticu", 40))
    rep = C.build(*make(u, d))
    g = rep["groups"]
    assert all(g[k]["unittype"]["cticu"] == W for k in g)
    check_invariants(rep)
    print("ok   category small in target only is withheld in all three columns plus a complement")


def test_small_only_in_source():
    u, d = base()
    u["s0"].append(("nicu", 5)); u["t1"].append(("nicu", 30))
    rep = C.build(*make(u, d))
    g = rep["groups"]
    assert all(g[k]["unittype"]["nicu"] == W for k in g if "nicu" in g[k]["unittype"])
    check_invariants(rep)
    print("ok   category small in source only is withheld in all, source and target columns")


def test_no_suppression_when_all_large():
    u, d = base()
    rep = C.build(*make(u, d))
    check_invariants(rep)
    assert rep["groups"]["all_stays"]["unittype"] == {"micu": 280, "sicu": 140}
    print("ok   nothing withheld when every linked cell is >= MIN_CELL; compositions sum to stays")


def test_refuse_small_implied_group():
    u, d = base()
    u["x0"] = [("micu", 12)]          # stays in a site that is neither source nor target
    scope, res, pt = make(u, d)
    scope["SITES"] = [s for s in scope["SITES"] if s != "x0"]
    try:
        C.build(scope, res, pt)
    except RuntimeError as e:
        assert "refuse" in str(e); print("ok   refuses when an implied group has 1-19 stays"); return
    raise AssertionError("did not refuse")


def test_primary_set_mismatch_refused():
    u, d = base()
    try:
        C.build(*make(u, d), primary_sites={"t0", "t2"})
    except RuntimeError as e:
        assert "primary hospital set" in str(e); print("ok   refuses when the 0-5 hospital set differs from the primary pairs"); return
    raise AssertionError("did not refuse")


def test_primary_set_match_ok():
    u, d = base()
    rep = C.build(*make(u, d), primary_sites={"t0", "t1"})
    assert rep["primary_hospital_set_verified"] is True
    print("ok   accepts the exact primary hospital set")


def test_join_refuses_unmatched_and_duplicates():
    u, d = base()
    scope, res, pt = make(u, d)
    for bad, msg in ((pt.iloc[1:], "without a patient-table row"),
                     (pd.concat([pt, pt.iloc[:1]]), "duplicated")):
        try:
            C.build(scope, res, bad)
        except RuntimeError as e:
            assert msg in str(e)
        else:
            raise AssertionError(msg)
    print("ok   join refuses unmatched stays and duplicated patient rows")


def fake_approved(scope, res, rep_all):
    data = scope["data"]
    import copy
    y = [np.asarray(res["parts"][s]["y_test"]) for s in res["TARGET"]]
    return {"audit": {"run_metadata": {"rows": len(data), "sites": data.site.nunique()}, "primary": {"n_hospitals": 2}},
            "diag": {"unit_types": {"denominator_selected_stays": len(data),
                                    "selected_hospital_deaths": int(data.label.sum()),
                                    "fields": {"unittype": {"categories": copy.deepcopy(rep_all["unittype"])},
                                               "unitstaytype": {"categories": copy.deepcopy(rep_all["unitstaytype"])}}},
                     "target_seed7_methods": {"m": {"n_target_hospitals": len(res["TARGET"]),
                                                    "n_test_stays": int(sum(len(v) for v in y)),
                                                    "n_test_deaths": int(sum(v.sum() for v in y))}}}}


def test_reconciliation():
    u, d = base()
    scope, res, pt = make(u, d)
    for s in res["TARGET"]:
        res["parts"][s]["y_test"] = np.array([0, 1, 0])
    rep = C.build(scope, res, pt)
    ap = fake_approved(scope, res, rep["groups"]["all_stays"])
    ok = C.build(scope, res, pt, approved=ap)
    assert ok["reconciled_with_approved_v9_results"] is True
    for path, val in ((("audit", "run_metadata", "rows"), 1), (("diag", "unit_types", "selected_hospital_deaths"), 1)):
        import copy
        bad = copy.deepcopy(ap); o = bad
        for k in path[:-1]:
            o = o[k]
        o[path[-1]] += val
        try:
            C.build(scope, res, pt, approved=bad)
        except RuntimeError as e:
            assert "reconciliation failed" in str(e)
        else:
            raise AssertionError(path)
    bad = copy.deepcopy(ap); bad["diag"]["target_seed7_methods"]["m"]["n_test_deaths"] += 1
    try:
        C.build(scope, res, pt, approved=bad)
    except RuntimeError:
        pass
    else:
        raise AssertionError("test deaths")
    print("ok   reconciliation passes on matching totals and refuses stays, deaths or test-death mismatches")


def test_age_top_code():
    u, d = base()
    scope, res, pt = make(u, d)
    pt["age"] = "> 89"
    rep = C.build(scope, res, pt)
    a = rep["groups"]["all_stays"]
    assert a["age_years_median_q1_q3"] == ["90+", "90+", "90+"]
    assert a["age_recorded"]["top_coded_90_plus"] == a["stays"]
    print("ok   '> 89' is counted as top-coded 90+ and quartiles show '90+'")


def hand_table(src, tgt, stays_s, stays_t):
    """Three-column table for one composition 'unittype' with every listed cell withheld where marked."""
    allv = {k: src[k] + tgt[k] for k in src}
    def col(v, st, wh):
        return {"stays": st, "unittype": {k: (W if k in wh else v[k]) for k in v}, "_raw": {"unittype": v}}
    return col, allv


def test_recoverability_detects_tight_range():
    src, tgt = {"a": 5, "b": 10, "c": 0}, {"a": 30, "b": 40, "c": 100}
    col, allv = hand_table(src, tgt, 15, 170)
    wh = {"a", "b"}
    table = {"all_stays": col(allv, 185, wh), "source_hospitals": col(src, 15, wh), "target_hospitals": col(tgt, 170, wh)}
    try:
        C.recoverability_check(table, 0, {})
    except RuntimeError as e:
        assert "recoverable" in str(e)
    else:
        raise AssertionError("tight range not detected")
    print("ok   recoverability check refuses a small cell pinned to a narrow range")


def test_recoverability_detects_public_totals():
    # Without public totals the withheld pair is protected; the approved all-column counts pin it down.
    src, tgt = {"a": 5, "b": 300, "c": 400}, {"a": 30, "b": 0, "c": 500}
    col, allv = hand_table(src, tgt, 705, 530)
    wh = {"a", "b"}
    table = {"all_stays": col(allv, 1235, wh), "source_hospitals": col(src, 705, wh), "target_hospitals": col(tgt, 530, wh)}
    C.recoverability_check(table, 0, {})
    try:
        C.recoverability_check(table, 0, {"unittype": {"a": 35, "b": 300}})
    except RuntimeError as e:
        assert "recoverable" in str(e)
    else:
        raise AssertionError("public totals not used")
    print("ok   recoverability check uses already-public all-stays counts (b=0 in target exposes a)")


def test_weakened_suppression_is_repaired():
    u, d = base()
    u["s0"].append(("nicu", 5)); u["t1"].append(("nicu", 30))
    orig = C.linked_suppression
    try:
        def no_complement(raw, linked):
            out = orig(raw, linked)
            out["unittype"] = {"nicu"}
            return out
        C.linked_suppression = no_complement
        rep = C.build(*make(u, d))
    finally:
        C.linked_suppression = orig
    g = rep["groups"]
    assert all(sum(v == W for v in g[k]["unittype"].values()) >= 2 for k in g)
    check_invariants(rep)
    print("ok   if complementary suppression is removed, the LP check forces extra suppression before output")


def test_approved_bytes_required():
    import tempfile, json as js, hashlib
    from pathlib import Path
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "x.json"; f.write_text(js.dumps({"a": 1}))
        good = {"aggregate_publication_audit_v9.json": hashlib.sha256(f.read_bytes()).hexdigest()}
        assert C.load_approved(f, "aggregate_publication_audit_v9.json", good) == {"a": 1}
        try:
            C.load_approved(f, "aggregate_publication_audit_v9.json")
        except RuntimeError as e:
            assert "SHA-256 mismatch" in str(e)
        else:
            raise AssertionError("unapproved bytes accepted")
    assert C.APPROVED_SHA256["aggregate_publication_audit_v9.json"].startswith("cac5f258")
    assert C.APPROVED_SHA256["aggregate_calibration_diagnostics_seed7.json"].startswith("671d2bfb")
    print("ok   approved audit and diagnostics must match the approved SHA-256 manifest")


def test_fuzz():
    rng = np.random.default_rng(11)
    ok = refused = 0
    for it in range(40):
        u, d = base()
        for cat in ("nicu", "cticu", "picu"):
            for s in rng.choice(list(u), size=rng.integers(1, 4), replace=False):
                u[s].append((cat, int(rng.integers(1, 40))))
        try:
            rep = C.build(*make(u, d, seed=it)); check_invariants(rep); ok += 1
        except RuntimeError as e:
            assert "cannot be protected" in str(e) or "refuse" in str(e), str(e); refused += 1
    assert ok > 0
    print(f"ok   fuzz: {ok} random tables passed every invariant and the linear screen, {refused} refused (small group or unprotectable)")


def test_mortality_percent_follows_vital_status():
    u, d = base()
    rep = C.build(*make(u, d, seed=3))
    for k, v in rep["groups"].items():
        has = "hospital_mortality_percent" in v
        assert has == (v["vital_status"]["died_in_hospital"] != W), k
    print("ok   mortality percent released only with both vital-status cells")


if __name__ == "__main__":
    for f in (test_no_primary_stratum_column, test_small_in_target_only, test_small_only_in_source,
              test_no_suppression_when_all_large, test_refuse_small_implied_group, test_primary_set_mismatch_refused,
              test_primary_set_match_ok, test_join_refuses_unmatched_and_duplicates, test_reconciliation,
              test_age_top_code, test_mortality_percent_follows_vital_status, test_recoverability_detects_tight_range,
              test_recoverability_detects_public_totals, test_weakened_suppression_is_repaired,
              test_approved_bytes_required, test_fuzz):
        f()
    print("ALL PASS")
