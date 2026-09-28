"""Host-side aggregate audit of stay promotion in the frozen v9 loader (v24).

Internal, supplementary. The frozen v9 loader drops rows missing
``unitvisitnumber`` or ``unitdischargeoffset`` *before* keeping one stay per
``uniquepid``. If a patient's earliest-ordered stay lacks
``unitdischargeoffset``, a later stay is "promoted" into the cohort. This
script replays the v9 selection rule on the restricted patient table and
reports aggregate counts only. It does not change the frozen v9 notebook or
its cohort. Downstream v9 filters (24-hour text window, >20 characters of
text, >=120 records per hospital) are not replayed here; counts refer to the
selected-stay, outcome-present, 24-hour-landmark stage.

Counts from 1 to 19 are replaced by "<20". This is a reporting rule, not a
formal disclosure guarantee; a responsible team member must approve any
release under the eICU data-use terms.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

STAY, PID, HOSP = "patientunitstayid", "uniquepid", "hospitalid"
VISIT, UDIS, STATUS = "unitvisitnumber", "unitdischargeoffset", "hospitaldischargestatus"
LANDMARK_MIN = 1440
MIN_CELL = 20


def _mask(count: int):
    return count if count == 0 or count >= MIN_CELL else f"<{MIN_CELL}"


def v9_selected(pat: pd.DataFrame) -> pd.DataFrame:
    """Replay the frozen v9 selection exactly (loader lines before text merge)."""
    p = pat[[STAY, PID, HOSP, VISIT, STATUS, UDIS]].dropna(subset=[STAY, PID, HOSP]).copy()
    for col in (VISIT, UDIS):
        p[col] = pd.to_numeric(p[col], errors="coerce")
    p = p.dropna(subset=[VISIT, UDIS])
    return p.sort_values([PID, VISIT, STAY]).drop_duplicates(PID)


def promotion_audit(pat: pd.DataFrame) -> dict:
    missing = {STAY, PID, HOSP, VISIT, STATUS, UDIS} - set(pat.columns)
    if missing:
        raise ValueError(f"Patient table lacks fields: {sorted(missing)}")
    if pat[STAY].duplicated().any():
        raise ValueError("Repeated patientunitstayid")

    selected = v9_selected(pat)
    base = pat[[STAY, PID, HOSP, VISIT, UDIS]].dropna(subset=[STAY, PID, HOSP]).copy()
    for col in (VISIT, UDIS):
        base[col] = pd.to_numeric(base[col], errors="coerce")
    ambiguous = base.loc[base[VISIT].isna(), PID].unique()
    ordered = base.dropna(subset=[VISIT])
    first = ordered.sort_values([PID, VISIT, STAY]).drop_duplicates(PID)[[PID, STAY]]
    cmp = selected[[PID, STAY, STATUS, UDIS]].merge(
        first.rename(columns={STAY: "first_ordered_stay"}), on=PID, how="left", validate="one_to_one")
    promoted = cmp[cmp[STAY] != cmp["first_ordered_stay"]]
    in_cohort = promoted[promoted[STATUS].notna() & (promoted[UDIS] >= LANDMARK_MIN)]

    final = selected.dropna(subset=[STATUS])
    final = final[final[UDIS] >= LANDMARK_MIN]
    return {
        "purpose": "supplementary aggregate cohort audit; frozen v9 cohort unchanged",
        "stage": "selected stay, outcome present, unit stay >= 1440 min (before text and hospital-size filters)",
        "patients_with_v9_selected_stay": _mask(int(len(selected))),
        "patients_at_landmark_stage": _mask(int(len(final))),
        "patients_promoted_past_stay_missing_unit_discharge_offset": _mask(int(len(promoted))),
        "promoted_patients_at_landmark_stage": _mask(int(len(in_cohort))),
        "patients_with_any_stay_missing_unit_visit_number_order_ambiguous": _mask(int(len(ambiguous))),
        "suppression_rule": f"counts 1-{MIN_CELL - 1} reported as '<{MIN_CELL}'; not a formal privacy guarantee",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--patient", type=Path, required=True,
                        help="restricted eICU patient.csv[.gz] on the authorized host")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    pat = pd.read_csv(args.patient, low_memory=False)
    pat.columns = pat.columns.str.lower()
    args.output.write_text(json.dumps(promotion_audit(pat), indent=2) + "\n")
    print(f"Aggregate saved on authorized host (release requires human approval): {args.output}")


if __name__ == "__main__":
    main()
