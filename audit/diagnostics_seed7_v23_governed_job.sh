#!/bin/bash
# INTERNAL ONLY: authorized eICU host; run after the genuinely approved v9 job.
# This wrapper replaces the v11 diagnostics_seed7_job.sh, which launches
# run_diagnostics_seed7.py and omits the v23 small-cell reporting fixes.
#SBATCH --job-name=privcal_diag_v23
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=privcal_diag_v23_%j.log

set -euo pipefail
umask 077
export PYTHONHASHSEED=0
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
export MKL_NUM_THREADS=4
export TOKENIZERS_PARALLELISM=false

readonly PROJECT_DIR="${PRIVCAL_PROJECT_DIR:-/home/spath004/Small Language Model Project}"
readonly PYTHON_BIN="${PRIVCAL_PYTHON_BIN:-/home/spath004/envs/hijack/bin/python}"
readonly NOTEBOOK="PrivCal_eICU_reviewer_sensitivities_v9.ipynb"
readonly DIAGNOSTIC="run_diagnostics_seed7_v23.py"
readonly EXPECTED_NOTEBOOK_SHA256="23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
readonly EXPECTED_DIAGNOSTIC_SHA256="d501afc6d7a76ac1fe306b966b8e37d4f2e798e601a18c19ff83b0687c997ab2"

# These paths must be set by the responsible team to the real, existing
# pre-run v11b lock, receipt, and completed v9 aggregate on this host.
: "${PRIVCAL_V9_LOCK:?Set PRIVCAL_V9_LOCK to the genuine approved lock path}"
: "${PRIVCAL_V9_RECEIPT:?Set PRIVCAL_V9_RECEIPT to the pre-run receipt path}"
: "${PRIVCAL_V9_AUDIT:?Set PRIVCAL_V9_AUDIT to the completed restricted v9 audit path}"

cd "${PROJECT_DIR}"
for required in "${PYTHON_BIN}" "${NOTEBOOK}" "${DIAGNOSTIC}" \
                "verify_v9_analysis_lock.py" "${PRIVCAL_V9_LOCK}" \
                "${PRIVCAL_V9_RECEIPT}" "${PRIVCAL_V9_AUDIT}"; do
  if [[ ! -r "${required}" ]]; then
    echo "Missing required authorized-host input: ${required}" >&2
    exit 2
  fi
done

actual_notebook_sha256="$(sha256sum "${NOTEBOOK}" | awk '{print $1}')"
actual_diagnostic_sha256="$(sha256sum "${DIAGNOSTIC}" | awk '{print $1}')"
if [[ "${actual_notebook_sha256}" != "${EXPECTED_NOTEBOOK_SHA256}" ||
      "${actual_diagnostic_sha256}" != "${EXPECTED_DIAGNOSTIC_SHA256}" ]]; then
  echo "Frozen v9 notebook or v23 diagnostic hash differs from the reviewed source." >&2
  exit 2
fi

"${PYTHON_BIN}" verify_v9_analysis_lock.py postrun \
  --lock "${PRIVCAL_V9_LOCK}" \
  --receipt "${PRIVCAL_V9_RECEIPT}" \
  --v9-audit "${PRIVCAL_V9_AUDIT}"

export PRIVCAL_OUTDIR="./privcal_eicu_diag_v23_${SLURM_JOB_ID:-manual}_$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -e "${PRIVCAL_OUTDIR}" ]]; then
  echo "Refusing to overwrite an existing diagnostic directory." >&2
  exit 2
fi
"${PYTHON_BIN}" -u "${DIAGNOSTIC}"
echo "Supplementary seed-7 diagnostic finished on the authorized host."
