#!/bin/bash
# INTERNAL ONLY. v29 = Codex v28a patch (reviewed and tested by Claude) + a final non-JSON guard.
# Run on Wahab by an authorized team member AFTER the v11b-governed v9 job succeeds.
# It never changes the v9 output. It writes aggregate-only JSON files into a new
# release_review_<time>/ folder for YOUR review before anything leaves Wahab.
#SBATCH --job-name=privcal_post_v29
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=privcal_post_v29_%j.log
set -euo pipefail
umask 077
export PYTHONHASHSEED=0 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4

readonly PROJECT_DIR="${PRIVCAL_PROJECT_DIR:-/home/spath004/Small Language Model Project}"
readonly PY="${PRIVCAL_PYTHON_BIN:-/home/spath004/envs/hijack/bin/python}"
: "${PRIVCAL_V9_OUT:?Set PRIVCAL_V9_OUT to the finished v9 output directory}"
: "${PRIVCAL_V9_LOCK:?Set PRIVCAL_V9_LOCK to your approved v11b lock file}"
: "${PRIVCAL_V9_RECEIPT:?Set PRIVCAL_V9_RECEIPT to the v11b pre-run receipt}"
: "${PRIVCAL_V9_AUDIT:?Set PRIVCAL_V9_AUDIT to the audit JSON the v11 job already wrote}"

cd "${PROJECT_DIR}"
check() { [[ "$(sha256sum "$1" | awk '{print $1}')" == "$2" ]] || { echo "Hash mismatch: $1" >&2; exit 2; }; }
check PrivCal_eICU_reviewer_sensitivities_v9.ipynb 23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75
check audit_publication_results_v9.py            1e3126e2a580e464c0c1336b7f41a697f608b4626e1f8cbb807c93abc97c6eb3
check run_diagnostics_seed7_v23.py               d501afc6d7a76ac1fe306b966b8e37d4f2e798e601a18c19ff83b0687c997ab2
check reconcile_v9_site_rows_v21.py              1a735ce1b4b4a0d9e9c529b3852a2484e4cfb25ce6074f79203943a30fca9eaf
check primary_site_summary_v24.py                e31f08dbda545904b3c586c83b085117c685e0d1bdf31db956b971ac3887bb50
check stay_promotion_audit_v24.py                e0bc9274980f8c628d467a4a6b9ac7022db3fbede1b527d18896f1f140fca87f
check diagnostics_seed7_v23_governed_job.sh      3283b29b2c60a833b6117b64ea19ec640040c0068fcdcfbc9f4cc1411c2ef765
check stratum_calibration_v28a_codex.py           d060c18dd910aa1789486b01531bd1aad126c83171bfd692f8f4b3798fa03caf
[[ -r verify_v9_analysis_lock.py ]] || { echo "Install verify_v9_analysis_lock.py from the v11b package first" >&2; exit 2; }
[[ "${PRIVCAL_V9_AUDIT}" == "${PRIVCAL_V9_OUT%/}/aggregate_publication_audit_v9.json" ]] || {
  echo "Audit path must point inside the exact selected v9 output directory." >&2; exit 2;
}

# The governance gate runs before preparing any review files.
"${PY}" verify_v9_analysis_lock.py postrun --lock "${PRIVCAL_V9_LOCK}" \
  --receipt "${PRIVCAL_V9_RECEIPT}" --v9-audit "${PRIVCAL_V9_AUDIT}"

REL="release_review_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "${REL}"

# 1. Keep the v11 job's own audit untouched. Re-run the pinned auditor into a separate
#    file and require byte-identical output (a consistency check, never an overwrite).
cp "${PRIVCAL_V9_AUDIT}" "${REL}/aggregate_publication_audit_v9.json"
"${PY}" audit_publication_results_v9.py --input "${PRIVCAL_V9_OUT}" \
  --output "${REL}/.reaudit_check.json" --require-v9-sensitivities
cmp "${REL}/.reaudit_check.json" "${PRIVCAL_V9_AUDIT}" || { echo "Re-audit differs from the v11 job audit; stop and review." >&2; exit 2; }
rm "${REL}/.reaudit_check.json"

# 2. v21 hospital-row reconciliation.
"${PY}" reconcile_v9_site_rows_v21.py --input "${PRIVCAL_V9_OUT}" \
  --output "${REL}/site_row_reconciliation_v21.json"

# 3. v24 counts: pooled-lower / local-lower / tied, and sign-flip deletions.
"${PY}" primary_site_summary_v24.py --input "${PRIVCAL_V9_OUT}/primary_brier_site_pairs.csv" \
  --output "${REL}/primary_site_summary_v24.json"

