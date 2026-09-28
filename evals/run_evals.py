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
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def setup_stdio():
    """UTF-8 output and colour only when it helps.

    Without the reconfigure the Windows ANSI code page (cp936) kills the run
    when a fixture contains emoji or rare CJK.
    """
    global GREEN, RED, YELLOW, DIM, RESET
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        GREEN = RED = YELLOW = DIM = RESET = ""


def run_convert(args, stdin_bytes=None):
    """Run the wrapper, returning (exit_code, stdout, stderr)."""
    # stdin stays bytes (a PDF piped into `- -x pdf` is not text), so the streams
    # are decoded here instead of letting subprocess do it via encoding=.
    process = subprocess.run(
        [sys.executable, CONVERT, *args],
        input=stdin_bytes,
        capture_output=True,
    )
    return (
        process.returncode,
        process.stdout.decode("utf-8", "replace"),
        process.stderr.decode("utf-8", "replace"),
    )


def check_file_eval(spec, workdir):
    """Convert one fixture and check the text, either from stdout or a file."""
    fixture = os.path.join(SKILL_DIR, spec["files"][0])
    problems = []

    output_file = None
    if spec.get("write_to_file"):
        output_file = os.path.join(workdir, f"eval-{spec['id']}.md")
        args = [fixture, "-o", output_file]
    else:
        args = [fixture]

    code, out, err = run_convert(args)
    expected_code = spec.get("expect_exit_code", 0)
    if code != expected_code:
        last = err.strip().splitlines()[-1] if err.strip() else "no stderr"
        problems.append(f"exit code {code}, expected {expected_code}: {last}")

    for needle in spec.get("expect_stderr_contains", []):
        if needle not in err:
            problems.append(f"stderr missing: {needle!r}")

    if output_file is not None:
        if not os.path.isfile(output_file):
            problems.append(f"no output file written: {output_file}")
            text = ""
        else:
            with open(output_file, encoding="utf-8") as handle:
                text = handle.read()
        if out.strip():
            problems.append(f"stdout should be empty when -o is used, got {len(out.strip())} chars")
    else:
        text = out

    for needle in spec.get("expect_contains", []):
        if needle not in text:
            problems.append(f"missing expected text: {needle!r}")
    for needle in spec.get("expect_not_contains", []):
        if needle in text:
            problems.append(f"unexpected text present: {needle!r}")

    length = len(text.strip())
    if length < spec.get("min_chars", 0):
        problems.append(f"output too short: {length} chars < {spec['min_chars']}")
    if "max_chars" in spec and length > spec["max_chars"]:
        problems.append(f"output too long: {length} chars > {spec['max_chars']}")

    return problems, text


def check_dir_eval(spec, workdir):
    """Convert a fixture tree and check which files appear where."""
    source = os.path.join(SKILL_DIR, spec["files"][0])
    out_dir = os.path.join(workdir, f"eval-{spec['id']}")
    args = [source, "--output-dir", out_dir] + list(spec.get("extra_args") or [])
    if spec.get("recursive"):
        args.append("--recursive")

    code, out, err = run_convert(args)
    problems = []
    expected_code = spec.get("expect_exit_code", 0)
    if code != expected_code:
        last = err.strip().splitlines()[-1] if err.strip() else "no stderr"
        problems.append(f"exit code {code}, expected {expected_code}: {last}")

    for needle in spec.get("expect_stderr_contains", []):
        if needle not in err:
            problems.append(f"stderr missing: {needle!r}")

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

    if spec.get("expect_json"):
        try:
            payload = json.loads(out)
        except json.JSONDecodeError as exc:
            problems.append(f"stdout is not JSON: {exc}")
            payload = {}
        for key in (spec["expect_json"].get("keys") or []):
            if key not in payload:
                problems.append(f"json summary is missing key: {key}")
        for key, expected in (spec["expect_json"].get("counts") or {}).items():
            actual = len(payload.get(key) or [])
            if actual != expected:
                problems.append(f"json {key}: {actual} entries, expected {expected}")
        for key, needle in (spec["expect_json"].get("mentions") or {}).items():
            blob = json.dumps(payload.get(key), ensure_ascii=False)
            if needle not in blob:
                problems.append(f"json {key} does not mention {needle!r}")
    elif spec.get("expect_stdout_empty") and out.strip():
        problems.append(f"directory mode leaked {len(out.strip())} chars to stdout")

    return problems, out


