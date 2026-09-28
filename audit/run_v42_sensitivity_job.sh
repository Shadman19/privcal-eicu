#!/bin/bash
# Slurm job: reviewer-requested sensitivity analyses (discharge audit; unweighted base model). Aggregate-only.
#SBATCH --job-name=privcal_v42_sens
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=privcal_v42_sens_%j.log
set -euo pipefail
umask 077
export PYTHONHASHSEED=0 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
readonly PROJECT_DIR="${PRIVCAL_PROJECT_DIR:-/home/spath004/Small Language Model Project}"
readonly PY="${PRIVCAL_PYTHON_BIN:-/home/spath004/envs/hijack/bin/python}"
cd "${PROJECT_DIR}"
check() { [[ "$(sha256sum "$1" | awk '{print $1}')" == "$2" ]] || { echo "Hash mismatch: $1" >&2; exit 2; }; }
check PrivCal_eICU_reviewer_sensitivities_v9.ipynb 23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75
check stratum_calibration_v28a_codex.py           d060c18dd910aa1789486b01531bd1aad126c83171bfd692f8f4b3798fa03caf
check sensitivity_v42.py                          1205bf449983c2135a8437a343cddb2ffd1541f4f59006a8abf6f454b65b435d
mapfile -t OUTS < <(ls -d privcal_eicu_v9_verified_6849217_* 2>/dev/null)
[[ ${#OUTS[@]} -eq 1 ]] || { echo "Expected exactly one privcal_eicu_v9_verified_6849217_* folder" >&2; exit 2; }
OUT="${OUTS[0]}"
REL=release_review_20260927T161413Z
check "${REL}/aggregate_publication_audit_v9.json"          cac5f258ba95d17a3e0574c798dd36cbd0898a3f13e2e32a20d153425cfd56ad
check "${REL}/aggregate_calibration_diagnostics_seed7.json" 671d2bfbd8bae4c8fb9207c99f473188870cadc9ac18c862ea2efd8cd51cfa00
if [[ -f eicu/patient.csv.gz ]]; then PAT=eicu/patient.csv.gz; elif [[ -f eicu/patient.csv ]]; then PAT=eicu/patient.csv; else echo "Missing patient table" >&2; exit 2; fi
CAND="v42_sensitivity_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "${CAND}"
SCR="$(mktemp -d "${TMPDIR:-/tmp}/privcal_v42.XXXXXX")"
trap 'rm -rf "${SCR}"' EXIT
"${PY}" sensitivity_v42.py --outdir "${SCR}/rerun" --output "${CAND}/sensitivity_v42.json" --patient "${PAT}" \
  --primary-manifest "${OUT}/run_manifest.json" --primary-pairs "${OUT}/primary_brier_site_pairs.csv" \
  --approved-audit "${REL}/aggregate_publication_audit_v9.json" --approved-diagnostics "${REL}/aggregate_calibration_diagnostics_seed7.json"
(cd "${CAND}" && sha256sum *.json > CANDIDATE_SHA256SUMS.txt)
echo "Done: ${CAND}"; cat "${CAND}/CANDIDATE_SHA256SUMS.txt"
echo "Candidates for team and data-use review. Do not share logs, site IDs or patient rows."
