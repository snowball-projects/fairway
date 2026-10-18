"""Select additive verification scopes; uncertain paths require full integration."""

import argparse
import json
import os
import subprocess
from pathlib import Path, PurePosixPath

CATALOG_FACT_TESTS = {"tests/test_catalog_foundation.py", "tests/test_kansas_delta.py"}
PACKAGE_FILES = {"MANIFEST.in", "README.md", "LICENSE", "THIRD-PARTY-NOTICES.md"}
DEPENDENCY_FILES = {"pyproject.toml", "uv.lock"}
ROAD_FILES = {
    "src/fairway/app.py",
    "src/fairway/course_index.py",
    "src/fairway/courses.py",
    "src/fairway/fetch.py",
    "src/fairway/matrix.py",
    "src/fairway/paths.py",
    "src/fairway/scoring.py",
    "src/fairway/snapshots.py",
    "scripts/build_course_index.py",
    "scripts/build_snapshot.py",
    "scripts/fetch_snapshot.py",
    "scripts/validate_snapshot.py",
}


def catalog_path(path):
    return (
        path.startswith("data/catalog-release/")
        or path in {"data/README.md", "CHANGELOG.md"}
        or path in CATALOG_FACT_TESTS
        or (
            PurePosixPath(path).parent == PurePosixPath("docs/catalog")
            and PurePosixPath(path).name.startswith("RELEASE")
            and path.endswith(".md")
        )
    )


def select(paths, *, uncertain=False):
    paths = set(paths)
    # Test-only changes cannot assert that production behavior is unchanged.
    catalog_only = (
        bool(paths)
        and any(p.startswith("data/catalog-release/") for p in paths)
        and all(catalog_path(p) for p in paths)
    )
    types = set()
    if uncertain or not paths:
        types.add("full")
    elif catalog_only:
        types.add("catalog")
    else:
        for path in paths:
            if path in DEPENDENCY_FILES:
                types.add("dependencies")
            elif path in PACKAGE_FILES:
                types.add("packaging")
            elif path.startswith("experiments/catalog-expansion/"):
                types.add("experiment")
            elif path.startswith("src/fairway/") or path == "scripts/build_pages.py":
                types.add("runtime")
            elif not catalog_path(path) or path in CATALOG_FACT_TESTS:
                types.add("full")
        if not types:
            types.add("full")
    app = bool(types & {"runtime", "packaging", "dependencies", "full"})
    return {
        "scope": ", ".join(sorted(types)),
        "app": app,
        "archive_both": bool(types & {"packaging", "dependencies", "full"}),
        "snapshot": bool(types & {"dependencies", "full"})
        or any(p in ROAD_FILES or p.startswith("src/fairway/data/") for p in paths),
        "experiment": "experiment" in types or "full" in types,
    }


def changed_paths(base, head):
    if not base or set(base) == {"0"}:
        return [], True
    try:
        # --no-renames keeps both removed and added paths, so moves cannot hide scope.
        raw = subprocess.check_output(
            ["git", "diff", "--no-renames", "--name-only", "-z", base, head]
        )
    except subprocess.CalledProcessError:
        return [], True
    return os.fsdecode(raw).rstrip("\0").split("\0") if raw else [], False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("BASE"))
    parser.add_argument("--head", default=os.environ.get("HEAD", "HEAD"))
    args = parser.parse_args()
    paths, uncertain = changed_paths(args.base, args.head)
    result = select(paths, uncertain=uncertain)
    print(json.dumps({**result, "changed_paths": paths}, indent=2))
    outputs = "".join(
        f"{name}={str(value).lower() if isinstance(value, bool) else value}\n"
        for name, value in result.items()
    )
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
            stream.write(outputs)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write("### Selected verification\n\n```text\n" + outputs + "```\n")


if __name__ == "__main__":
    main()
