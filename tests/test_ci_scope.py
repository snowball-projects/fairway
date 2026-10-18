"""Production paths and uncertain diffs must retain their verification coverage."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.ci_scope import changed_paths, select

RELEASE = [
    "data/catalog-release/manifest.json",
    "data/catalog-release/catalog.json.gz",
    "data/README.md",
    "docs/catalog/RELEASE981.md",
    "CHANGELOG.md",
    "tests/test_catalog_foundation.py",
]


def test_catalog_only_preserves_facts_without_claiming_api_or_package_tests():
    assert select(RELEASE) == {
        "scope": "catalog",
        "app": False,
        "archive_both": False,
        "snapshot": False,
        "experiment": False,
    }


@pytest.mark.parametrize(
    "path",
    [
        "src/fairway/static/app.js",
        "src/fairway/static/public-catalog.mjs",
        "src/fairway/static/public-planning.mjs",
        "src/fairway/catalog_native.py",
        "src/fairway/catalog_native_export.py",
        "src/fairway/catalog_schema/native.sql",
        "scripts/build_pages.py",
    ],
)
def test_runtime_mixed_with_catalog_data_runs_both_python_behavior_suites(path):
    result = select([*RELEASE[:2], path])
    assert result["app"] and result["scope"] == "runtime"


@pytest.mark.parametrize("path", ["MANIFEST.in", "README.md", "LICENSE"])
def test_package_changes_require_archive_tests_on_both_python_versions(path):
    result = select([path])
    assert result["scope"] == "packaging"
    assert result["app"] and result["archive_both"]


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock"])
def test_dependency_changes_also_validate_real_snapshot_and_both_archives(path):
    result = select([path])
    assert result["scope"] == "dependencies"
    assert result["app"] and result["archive_both"] and result["snapshot"]


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "scripts/ci_scope.py",
        "tests/test_ci_scope.py",
        "tests/test_catalog_foundation.py",
        "tests/public-catalog.test.mjs",
        "tests/new-test.py",
        "other/docs/catalog/RELEASE981.md",
        "new-config.toml",
        "docs/catalog/RELEASE981.md",
    ],
)
def test_unknown_workflow_and_test_only_paths_cannot_take_catalog_shortcut(path):
    result = select([path])
    assert result["scope"] == "full"
    assert all(result[k] for k in ("app", "archive_both", "snapshot", "experiment"))


def test_unrecognized_test_mixed_with_release_requires_full_integration():
    assert select([*RELEASE, "tests/public-catalog.test.mjs"])["scope"] == "full"


@pytest.mark.parametrize(
    "path",
    [
        "src/fairway/matrix.py",
        "scripts/build_course_index.py",
        "src/fairway/data/snapshots.json",
    ],
)
def test_road_inputs_select_exhaustive_real_index_validation(path):
    assert select([path])["snapshot"]


def test_experiment_only_has_its_own_tests_without_claiming_api_integration():
    result = select(["experiments/catalog-expansion/src/main.mjs"])
    assert result["experiment"] and not result["app"]


def test_missing_or_empty_diff_fails_safe_to_full_integration():
    for base in (None, "0" * 40):
        paths, uncertain = changed_paths(base, "HEAD")
        assert select(paths, uncertain=uncertain)["scope"] == "full"
    assert select([])["scope"] == "full"


def test_real_git_rename_retains_removed_runtime_path_and_nul_names(
    tmp_path, monkeypatch
):
    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=tmp_path, stderr=subprocess.DEVNULL
        )

    git("init")
    source = tmp_path / "src/fairway/old\nmodule.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.test",
        "commit",
        "-m",
        "base",
    )
    base = git("rev-parse", "HEAD").decode().strip()
    destination = tmp_path / "data/catalog-release/new.json"
    destination.parent.mkdir(parents=True)
    source.rename(destination)
    git("add", "-A")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.test",
        "commit",
        "-m",
        "move",
    )
    monkeypatch.chdir(tmp_path)
    paths, uncertain = changed_paths(base, "HEAD")
    assert not uncertain and "src/fairway/old\nmodule.py" in paths
    assert select(paths)["app"]
    paths, uncertain = changed_paths("missing-base", "HEAD")
    assert uncertain and select(paths, uncertain=uncertain)["scope"] == "full"


def test_cli_reports_actual_scope_without_exposing_paths_in_github_outputs(tmp_path):
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    script = Path(__file__).resolve().parents[1] / "scripts/ci_scope.py"
    completed = subprocess.run(
        [os.sys.executable, str(script), "--base", "0" * 40],
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["scope"] == "full"
    assert "app=true\n" in output.read_text() and "scope=full\n" in output.read_text()
    assert "Selected verification" in summary.read_text()
