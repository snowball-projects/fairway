"""The one-time course accounting must catch loss and reminted identities."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "audit", ROOT / "scripts/audit_migration.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_original_course_preservation_uses_committed_ids_not_array_order():
    old = [{"name": "North", "holes": 18}, {"name": "South", "holes": None}]
    current = [
        {"id": "south", "name": "South", "holes": None},
        {"id": "north", "name": "North", "holes": 18},
        {"id": "new", "name": "Retained additional course", "holes": None},
    ]
    audit.assert_original_courses(old, current, ["north", "south"])


@pytest.mark.parametrize(
    "defect", ["missing_trailing_course", "changed_id", "short_mapping"]
)
def test_course_accounting_rejects_loss_and_identity_changes(defect):
    old = [{"name": "North", "holes": 18}, {"name": "South", "holes": None}]
    current = [{"id": "north", **old[0]}, {"id": "south", **old[1]}]
    persisted = ["north", "south"]
    if defect == "missing_trailing_course":
        current.pop()
    elif defect == "changed_id":
        current[-1]["id"] = "reminted"
    else:
        persisted.pop()
    with pytest.raises(AssertionError):
        audit.assert_original_courses(old, current, persisted)
