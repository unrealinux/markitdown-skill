#!/usr/bin/env python3
"""Run the markitdown skill evals defined in evals.json.

    py evals/make_fixtures.py && py evals/run_evals.py

Standard library only. Each eval shells out to scripts/convert.py, which is the
same entry point a skill invocation uses, so a pass means the wrapper works
end to end (uv + markitdown + converted output).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CONVERT = os.path.join(SKILL_DIR, "scripts", "convert.py")
FIXTURES = os.path.join(HERE, "fixtures")

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def setup_stdio():
    """UTF-8 output and colour only when it helps.

    Without the reconfigure the Windows ANSI code page (cp936) kills the run
    when a fixture contains emoji or rare CJK.
    """
    global GREEN, RED, DIM, RESET
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        GREEN = RED = DIM = RESET = ""


def run_convert(args):
    """Run the wrapper, returning (exit_code, stdout, stderr)."""
    process = subprocess.run(
        [sys.executable, CONVERT, *args],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    return process.returncode, process.stdout, process.stderr


def check_file_eval(spec):
    """Convert one fixture to stdout and check the text."""
    fixture = os.path.join(SKILL_DIR, spec["files"][0])
    code, out, err = run_convert([fixture])
    problems = []

    if code != 0:
        problems.append(f"exit code {code}: {err.strip().splitlines()[-1] if err.strip() else 'no stderr'}")
        return problems, ""

    for needle in spec.get("expect_contains", []):
        if needle not in out:
            problems.append(f"missing expected text: {needle!r}")
    for needle in spec.get("expect_not_contains", []):
        if needle in out:
            problems.append(f"unexpected text present: {needle!r}")

    length = len(out.strip())
    if length < spec.get("min_chars", 0):
        problems.append(f"output too short: {length} chars < {spec['min_chars']}")
    if "max_chars" in spec and length > spec["max_chars"]:
        problems.append(f"output too long: {length} chars > {spec['max_chars']}")

    return problems, out


def check_dir_eval(spec, workdir):
    """Convert a fixture tree and check which files appear where."""
    source = os.path.join(SKILL_DIR, spec["files"][0])
    out_dir = os.path.join(workdir, f"eval-{spec['id']}")
    args = [source, "--output-dir", out_dir]
    if spec.get("recursive"):
        args.append("--recursive")

    code, out, err = run_convert(args)
    problems = []
    if code != 0:
        problems.append(f"exit code {code}: {err.strip().splitlines()[-1] if err.strip() else 'no stderr'}")
        return problems, out

    for relative, needle in spec.get("expect_files", {}).items():
        path = os.path.join(out_dir, relative)
        if not os.path.isfile(path):
            problems.append(f"missing output file: {relative}")
            continue
        with open(path, encoding="utf-8") as handle:
            if needle not in handle.read():
                problems.append(f"{relative} does not contain {needle!r}")

    for relative in spec.get("expect_absent_files", []):
        if os.path.exists(os.path.join(out_dir, relative)):
            problems.append(f"file should not have been written: {relative}")

    if spec.get("expect_stdout_empty") and out.strip():
        problems.append(f"directory mode leaked {len(out.strip())} chars to stdout")

    return problems, out


def main():
    setup_stdio()
    if not os.path.isdir(FIXTURES):
        print("fixtures missing — run: python3 evals/make_fixtures.py")
        return 2

    with open(os.path.join(HERE, "evals.json"), encoding="utf-8") as handle:
        specs = json.load(handle)["evals"]

    failures = []
    failed_ids = []
    workdir = tempfile.mkdtemp(prefix="markitdown-evals-")
    try:
        for spec in specs:
            label = f"[{spec['id']}] {spec['prompt']}"
            if spec.get("mode") == "dir":
                problems, output = check_dir_eval(spec, workdir)
            else:
                problems, output = check_file_eval(spec)

            if problems:
                failures.append((label, problems, output))
                failed_ids.append(spec["id"])
                print(f"{RED}FAIL{RESET} {label}")
                for problem in problems:
                    print(f"     - {problem}")
            else:
                preview = output.strip().replace("\n", " ")[:60]
                print(f"{GREEN}PASS{RESET} {label}")
                print(f"     {DIM}{len(output.strip())} chars: {preview}{RESET}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    total = len(specs)
    passed = total - len(failures)
    print(f"\n{passed}/{total} evals passed")
    if failed_ids:
        ids = ", ".join(str(value) for value in failed_ids)
        print(f"{RED}failed ids: {ids}{RESET}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