# 4. v24 stay-promotion audit (reads the restricted patient table; writes counts only).
# Never use an ls pipeline here: under pipefail it exits when only one file exists.
if [[ -f eicu/patient.csv.gz ]]; then
  PAT=eicu/patient.csv.gz
elif [[ -f eicu/patient.csv ]]; then
  PAT=eicu/patient.csv
else
  echo "Missing eicu/patient.csv.gz and eicu/patient.csv" >&2; exit 2
fi
"${PY}" stay_promotion_audit_v24.py --patient "${PAT}" --output "${REL}/stay_promotion_audit_v24.json"

# 5. v23 seed-7 diagnostic through the reviewed v23a wrapper. It runs inline here
#    (not a second sbatch), so this script waits for it to finish before collecting.
shopt -s nullglob
before=(privcal_eicu_diag_v23_*)
bash diagnostics_seed7_v23_governed_job.sh
after=(privcal_eicu_diag_v23_*)
new_dirs=()
for d in "${after[@]}"; do
  seen=0; for b in "${before[@]}"; do [[ "$d" == "$b" ]] && seen=1; done
  (( seen )) || new_dirs+=("$d")
done
if (( ${#new_dirs[@]} != 1 )); then
  echo "Expected exactly one new diagnostic directory, found ${#new_dirs[@]}; stop and review." >&2; exit 2
fi
DIAG="${new_dirs[0]}"
[[ -s "${DIAG}/aggregate_calibration_diagnostics_seed7.json" ]] || { echo "Diagnostic output missing in ${DIAG}" >&2; exit 2; }
# Its restricted provenance is reviewed on this host against the original v9 run.
# Never copy either input fingerprint object into the transferable review folder.
"${PY}" - "${PRIVCAL_V9_OUT}/run_manifest.json" \
  "${DIAG}/restricted_input_provenance_do_not_transfer.json" <<'PY'
import json, sys
from pathlib import Path
main = json.loads(Path(sys.argv[1]).read_text())
diag = json.loads(Path(sys.argv[2]).read_text())
if main.get('input_fingerprints') != diag.get('input_fingerprints'):
    raise SystemExit('Primary and diagnostic eICU input fingerprints differ; stop on host')
if main.get('source_notebook_sha256') != diag.get('notebook_sha256'):
    raise SystemExit('Primary and diagnostic notebook hashes differ; stop on host')
if main.get('software_versions') != diag.get('software_versions'):
    raise SystemExit('Primary and diagnostic software versions differ; stop on host')
PY
cp "${DIAG}/aggregate_calibration_diagnostics_seed7.json" "${REL}/"

# 6. The frozen loader writes a restricted per-hospital site_summary.csv on rerun.
# Keep its scratch directory outside release_review, and remove it even on error.
STRATUM_TMP="$(mktemp -d "${PROJECT_DIR}/.privcal_stratum_v28a_${SLURM_JOB_ID:-manual}_XXXXXXXX")"
cleanup_stratum_tmp() {
  if [[ -n "${STRATUM_TMP:-}" && -d "${STRATUM_TMP}" ]]; then
    "${PY}" - "${STRATUM_TMP}" <<'PY'
from pathlib import Path
import shutil, sys
root = Path(sys.argv[1])
if not root.name.startswith('.privcal_stratum_v28a_') or root.is_symlink():
    raise SystemExit('Refusing to remove an unexpected scratch directory')
shutil.rmtree(root)
PY
  fi
}
trap cleanup_stratum_tmp EXIT
"${PY}" stratum_calibration_v28a_codex.py --outdir "${STRATUM_TMP}/v9_rerun" \
  --primary-pairs "${PRIVCAL_V9_OUT}/primary_brier_site_pairs.csv" \
  --primary-manifest "${PRIVCAL_V9_OUT}/run_manifest.json" \
  --output "${REL}/stratum_calibration_v27.json"

# Require every entry under the review folder to be a regular JSON file.
# No grep -q pipeline: early pipe closure under pipefail can mask a match.
unexpected="$(find "${REL}" -mindepth 1 \( ! -type f -o ! -name '*.json' \) -print -quit)" || {
  echo "Unable to inspect ${REL}; do not release, review on host." >&2; exit 2
}
if [[ -n "${unexpected}" ]]; then
  echo "Non-JSON file found in ${REL}; do not release, review on host." >&2; exit 2
fi
echo
echo "Done. Aggregate-only files for YOUR review are in: ${PROJECT_DIR}/${REL}"
ls -la "${REL}"
echo "Check them for small cells before sharing. Never share patient rows, site IDs, logs,"
echo "the lock/receipt, or restricted_input_provenance_do_not_transfer.json."
echo "Only an explicitly approved, exact aggregate JSON may leave Wahab."