def check_cli_eval(spec, workdir):
    """Run the wrapper with literal arguments: URIs, stdin and --help."""
    args = [arg.replace("{skill}", SKILL_DIR) for arg in spec["args"]]
    stdin_bytes = None
    if spec.get("stdin_file"):
        with open(os.path.join(SKILL_DIR, spec["stdin_file"]), "rb") as handle:
            stdin_bytes = handle.read()

    code, out, err = run_convert(args, stdin_bytes=stdin_bytes)
    problems = []
    expected_code = spec.get("expect_exit_code", 0)
    if code != expected_code:
        last = err.strip().splitlines()[-1] if err.strip() else "no stderr"
        problems.append(f"exit code {code}, expected {expected_code}: {last}")

    for needle in spec.get("expect_stdout_contains", []):
        if needle not in out:
            problems.append(f"stdout missing: {needle!r}")
    for needle in spec.get("expect_stderr_contains", []):
        if needle not in err:
            problems.append(f"stderr missing: {needle!r}")
    for needle in spec.get("expect_not_contains", []):
        if needle in out:
            problems.append(f"unexpected stdout text: {needle!r}")

    length = len(out.strip())
    if length < spec.get("min_chars", 0):
        problems.append(f"stdout too short: {length} chars < {spec['min_chars']}")
    if "max_chars" in spec and length > spec["max_chars"]:
        problems.append(f"stdout too long: {length} chars > {spec['max_chars']}")

    return problems, out


def check_source_eval(spec):
    """Grep the skill's own files. Guards against doc and config regressions."""
    problems = []
    for relative in spec["files"]:
        path = os.path.join(SKILL_DIR, relative)
        if not os.path.isfile(path):
            problems.append(f"missing file: {relative}")
            continue
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for needle in spec.get("expect_contains", []):
            if needle not in text:
                problems.append(f"{relative} is missing {needle!r}")
        for needle in spec.get("expect_not_contains", []):
            if needle in text:
                problems.append(f"{relative} still contains {needle!r}")
    return problems, ""


def main():
    setup_stdio()
    if not os.path.isdir(FIXTURES):
        print("fixtures missing — run: python3 evals/make_fixtures.py")
        return 2

    with open(os.path.join(HERE, "evals.json"), encoding="utf-8") as handle:
        specs = json.load(handle)["evals"]

    failures = []
    failed_ids = []
    skipped_ids = []
    workdir = tempfile.mkdtemp(prefix="markitdown-evals-")
    try:
        for spec in specs:
            label = f"[{spec['id']}] {spec['prompt']}"
            missing = [f for f in spec.get("files", [])
                       if not os.path.exists(os.path.join(SKILL_DIR, f))]
            if missing:
                skipped_ids.append(spec["id"])
                print(f"{YELLOW}SKIP{RESET} {label}")
                print(f"     missing fixture {missing[0]} — run evals/make_fixtures.py")
                continue

            if spec.get("mode") == "source":
                problems, output = check_source_eval(spec)
            elif spec.get("mode") == "cli":
                problems, output = check_cli_eval(spec, workdir)
            elif spec.get("mode") == "dir":
                problems, output = check_dir_eval(spec, workdir)
            else:
                problems, output = check_file_eval(spec, workdir)

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
    passed = total - len(failures) - len(skipped_ids)
    summary = f"\n{passed}/{total} evals passed"
    if skipped_ids:
        ids = ", ".join(str(value) for value in skipped_ids)
        summary += f", {len(skipped_ids)} skipped (ids: {ids})"
    print(summary)
    if failed_ids:
        ids = ", ".join(str(value) for value in failed_ids)
        print(f"{RED}failed ids: {ids}{RESET}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
