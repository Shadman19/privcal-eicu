#!/usr/bin/env python3
"""Branch and fail-closed tests for fill_results_v31.py on SYNTHETIC fixtures (not eICU).

Builds favorable / adverse / inconclusive variants, fills and compiles each PDF, checks the
wording and the page count, and checks that tampering or a missing control fails closed.
"""
import copy, hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIX = HERE / "synthetic_fixture_NOT_EICU"
sys.path.insert(0, str(ROOT))
import fill_results_v31 as F  # noqa: E402

def write(d: Path, J: dict) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, name in F.FILES.items():
        raw = (json.dumps(J[k], indent=2) + "\n").encode()
        (d / name).write_bytes(raw)
        lines.append(f"{hashlib.sha256(raw).hexdigest()}  {name}")
    (d / "APPROVED_SHA256SUMS.txt").write_text("\n".join(lines) + "\n")
    return d

def base() -> dict:
    return {k: json.loads((FIX / n).read_text()) for k, n in F.FILES.items()}

def set_primary(J, mean, ci, pooled_lower):
    for c in [J["audit"]["primary"]] + [c for c in J["audit"]["local_intercept_penalty_sensitivity"] if c["comparison"].endswith("_2")]:
        c["mean_comparator_minus_method_Brier"] = mean
        c["paired_hospital_bootstrap_95_CI"] = ci
    n = J["audit"]["primary"]["n_hospitals"]
    J["audit"]["primary"]["method_lower_Brier_hospitals"] = pooled_lower
    J["sites"]["pooled_lower_Brier_hospitals"] = pooled_lower
    J["sites"]["local_intercept_lower_Brier_hospitals"] = n - pooled_lower
    J["sites"]["exactly_tied_hospitals"] = 0

def set_ctrl(J, key, mean, ci):
    name = next(k for k, v in F.CONTROL.items() if v == key)
    c = next(c for c in J["audit"]["low_event_seed7_sensitivity"] if c["comparison"] == name)
    c["mean_comparator_minus_method_Brier"] = mean
    c["paired_hospital_bootstrap_95_CI"] = ci

def fill(d: Path, out: Path):
    return subprocess.run([sys.executable, str(ROOT / "fill_results_v31.py"), "--release", str(d),
                           "--manifest", str(d / "APPROVED_SHA256SUMS.txt"), "--out", str(out)],
                          capture_output=True, text=True)

def compile_pages(tex_dir: Path) -> int:
    for _ in range(2):
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "PrivCal_v31.tex"], cwd=tex_dir, capture_output=True)
    info = subprocess.run(["pdfinfo", "PrivCal_v31.pdf"], cwd=tex_dir, capture_output=True, text=True).stdout
    return int(next(l.split()[-1] for l in info.splitlines() if l.startswith("Pages")))

CASES = {
    "favorable_srcbin_inconclusive": (lambda J: None, ["had lower mean Brier score than the local intercept", "interval included zero"], "favors pooling"),
    "favorable_srcbin_favorable": (lambda J: set_ctrl(J, "srcbin", 0.004, [0.001, 0.007]), ["also had lower mean Brier score than the source-only"], "favors pooling"),
    "adverse": (lambda J: set_primary(J, -0.012, [-0.020, -0.004], 3), ["the local intercept had lower mean Brier score than the pooled map", "had lower mean Brier score than pooled calibration"], "favors the comparator"),
    "inconclusive": (lambda J: set_primary(J, 0.002, [-0.004, 0.008], 6), ["but the interval included zero", "was inconclusive"], "inconclusive"),
}

def main():
    ok = True
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        for name, (mod, phrases, want) in CASES.items():
            J = base(); mod(J)
            d = write(t / name, J)
            texd = t / (name + "_tex"); texd.mkdir()
            for f in ("PrivCal_v31.tex", "IEEEtran.cls", "fig_sim_boundary_v25.pdf"):
                shutil.copy(ROOT / f, texd)
            r = fill(d, texd / "results_v31.tex")
            if r.returncode != 0 or want not in r.stdout:
                print("FAIL", name, r.stdout, r.stderr); ok = False; continue
            txt = (texd / "results_v31.tex").read_text()
            miss = [p for p in phrases if p not in txt]
            if name != "favorable_srcbin_favorable" and "gain over the local intercept" in txt:
                miss.append("forbidden: gain over the local intercept")
            pages = compile_pages(texd)
            status = "ok" if not miss and pages <= 8 else "FAIL"
            ok &= status == "ok"
            print(f"{status} {name}: pages={pages} missing={miss}")
            if name == "adverse":
                shutil.copy(texd / "PrivCal_v31.pdf", HERE / "SYNTHETIC_branch_adverse.pdf")
        # fail-closed checks
        J = base(); J["audit"]["low_event_seed7_sensitivity"] = [c for c in J["audit"]["low_event_seed7_sensitivity"] if "vs_source_platt" not in c["comparison"] or "self_including" in c["comparison"]]
        r = fill(write(t / "missing_ctrl", J), t / "x.tex"); ok &= r.returncode != 0; print("ok" if r.returncode else "FAIL", "missing LOTO-vs-Platt control rejected")
        d = write(t / "tamper", base()); p = d / F.FILES["sites"]; p.write_text(p.read_text().replace('"n_hospitals": 11', '"n_hospitals": 11 '))
        r = fill(d, t / "y.tex"); ok &= r.returncode != 0 and "approved bytes" in r.stderr; print("ok" if r.returncode else "FAIL", "tampered bytes rejected")
        J = base(); set_primary(J, -0.001, [0.002, 0.009], 9)
        r = fill(write(t / "sign", J), t / "z.tex"); ok &= r.returncode != 0; print("ok" if r.returncode else "FAIL", "mean/interval sign disagreement rejected")
    print("ALL PASS" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
