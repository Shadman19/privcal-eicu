"""Adversarial and rule tests for make_v10_publication_extract.py (synthetic inputs only)."""
import copy, json, sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import make_v10_publication_extract as X

SRC = Path(sys.argv[1])
base = json.loads(SRC.read_text())
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("ok  " if cond else "FAIL"), name)

out = X.extract(copy.deepcopy(base), "x")
check("only all-target and 0-5 groups released", {c["group"] for c in out["split_contrasts"]} == {"all target hospitals", "0-5 calibration deaths"})
check("no median/IQR/win counts", not any(k in c for c in out["split_contrasts"] for k in ("median_comparator_minus_method_Brier", "IQR_comparator_minus_method_Brier", "method_lower_Brier_hospitals")))
# every released pair implies a complement group of >= MIN_GROUP hospitals
by = {}
for c in out["split_contrasts"]:
    by.setdefault(c["split_seed"], {})[c["group"]] = c
for s, g in by.items():
    if g["all target hospitals"]["released"]:
        N, n = g["all target hospitals"]["n_hospitals"], g["0-5 calibration deaths"]["n_hospitals"]
        check(f"split {s}: 0-5 group and complement both >= {X.MIN_GROUP} ({n}, {N-n})", n >= X.MIN_GROUP and N - n >= X.MIN_GROUP)
# small 0-5 stratum -> whole split withheld
j = copy.deepcopy(base)
for r in j["five_correlated_split_strata"]:
    if r["split_seed"] == 11 and r["stratum"] == X.LOW: r["n_target_hospitals"] = 7
o = X.extract(j, "x")
check("split with 0-5 n=7 withheld entirely", all(not c["released"] for c in o["split_contrasts"] if c["split_seed"] == 11))
# small complement -> withheld
j = copy.deepcopy(base)
for r in j["five_correlated_split_strata"]:
    if r["split_seed"] == 17 and r["stratum"] == X.ALL:
        low = next(x for x in j["five_correlated_split_strata"] if x["split_seed"] == 17 and x["stratum"] == X.LOW)
        r["n_target_hospitals"] = low["n_target_hospitals"] + 4
o = X.extract(j, "x")
check("split with complement 4 withheld entirely", all(not c["released"] for c in o["split_contrasts"] if c["split_seed"] == 17))
# primary mismatch -> refuse
j = copy.deepcopy(base); j["primary"]["mean_comparator_minus_method_Brier"] += 1e-6
try:
    X.extract(j, "x"); check("primary mismatch refused", False)
except SystemExit:
    check("primary mismatch refused", True)
# metric with 1-9 invalid hospitals -> banded denominator; <10 valid -> withheld
j = copy.deepcopy(base); m = j["target_method_macro_metrics"][0]; m["n_valid_AUROC"] = m["n_target_hospitals"] - 3
o = X.extract(j, "x")
check("AUROC denominator banded when 3 invalid", isinstance(o["all_target_macro_metrics"][0]["n_valid_AUROC"], str))
j = copy.deepcopy(base); m = j["target_method_macro_metrics"][0]; m["n_valid_ECE"] = 6
o = X.extract(j, "x")
check("ECE withheld when only 6 valid", o["all_target_macro_metrics"][0]["macro_ECE"] == "withheld")
o = X.extract(copy.deepcopy(base), "x", copy.deepcopy(base["primary"]))
s7 = next(c for c in o["split_contrasts"] if c["split_seed"] == 7 and c["group"] == "0-5 calibration deaths")
check("seed-7 0-5 uses locked primary interval and seed", s7["paired_hospital_bootstrap_95_CI"] == base["primary"]["paired_hospital_bootstrap_95_CI"] and s7["bootstrap_seed"] == base["primary"]["bootstrap_seed"])
bad = copy.deepcopy(base["primary"]); bad["paired_hospital_bootstrap_95_CI"] = [0, 1]
try:
    X.extract(copy.deepcopy(base), "x", bad); check("approved-primary CI mismatch refused", False)
except SystemExit:
    check("approved-primary CI mismatch refused", True)
import tempfile, hashlib
with tempfile.TemporaryDirectory() as t:
    f = Path(t) / "audit.json"; f.write_text(json.dumps({"primary": base["primary"]}))
    try:
        X.load_approved_primary(f); check("unapproved audit bytes refused", False)
    except SystemExit:
        check("unapproved audit bytes refused", True)
    check("approved audit bytes accepted", X.load_approved_primary(f, hashlib.sha256(f.read_bytes()).hexdigest()) == base["primary"])
check("approved audit hash pinned", X.APPROVED_AUDIT_SHA256.startswith("cac5f258"))
print("ALL PASS" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
