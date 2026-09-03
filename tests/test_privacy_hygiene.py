"""Regression checks preventing private environment data from being committed."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_IDENTIFIERS = (
    "pido" + "udet",
    "Pierre " + "DOUDET",
    "OneDrive - " + "Microsoft",
    "PBI " + "SME",
    "OracleTo" + "Postgre",
    "ms-len-" + "moa",
)
CORPORATE_EMAIL = re.compile(
    r"[A-Z0-9._%+-]+@(microsoft|outlook|hotmail)\.com",
    re.IGNORECASE,
)
PRIVATE_HOSTNAME = re.compile(
    r"https?://(?:[^/\s]+\.)?(?:corp|internal|intranet|company-private)\.[^/\s]+",
    re.IGNORECASE,
)
WINDOWS_USER_PATH = re.compile(r"[A-Z]:\\Users\\[^<%$\\]+", re.IGNORECASE)


def _tracked_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = result.stdout.decode("utf-8").split("\0")
    return [ROOT / path for path in paths if path and (ROOT / path).is_file()]


def test_generated_customer_artifacts_are_not_tracked() -> None:
    tracked_artifacts = [
        path.relative_to(ROOT).as_posix()
        for path in _tracked_text_files()
        if path.relative_to(ROOT).parts[0] == "artifacts"
    ]

    assert not tracked_artifacts, (
        "Generated customer artifacts must never be tracked:\n"
        + "\n".join(tracked_artifacts)
    )


def test_tracked_files_do_not_expose_private_environment_data() -> None:
    findings: list[str] = []

    for path in _tracked_text_files():
        if path == Path(__file__):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        relative = path.relative_to(ROOT).as_posix()
        lowered = text.casefold()
        for identifier in PRIVATE_IDENTIFIERS:
            if identifier.casefold() in lowered:
                findings.append(f"{relative}: private identifier")
        if CORPORATE_EMAIL.search(text):
            findings.append(f"{relative}: corporate email address")
        if PRIVATE_HOSTNAME.search(text):
            findings.append(f"{relative}: private hostname")
        if WINDOWS_USER_PATH.search(text):
            findings.append(f"{relative}: hard-coded Windows user profile")

    assert not findings, "Private data found in tracked files:\n" + "\n".join(findings)