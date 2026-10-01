#!/usr/bin/env python3
"""Post a CI transcript to the pull request that triggered the run.

Used so a failing matrix job (e.g. Windows, where blob storage log downloads
may be unavailable) can still be inspected from the conversation:

    python tools/post_ci_output.py selftest.txt "windows-latest"

Environment:
    PR_NUMBER         pull request number (absent on plain pushes → no-op)
    GITHUB_REPOSITORY owner/repo
    GH_TOKEN          authentication for `gh`
"""

from __future__ import annotations

import os
import subprocess
import sys


def main(argv: list[str]) -> int:
    log_path = argv[1] if len(argv) > 1 else "selftest.txt"
    label = argv[2] if len(argv) > 2 else os.environ.get("RUNNER_OS", "CI")
    pr = os.environ.get("PR_NUMBER", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()

    if not pr or not repo:
        print("no pull request context — nothing to post")
        return 0

    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        text = f"(could not read {log_path}: {exc})"

    if len(text) > 60000:
        text = text[:30000] + "\n… (truncated) …\n" + text[-20000:]

    body = f"### Self-test output ({label})\n\n```\n{text}\n```"
    result = subprocess.run(
        ["gh", "pr", "comment", pr, "--repo", repo, "--body", body],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip()[:500])
        return result.returncode
    print("posted self-test output to PR #" + pr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
