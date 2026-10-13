"""Portable replay must publish truthful, reproducible intake history."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/kansas-rural-20261013/apply_delta.py"


@pytest.fixture
def replay(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("kansas_replay", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    delta = json.loads(SCRIPT.with_name("delta.json").read_text())
    added_ids = {f["id"] for f in delta["added_facilities"]}
    before = script.catalog.read()
    before["facilities"] = [f for f in before["facilities"] if f["id"] not in added_ids]
    for facility_id in added_ids:
        before["research"].pop(facility_id)
    for batch in before["history"]["batches"]:
        batch["added_facilities"] = [
            f for f in batch["added_facilities"] if f.get("id") not in added_ids
        ]
        batch["facilities_added"] = len(batch["added_facilities"]) + batch.get(
            "redacted_entries", 0
        )
    input_path = tmp_path / "before.json"
    input_path.write_bytes(script.catalog.encoded(before))
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Replay test",
            "-c",
            "user.email=replay@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "Evidence fixture",
        ],
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-01-01T08:15:00-06:00",
            "GIT_COMMITTER_DATE": "2026-01-01T08:15:00-06:00",
        },
    )
    commit = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    output = tmp_path / "proposal.json"
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--catalog",
            str(input_path),
            "--output",
            str(output),
            "--evidence-commit",
            commit,
        ],
    )
    script.main()
    proposal = script.catalog.read(output)
    return before, proposal, script.catalog.exports(proposal), commit


def test_replay_uses_actual_git_commit_time(replay):
    _, proposal, exported, commit = replay
    batch = next(b for b in proposal["history"]["batches"] if b["commit"] == commit)
    assert batch["committed_at"] == "2026-01-01T14:15:00Z"
    assert batch["reported_at"] != batch["committed_at"]
    published = next(
        b
        for b in exported["catalog-additions.json"]["batches"]
        if b["commit"] == commit
    )
    assert published["committed_at"] == batch["committed_at"]


def test_replay_publishes_latest_report_first(replay):
    before, proposal, exported, commit = replay
    assert proposal["progress"]["report_commits"] == [
        commit,
        *before["progress"]["report_commits"],
    ]
    assert exported["research-progress.json"]["recent_batches"][0]["commit"] == commit


def test_replay_publishes_known_zero_updates(replay):
    before, proposal, exported, commit = replay
    original = {f["id"]: f for f in before["facilities"]}
    assert all(
        original[f["id"]] == f for f in proposal["facilities"] if f["id"] in original
    )
    published = next(
        b
        for b in exported["research-progress.json"]["recent_batches"]
        if b["commit"] == commit
    )
    assert published["facilities_added"] == 3
    assert published["facilities_updated"] == 0
