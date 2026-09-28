import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from verify_v9_analysis_lock import LockError, load_lock, postrun, preflight


HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "V9_ANALYSIS_LOCK_AND_AUTHORIZATION.md"


def approved_text(approval="2026-09-24T10:00:00Z"):
    text = TEMPLATE.read_text(encoding="utf-8")
    return (text.replace('"status": "PENDING"', '"status": "APPROVED"')
                .replace('"approval_utc": null', f'"approval_utc": "{approval}"')
                .replace('"approved_by": []', '"approved_by": ["responsible-team-member"]')
                .replace('"analysis_plan_reviewed": false', '"analysis_plan_reviewed": true')
                .replace('"data_use_and_aggregate_release_reviewed": false', '"data_use_and_aggregate_release_reviewed": true')
                .replace('"authorship_and_oversight_owner_identified": false', '"authorship_and_oversight_owner_identified": true'))


class LockTests(unittest.TestCase):
    def test_template_fails_pending(self):
        lock, _ = load_lock(TEMPLATE)
        with self.assertRaises(LockError):
            from verify_v9_analysis_lock import validate_approved_lock
            validate_approved_lock(lock)

    def test_preflight_and_postrun_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); lock = root / "lock.md"; receipt = root / "receipt.json"; audit = root / "audit.json"
            lock.write_text(approved_text(), encoding="utf-8")
            preflight(lock, receipt, datetime(2026, 9, 24, 10, 1, tzinfo=timezone.utc))
            audit.write_text(json.dumps({"run_metadata": {
                "run_started_utc": "2026-09-24T10:02:00Z",
                "source_notebook_sha256": "23d0ca0666fd68e040bd6a39d6e3361b2ba0c0502b39cc01f88cfa4baa807b75",
                "pythonhashseed": 0}}), encoding="utf-8")
            postrun(lock, receipt, audit)

    def test_late_approval_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); lock = root / "lock.md"; receipt = root / "receipt.json"
            lock.write_text(approved_text("2026-09-24T10:05:00Z"), encoding="utf-8")
            with self.assertRaises(LockError):
                preflight(lock, receipt, datetime(2026, 9, 24, 10, 1, tzinfo=timezone.utc))

    def test_changed_lock_fails_postrun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); lock = root / "lock.md"; receipt = root / "receipt.json"; audit = root / "audit.json"
            lock.write_text(approved_text(), encoding="utf-8")
            preflight(lock, receipt, datetime(2026, 9, 24, 10, 1, tzinfo=timezone.utc))
            lock.write_text(lock.read_text().replace("hospital macro mean", "patient pooled mean"), encoding="utf-8")
            audit.write_text(json.dumps({"run_metadata": {"run_started_utc": "2026-09-24T10:02:00Z"}}), encoding="utf-8")
            with self.assertRaises(LockError):
                postrun(lock, receipt, audit)


if __name__ == "__main__":
    unittest.main()
