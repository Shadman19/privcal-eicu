#!/bin/bash
# Run only on authorized eICU host; execute frozen v9 notebook without changing v7.
#SBATCH --job-name=privcal_eicu_verified_review
#SBATCH --time=08:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=privcal_eicu_verified_%j.log

set -euo pipefail
umask 077
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
export MKL_NUM_THREADS=4
export TOKENIZERS_PARALLELISM=false
export PYTHONHASHSEED=0

readonly PROJECT_DIR="/home/spath004/Small Language Model Project"
readonly PYTHON_BIN="/home/spath004/envs/hijack/bin/python"
readonly NOTEBOOK="PrivCal_eICU_reviewer_sensitivities_v9.ipynb"
readonly EXPECTED_SHA256="23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
readonly RUN_ID="${SLURM_JOB_ID:-manual}_$(date -u +%Y%m%dT%H%M%SZ)"

cd "${PROJECT_DIR}"
actual_sha256="$(sha256sum "${NOTEBOOK}" | awk '{print $1}')"
if [[ "${actual_sha256}" != "${EXPECTED_SHA256}" ]]; then
  echo "Unexpected v9 notebook hash: ${actual_sha256}; use the frozen verified source package." >&2
  exit 2
fi
export PRIVCAL_NOTEBOOK_SHA256="${actual_sha256}"
export PRIVCAL_OUTDIR="./privcal_eicu_v9_verified_${RUN_ID}"
if [[ -e "${PRIVCAL_OUTDIR}" ]]; then
  echo "Refusing to overwrite ${PRIVCAL_OUTDIR}" >&2
  exit 2
fi

echo "Started $(date -u +%Y-%m-%dT%H:%M:%SZ); results stay on authorized host."
"${PYTHON_BIN}" -u - "${NOTEBOOK}" <<'PY'
import json
import sys
from pathlib import Path
notebook = Path(sys.argv[1])
source = "\n".join("".join(cell["source"]) for cell in
                   json.loads(notebook.read_text())["cells"] if cell["cell_type"] == "code")
exec(compile(source, str(notebook), "exec"), {"__name__": "__main__"})
PY

"${PYTHON_BIN}" audit_publication_results_v9.py \
    --input "${PRIVCAL_OUTDIR}" \
    --output "${PRIVCAL_OUTDIR}/aggregate_publication_audit_v9.json" \
    --require-v9-sensitivities
"${PYTHON_BIN}" audit_robustness_aggregates_v10.py \
    --input "${PRIVCAL_OUTDIR}" \
    --base-audit "${PRIVCAL_OUTDIR}/aggregate_publication_audit_v9.json" \
    --output "${PRIVCAL_OUTDIR}/aggregate_review_tables_v10.json"
echo "Finished $(date -u +%Y-%m-%dT%H:%M:%SZ). Review aggregate JSONs under the data-use terms."
