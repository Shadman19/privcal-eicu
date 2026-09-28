"""Fail-closed timing and integrity verifier for the PrivCal eICU v9 lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SOURCE_SHA = "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75"
DIRECTIONAL = [
    "self_including_pooled_binned_isotonic_vs_source_platt_local_intercept",
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_regularized_local_intercept",
    "leave_one_target_hospital_out_pooled_binned_isotonic_vs_source_platt_local_intercept",
    "self_including_pooled_binned_isotonic_vs_source_only_binned_isotonic",
    "pooled_binned_isotonic_vs_pooled_temperature",
]
DIAGNOSTIC = "leave_one_target_hospital_out_pooled_binned_isotonic_vs_self_including_pooled_binned_isotonic"
PENALTIES = [0.5, 1.0, 2.0, 4.0, 8.0]


class LockError(ValueError):
    pass


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise LockError(f"{field} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LockError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise LockError(f"{field} must include UTC offset Z or +00:00")
    return parsed.astimezone(timezone.utc)


def load_lock(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if len(blocks) != 1:
        raise LockError("lock must contain exactly one fenced JSON object")
    try:
        lock = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise LockError("lock JSON is malformed") from exc
    if not isinstance(lock, dict):
        raise LockError("lock JSON must be an object")
    return lock, hashlib.sha256(raw).hexdigest()


def validate_approved_lock(lock: dict[str, object]) -> datetime:
    expected = {
        "schema_version": "privcal_eicu_v9_lock_v1",
        "study_id": "one_pooled_calibration_eicu",
        "analysis_role": "claim_forming",
        "status": "APPROVED",
    }
    for key, value in expected.items():
        if lock.get(key) != value:
            raise LockError(f"{key} must equal {value!r}")
    approval = _utc(lock.get("approval_utc"), "approval_utc")
    approvers = lock.get("approved_by")
    if not isinstance(approvers, list) or not approvers or not all(isinstance(x, str) and x.strip() for x in approvers):
        raise LockError("approved_by must contain at least one nonempty responsible-team identifier")
    auth = lock.get("authorizations")
    if not isinstance(auth, dict) or set(auth.values()) != {True} or len(auth) != 3:
        raise LockError("all three authorization attestations must be true")
    source = lock.get("frozen_source")
    if not isinstance(source, dict) or source.get("sha256") != SOURCE_SHA:
        raise LockError("frozen v9 source SHA-256 is missing or changed")
    primary = lock.get("primary_estimand")
    fixed = {
        "split_seed": 7, "backend": "tfidf_lr",
        "target_subset": "0-5 calibration deaths, inclusive",
        "unit": "target hospital", "aggregation": "hospital macro mean",
        "outcome_metric": "Brier score",
        "method": "self-including pooled 12-bin binned-isotonic map",
        "comparator": "fixed-penalty regularized local intercept",
        "contrast": "comparator Brier minus method Brier",
        "positive_contrast_favors": "pooled method",
        "bootstrap_resamples": 2000, "bootstrap_seed": 971,
        "confidence_interval": "paired hospital bootstrap percentile 95%",
    }
    if not isinstance(primary, dict) or any(primary.get(k) != v for k, v in fixed.items()):
        raise LockError("primary estimand differs from the locked specification")
    if lock.get("required_directional_controls") != DIRECTIONAL:
        raise LockError("directional control set or order differs from the lock")
    if lock.get("diagnostic_only_control") != DIAGNOSTIC:
        raise LockError("diagnostic-only control differs from the lock")
    penalties = lock.get("local_intercept_penalties")
    if not isinstance(penalties, list) or [float(x) for x in penalties] != PENALTIES:
        raise LockError("local-intercept penalty grid differs from the lock")
    return approval


def preflight(lock_path: Path, receipt_path: Path, now: datetime | None = None) -> dict[str, object]:
    lock, digest = load_lock(lock_path)
    approval = validate_approved_lock(lock)
    checked = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if approval > checked:
        raise LockError("approval_utc is later than preflight time")
    if receipt_path.exists():
        raise LockError(f"refusing to overwrite existing receipt: {receipt_path}")
    receipt = {
        "schema_version": "privcal_eicu_v9_lock_receipt_v1",
        "lock_sha256": digest,
        "approval_utc": approval.isoformat().replace("+00:00", "Z"),
        "preflight_utc": checked.isoformat().replace("+00:00", "Z"),
        "frozen_source_sha256": SOURCE_SHA,
        "approval_identifiers_exported": False,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def postrun(lock_path: Path, receipt_path: Path, audit_path: Path) -> None:
    lock, digest = load_lock(lock_path)
    approval = validate_approved_lock(lock)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != "privcal_eicu_v9_lock_receipt_v1" or receipt.get("lock_sha256") != digest:
        raise LockError("receipt does not match the unchanged approved lock")
    preflight_time = _utc(receipt.get("preflight_utc"), "receipt.preflight_utc")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    metadata = audit.get("run_metadata")
    if not isinstance(metadata, dict):
        raise LockError("v9 audit lacks run_metadata")
    started = _utc(metadata.get("run_started_utc"), "v9 audit.run_metadata.run_started_utc")
    if started < approval or started < preflight_time:
        raise LockError("v9 run started before final approval or verified preflight")
    if metadata.get("source_notebook_sha256") != SOURCE_SHA:
        raise LockError("v9 audit source hash does not match the approved frozen source")
    if str(metadata.get("pythonhashseed")) != "0":
        raise LockError("v9 audit did not record PYTHONHASHSEED=0")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    before = sub.add_parser("preflight")
    before.add_argument("--lock", required=True, type=Path)
    before.add_argument("--receipt", required=True, type=Path)
    after = sub.add_parser("postrun")
    after.add_argument("--lock", required=True, type=Path)
    after.add_argument("--receipt", required=True, type=Path)
    after.add_argument("--v9-audit", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        preflight(args.lock, args.receipt)
        print(f"Approved lock verified; internal receipt written to {args.receipt}")
    else:
        postrun(args.lock, args.receipt, args.v9_audit)
        print("Post-run timing, lock integrity, and pinned source hash verified")


if __name__ == "__main__":
    main()
