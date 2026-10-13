"""Bundle preparation/injection regressions; no Docker, downloads or installs."""

import hashlib
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE = (
    Path(__file__).resolve().parents[1] / "ops/private-national-api/review-fixture"
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE))
    prepare = load("review_prepare", FIXTURE / "prepare_bundle.py")
    integrity = load("review_integrity", FIXTURE / "bundle_integrity.py")
    source = tmp_path / "repo"
    here = source / "fixture"
    here.mkdir(parents=True)
    (source / "docs").mkdir()
    (source / "docs/disposable-container-test.md").write_text(
        "Synthetic review inputs."
    )
    for name in prepare.FILES:
        shutil.copyfile(FIXTURE / name, here / name)
    wheels = tmp_path / "inputs"
    wheels.mkdir()
    requirements, packages, hashes = [], [], {}
    for name in sorted(integrity.DEPENDENCIES | integrity.APPLICATIONS):
        filename = f"{name}-1.0-py3-none-any.whl"
        path = wheels / filename
        path.write_bytes(f"synthetic wheel bytes for {name}".encode())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[name] = digest
        packages.append(
            f'[[package]]\nname = "{name}"\nversion = "1.0"\nwheels = [{{url = "https://files.pythonhosted.org/{filename}", hash = "sha256:{digest}"}}]\n'
        )
        if name in integrity.DEPENDENCIES:
            requirements.append(f"{name}==1.0 --hash=sha256:{digest}\n")
    (source / "uv.lock").write_text("\n".join(packages))
    (here / "runtime-requirements.arm64.txt").write_text("".join(requirements))
    monkeypatch.setattr(prepare, "REPO", source)
    monkeypatch.setattr(prepare, "HERE", here)
    output = tmp_path / "review"
    arguments = (
        output,
        wheels,
        wheels / "fairway-1.0-py3-none-any.whl",
        hashes["fairway"],
        wheels / "modo-1.0-py3-none-any.whl",
        hashes["modo"],
    )
    return prepare, integrity, output, arguments


def test_prepare_clean_bundle_offline_and_refuse_existing_output(prepared):
    prepare, integrity, output, args = prepared
    with patch("subprocess.run") as external:
        result = prepare.prepare(*args)
    external.assert_not_called()
    assert result["network_calls"] == result["docker_calls"] == 0
    assert integrity.verify(output)["wheels"] == 8
    with pytest.raises(ValueError, match="new directory"):
        prepare.prepare(*args)


@pytest.mark.parametrize(
    "injection", ["extra-wheel", "extra-root-file", "extra-manifest-wheel", "symlink"]
)
def test_extra_files_and_manifest_injection_fail_before_review(
    prepared, injection, monkeypatch
):
    prepare, integrity, output, args = prepared
    prepare.prepare(*args)
    name = "wheels/unlisted-1.0-py3-none-any.whl"
    if injection == "extra-root-file":
        (output / "unlisted.txt").write_text("unexpected")
    elif injection == "symlink":
        (output / name).symlink_to(args[2])
    else:
        (output / name).write_bytes(b"unlisted wheel")
        if injection == "extra-manifest-wheel":
            digest = hashlib.sha256(b"unlisted wheel").hexdigest()
            with (output / "SHA256SUMS").open("a") as stream:
                stream.write(f"{digest}  {name}\n")
    with pytest.raises(ValueError):
        integrity.verify(output)
    review = load("review_run", FIXTURE / "run_review.py")
    monkeypatch.setattr(review, "ROOT", output)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_review.py",
            "--execute",
            "--api-image-id",
            "sha256:" + "a" * 64,
            "--fixture-image-id",
            "sha256:" + "b" * 64,
        ],
    )
    with patch("subprocess.run") as docker, pytest.raises(ValueError):
        review.main()
    docker.assert_not_called()


def test_bad_application_hash_creates_no_output(prepared):
    prepare, _, output, args = prepared
    altered = (*args[:3], "0" * 64, *args[4:])
    with pytest.raises(ValueError, match="checksum mismatch"):
        prepare.prepare(*altered)
    assert not output.exists()


def test_image_wheel_subset_verification_rejects_pip_candidate_injection(prepared):
    prepare, integrity, output, args = prepared
    prepare.prepare(*args)
    image = output.parent / "image-copy"
    image.mkdir()
    for name in integrity.IMAGE_FILES | {"SHA256SUMS"}:
        shutil.copyfile(output / name, image / name)
    shutil.copytree(output / "wheels", image / "wheels")
    assert integrity.verify(image, wheels_only=True)["wheels"] == 8
    (image / "wheels/geographiclib-999.0-py3-none-any.whl").write_bytes(
        b"rogue candidate"
    )
    with pytest.raises(ValueError, match="extra or missing"):
        integrity.verify(image, wheels_only=True)


def test_application_requirement_cannot_be_an_external_url(prepared):
    prepare, integrity, output, args = prepared
    prepare.prepare(*args)
    (output / "application-requirements.txt").write_text(
        "https://example.com/rogue.whl\n"
    )
    with pytest.raises(ValueError, match="local hash-locked"):
        integrity.verify(output)


def test_documented_output_setup_allows_precreated_logs_without_changing_bundle(
    prepared,
):
    prepare, integrity, output, args = prepared
    prepare.prepare(*args)
    before = integrity.verify(output)
    document = (FIXTURE.parents[2] / "docs/disposable-container-test.md").read_text()
    # Execute the actual shared setup lines, not a different directory recipe.
    lines = [
        line for line in document.splitlines() if line.startswith("REVIEW_OUTPUT=")
    ]
    assert len(lines) == 6 and lines[:2] == lines[2:4] == lines[4:6]
    script = "\n".join(lines[:2]) + "\nexport REVIEW_OUTPUT\n"
    script += (
        f"{shlex.quote(sys.executable)} run_review.py "
        '> "$REVIEW_OUTPUT/review-events.jsonl" 2>&1\n'
        'printf "%s\\n" "$REVIEW_OUTPUT"\n'
    )
    completed = subprocess.run(
        ["bash", "-eu", "-c", script],
        cwd=output,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    evidence = Path(completed.stdout.strip())
    assert evidence.is_absolute() and evidence.parent == output.parent
    assert not evidence.is_relative_to(output)
    assert (
        json.loads((evidence / "review-events.jsonl").read_text())["docker_calls"] == 0
    )
    # No Docker save: a stand-in archive exercises the same outside output location.
    (evidence / "fairway-safety-images.tar").write_bytes(b"synthetic archive evidence")
    assert integrity.verify(output) == before
    assert not (output / "review-events.jsonl").exists()
    assert not (output / "fairway-safety-images.tar").exists()
    assert 'docker save -o "$REVIEW_OUTPUT/fairway-safety-images.tar"' in document


@pytest.mark.parametrize("name", ["review-events.jsonl", "fairway-safety-images.tar"])
def test_operator_outputs_inside_bundle_still_fail_exact_file_check(prepared, name):
    prepare, integrity, output, args = prepared
    prepare.prepare(*args)
    (output / name).write_bytes(b"operator output must stay outside")
    with pytest.raises(ValueError, match="extra or missing"):
        integrity.verify(output)
