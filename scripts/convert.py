#!/usr/bin/env python3
"""
MarkItDown wrapper script for skill use.
Converts documents to Markdown using the markitdown package.

Requirements:
- uv (install: https://astral.sh/uv)
- Python 3.10+; this script prefers the 3.12 toolchain that uv manages

Single file mode writes Markdown to stdout unless -o is given.
Directory mode writes one .md per input file, mirroring subdirectories.
"""

import argparse
import os
import shutil
import subprocess
import sys

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".html", ".htm", ".csv", ".txt", ".json", ".xml", ".zip",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".mp3", ".wav", ".m4a",
}

# Runs inside the uv-managed interpreter. The input path arrives through argv,
# never interpolated into this source, so Windows backslash paths and paths
# containing quotes cannot produce a SyntaxError.
CONVERT_SNIPPET = (
    "import sys\n"
    "from markitdown import MarkItDown\n"
    "try:\n"
    "    result = MarkItDown().convert(sys.argv[1])\n"
    "except Exception as exc:\n"
    "    print(f'Error: {exc}', file=sys.stderr)\n"
    "    sys.exit(1)\n"
    "sys.stdout.write(getattr(result, 'text_content', str(result)))\n"
)


def force_utf8_stdout():
    """Make this process emit UTF-8 Markdown.

    The child interpreter is handled separately by child_env(); this covers the
    wrapper itself, whose stdout would otherwise be the Windows ANSI code page.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        sys.stderr.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


def child_env():
    """Environment for the child interpreter: force UTF-8 stdio.

    Without PYTHONUTF8, a redirected stdout uses the ANSI code page (cp936/gbk
    on zh-CN Windows) and the conversion dies with UnicodeEncodeError on any
    character that code page cannot encode (emoji, arrows, rare CJK).
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def find_uv():
    """Locate the uv executable across Linux, macOS and Windows installs."""
    candidates = [
        os.path.expanduser("~/.local/bin/uv"),
        "uv",
        "/usr/local/bin/uv",
        "/opt/homebrew/bin/uv",
        os.path.join(os.environ.get("APPDATA", ""), "Python", "Python314", "Scripts", "uv.exe"),
        os.path.expanduser("~/AppData/Roaming/Python/Python314/Scripts/uv.exe"),
        os.path.expanduser("~/.local/bin/uv.exe"),
    ]
    for cmd in candidates:
        if cmd and (shutil.which(cmd) or os.path.exists(cmd)):
            return cmd
    return None


def find_python(uv_path):
    """Ask uv for a 3.12 interpreter; returns None when unavailable."""
    try:
        result = subprocess.run(
            [uv_path, "python", "find", "3.12"],
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        resolved = line.strip()
        if resolved and os.path.exists(resolved):
            return resolved
    return None


def uv_command(uv_path, python_path):
    """Build the `uv run` command that performs one conversion."""
    cmd = [uv_path, "run", "--with", "markitdown"]
    if python_path:
        cmd += ["--python", python_path]
    return cmd + ["python", "-c", CONVERT_SNIPPET]


def convert_one(input_path, uv_path, python_path, output_path=None):
    """Convert a single file.

    Returns the Markdown text on success, None on failure. With output_path the
    Markdown goes to that file, otherwise to stdout.
    """
    print(f"📄 Converting: {input_path}", file=sys.stderr)
    cmd = uv_command(uv_path, python_path) + [input_path]

    try:
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace",
            env=child_env(),
        )
    except OSError as exc:
        print(f"❌ Could not run uv: {exc}", file=sys.stderr)
        return None

    if result.returncode != 0:
        lines = [line for line in (result.stderr or "").splitlines() if line.strip()]
        detail = lines[-1] if lines else "unknown error"
        print(f"❌ Conversion failed: {detail}", file=sys.stderr)
        return None

    text = result.stdout
    if output_path:
        parent = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"✅ Saved to: {output_path} ({len(text)} chars)", file=sys.stderr)
    else:
        sys.stdout.write(text)
        sys.stdout.flush()
    return text


def collect_files(input_dir, recursive):
    """List supported files under input_dir, sorted, skipping dot-directories."""
    found = []
    for root, dirs, names in os.walk(input_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if root == input_dir and not recursive:
            dirs[:] = []
        for name in sorted(names):
            if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                found.append(os.path.join(root, name))
    return found


def convert_batch(input_dir, output_dir, uv_path, python_path, recursive=False):
    """Convert every supported file, mirroring the input tree into output_dir."""
    files = collect_files(input_dir, recursive)
    if not files:
        print(f"❌ No supported files found in {input_dir}", file=sys.stderr)
        return 1

    converted = 0
    failed = []
    for path in files:
        relative = os.path.relpath(path, input_dir)
        relative_stem = os.path.splitext(relative)[0]
        output_path = os.path.join(output_dir, relative_stem + ".md")
        if convert_one(path, uv_path, python_path, output_path) is None:
            failed.append(path)
        else:
            converted += 1

    print(f"📦 Batch finished: {converted} converted, {len(failed)} failed", file=sys.stderr)
    for path in failed:
        print(f"   ❌ {path}", file=sys.stderr)
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown using markitdown"
    )
    parser.add_argument("input", help="Input file or directory")
    parser.add_argument("-o", "--output",
                        help="Output file path. Single file mode prints to stdout when omitted")
    parser.add_argument("--recursive", action="store_true",
                        help="Recurse into subdirectories (directory mode)")
    parser.add_argument("--output-dir", metavar="DIR",
                        help="Output directory for directory mode (default: <input>_markdown)")
    args = parser.parse_args()

    force_utf8_stdout()

    if not os.path.exists(args.input):
        print(f"Error: input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    uv_path = find_uv()
    if not uv_path:
        print("Error: uv not found. Install it first:", file=sys.stderr)
        print("  curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
        print("  Windows: uv is expected at %APPDATA%\\Python\\Python314\\Scripts\\uv.exe", file=sys.stderr)
        sys.exit(1)

    print("🔍 Resolving Python 3.12 via uv (first run may download it)...", file=sys.stderr)
    python_path = find_python(uv_path)
    if not python_path:
        print("⚠️  Python 3.12 not found via uv; falling back to uv's default interpreter",
              file=sys.stderr)

    if os.path.isdir(args.input):
        if args.output:
            print("Error: -o applies to single files; use --output-dir for directories",
                  file=sys.stderr)
            sys.exit(1)
        output_dir = args.output_dir or (args.input.rstrip("/\\") + "_markdown")
        sys.exit(convert_batch(args.input, output_dir, uv_path, python_path, args.recursive))

    if args.output and os.path.isdir(args.output):
        print(f"Error: {args.output} is a directory; use --output-dir", file=sys.stderr)
        sys.exit(1)

    text = convert_one(args.input, uv_path, python_path, args.output)
    sys.exit(0 if text is not None else 1)


if __name__ == "__main__":
    main()
