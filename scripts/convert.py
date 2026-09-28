#!/usr/bin/env python3
"""
MarkItDown wrapper script for skill use.
Converts documents to Markdown using the markitdown package.

Requirements:
- uv (install: https://astral.sh/uv)
- Python 3.10+; this script prefers the 3.12 toolchain that uv manages

Single input writes Markdown to stdout unless -o is given. The input may be a
file, a URL (http:, https:, file:, data:), or "-" for stdin. Directory mode
writes one .md per input file, mirroring subdirectories, and converts every file
inside one interpreter.

Single-file conversion is delegated to markitdown's own CLI, so every upstream
flag (-x/-m/-c, -d, --use-cu, -p, --keep-data-uris, --list-plugins) behaves
exactly as documented by markitdown. Directory mode cannot use that CLI (it has
no batch mode), so it runs a small in-process loop instead, with the same
constructor and conversion options forwarded through a JSON manifest.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# markitdown pulls its format support in as optional extras: the bare package
# cannot read .docx, .xlsx, .pptx or .pdf and raises MissingDependencyException.
# These five cover the common office formats; anything else (outlook, audio,
# az-doc-intel, az-content-understanding, all) is reachable with --extra.
BASE_EXTRAS = ["docx", "xls", "xlsx", "pptx", "pdf"]
DEFAULT_WITH = "markitdown[" + ",".join(BASE_EXTRAS) + "]"

# Extras that exist in markitdown 0.1.8, for the --extra help text.
KNOWN_EXTRAS = [
    "all", "audio-transcription", "az-content-understanding", "az-doc-intel",
    "docx", "outlook", "pdf", "pptx", "xls", "xlsx", "youtube-transcription",
]

# Always request 3.12 explicitly. Falling back to whatever interpreter uv prefers
# is worse than failing: on 3.14 the extras have no ready wheels and the run
# spends 15+ minutes downloading instead of reporting anything. When 3.12 is
# missing uv installs it, which takes about a minute.
PYTHON_REQUEST = "3.12"

# What markitdown 0.1.8 actually reads, taken from its converters' accepted
# extension lists. .doc and .ppt are NOT here: no converter accepts them and
# there is no LibreOffice/antiword path in the package, so they fail with
# UnsupportedFormatException. .gif/.bmp/.webp are not here either — the image
# converter accepts only .jpg/.jpeg/.png.
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".csv",
    ".txt", ".text", ".json", ".jsonl", ".xml",
    ".html", ".htm", ".ipynb", ".epub", ".msg", ".zip",
    ".jpg", ".jpeg", ".png",
    ".mp3", ".wav", ".m4a", ".mp4",
}

# Already Markdown: converting would be a byte-for-byte copy and, with
# --output-dir pointing at the input, could overwrite the source. Directory mode
# skips these and says so; single-file mode still converts if asked.
ALREADY_MARKDOWN = {".md", ".markdown"}

# URI schemes markitdown.convert() accepts. A Windows path like C:\x does not
# match (single-letter scheme), and neither does a relative filename.
URI_RE = re.compile(r"^(https?|file)://", re.IGNORECASE)
DATA_URI_RE = re.compile(r"^data:", re.IGNORECASE)

# Importing markitdown costs about five seconds, so batch mode converts every
# file inside one interpreter instead of paying that cost per file. The child
# reads a JSON manifest of {jobs, options} and reports one JSON line per job,
# which keeps the markdown itself out of the framed stdout stream.
BATCH_SNIPPET = (
    "import json\n"
    "import os\n"
    "import sys\n"
    "from markitdown import MarkItDown\n"
    "with open(sys.argv[1], encoding='utf-8') as handle:\n"
    "    manifest = json.load(handle)\n"
    "jobs = manifest['jobs']\n"
    "options = manifest.get('options') or {}\n"
    "ctor = dict(options.get('ctor') or {})\n"
    "if ctor.get('cu_file_types'):\n"
    "    from markitdown.converters import ContentUnderstandingFileType\n"
    "    ctor['cu_file_types'] = [ContentUnderstandingFileType(name)\n"
    "                             for name in ctor['cu_file_types']]\n"
    "stream_info = None\n"
    "hints = options.get('stream_info') or {}\n"
    "if hints:\n"
    "    from markitdown._stream_info import StreamInfo\n"
    "    stream_info = StreamInfo(**hints)\n"
    "convert_kwargs = dict(options.get('convert') or {})\n"
    "converter = MarkItDown(**ctor)\n"
    "for job in jobs:\n"
    "    record = {'input': job['input'], 'output': job['output'], 'ok': False,\n"
    "              'chars': 0, 'error': None}\n"
    "    try:\n"
    "        result = converter.convert(job['input'], stream_info=stream_info,\n"
    "                                  **convert_kwargs)\n"
    "        text = getattr(result, 'text_content', '') or ''\n"
    "        os.makedirs(os.path.dirname(os.path.abspath(job['output'])), exist_ok=True)\n"
    "        with open(job['output'], 'w', encoding='utf-8') as handle:\n"
    "            handle.write(text)\n"
    "        record['ok'] = True\n"
    "        record['chars'] = len(text)\n"
    "    except Exception as exc:\n"
    "        record['error'] = f'{type(exc).__name__}: {exc}'\n"
    "    print(json.dumps(record, ensure_ascii=False), flush=True)\n"
)

EMPTY_OUTPUT_WARNING = (
    "⚠️  Empty output: no extractable text. A scanned PDF or an image has no "
    "text layer (markitdown ships no OCR engine); audio needs --extra "
    "audio-transcription."
)


def force_utf8_stdout():
    """Make this process emit UTF-8 on both streams.

    The child interpreter is handled separately by child_env(); this covers the
    wrapper itself, whose stdout and stderr would otherwise be the Windows ANSI
    code page. stderr needs the encoding, not just the error handler: with
    errors="backslashreplace" alone the progress and result emoji were written
    as literal \\U0001f680 / \\u2705 escapes under cp936.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
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
    ]
    # The Windows install is under %APPDATA%\Python\Python3<minor>\, and the
    # minor version changes with every Python release, so glob instead of
    # hard-coding 314 (which silently broke uv discovery after an upgrade).
    appdata_python = os.path.join(os.environ.get("APPDATA", ""), "Python")
    candidates += sorted(
        glob.glob(os.path.join(appdata_python, "Python3*", "Scripts", "uv.exe")),
        reverse=True,
    )
    candidates += [
        os.path.expanduser("~/AppData/Roaming/Python/Python314/Scripts/uv.exe"),
        os.path.expanduser("~/.local/bin/uv.exe"),
    ]
    for cmd in candidates:
        if cmd and (shutil.which(cmd) or os.path.exists(cmd)):
            return cmd
    return None


def with_spec(extras):
    """Build the markitdown requirement string for uv.

    --extra all subsumes the rest, so asking for it alongside named extras must
    not produce "markitdown[docx,...,all]".
    """
    names = list(BASE_EXTRAS) + [extra for extra in extras if extra]
    if "all" in names:
        return "markitdown[all]"
    deduped = []
    for name in names:
        if name not in deduped:
            deduped.append(name)
    return "markitdown[" + ",".join(deduped) + "]"


def uv_command(uv_path, spec, snippet):
    """Build the `uv run` command that runs a python snippet."""
    return [
        uv_path, "run", "--with", spec,
        "--python", PYTHON_REQUEST,
        "python", "-c", snippet,
    ]


def cli_command(uv_path, spec):
    """Build the `uv run` command for markitdown's own CLI."""
    return [
        uv_path, "run", "--with", spec,
        "--python", PYTHON_REQUEST,
        "markitdown",
    ]


def is_uri(value):
    """True for the URI schemes markitdown can fetch or decode itself."""
    return bool(URI_RE.match(value) or DATA_URI_RE.match(value))


def validate_options(args):
    """The same requirement checks the upstream CLI makes, same wording.

    Returns an error message, or None. Doing this before an interpreter starts
    means a missing endpoint costs nothing instead of a download.
    """
    if args.use_docintel and not args.endpoint:
        return ("Document Intelligence Endpoint is required when using Document "
                "Intelligence. Pass -e/--endpoint or set "
                "MARKITDOWN_DOCINTEL_ENDPOINT.")
    if args.use_cu and not args.cu_endpoint:
        return ("Content Understanding Endpoint (--cu-endpoint) is required when "
                "using --use-cu. Pass --cu-endpoint or set MARKITDOWN_CU_ENDPOINT.")
    if args.mime_type and args.mime_type.count("/") != 1:
        return f"Invalid MIME type: {args.mime_type}"
    return None


def cli_args(args):
    """Forward the upstream-compatible flags to markitdown's CLI."""
    forwarded = []
    if args.extension:
        forwarded += ["-x", args.extension]
    if args.mime_type:
        forwarded += ["-m", args.mime_type]
    if args.charset:
        forwarded += ["-c", args.charset]
    if args.use_docintel:
        forwarded += ["-d"]
    if args.endpoint:
        forwarded += ["-e", args.endpoint]
    if args.use_cu:
        forwarded += ["--use-cu"]
    if args.cu_endpoint:
        forwarded += ["--cu-endpoint", args.cu_endpoint]
    if args.cu_analyzer:
        forwarded += ["--cu-analyzer", args.cu_analyzer]
    if args.cu_file_types:
        forwarded += ["--cu-file-types", args.cu_file_types]
    if args.use_plugins:
        forwarded += ["-p"]
    if args.keep_data_uris:
        forwarded += ["--keep-data-uris"]
    return forwarded


def batch_options(args):
    """Turn the flags into the ctor / convert / stream_info parts of a manifest."""
    ctor = {}
    if args.use_plugins:
        ctor["enable_plugins"] = True
    if args.use_docintel:
        ctor["docintel_endpoint"] = args.endpoint
    if args.use_cu:
        ctor["cu_endpoint"] = args.cu_endpoint
        if args.cu_analyzer:
            ctor["cu_analyzer_id"] = args.cu_analyzer
        if args.cu_file_types:
            ctor["cu_file_types"] = [
                name.strip().lower()
                for name in args.cu_file_types.split(",")
                if name.strip()
            ]

    convert_kwargs = {"keep_data_uris": True} if args.keep_data_uris else {}

    stream_info = {}
    if args.extension:
        # markitdown compares extensions with the leading dot; the upstream CLI
        # adds it for the user, so the batch path has to do the same.
        stream_info["extension"] = (
            args.extension if args.extension.startswith(".")
            else "." + args.extension
        )
    if args.mime_type:
        stream_info["mimetype"] = args.mime_type
    if args.charset:
        stream_info["charset"] = args.charset

    return ctor, convert_kwargs, stream_info


def report_failure(result):
    """Print the tail of a failed child run.

    Upstream's _exit_with_error() prints its message to stdout rather than
    stderr, so both streams have to be inspected.
    """
    lines = [
        line for line in ((result.stderr or "") + (result.stdout or "")).splitlines()
        if line.strip()
    ]
    print("❌ Conversion failed:", file=sys.stderr)
    for line in lines[-5:]:
        print(f"   {line}", file=sys.stderr)


def convert_one(args, uv_path, spec):
    """Convert a single file, URL or stdin stream via markitdown's own CLI.

    Returns the Markdown text on success, None on failure.
    """
    source = args.input
    print(f"📄 Converting: {'stdin' if source == '-' else source}", file=sys.stderr)

    cmd = cli_command(uv_path, spec) + cli_args(args)
    if args.output:
        parent = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(parent, exist_ok=True)
        cmd += ["-o", args.output]
    if source != "-":
        cmd.append(source)

    try:
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace",
            env=child_env(),
        )
    except OSError as exc:
        print(f"❌ Could not run uv: {exc}", file=sys.stderr)
        return None

    if result.returncode != 0:
        report_failure(result)
        return None

    if args.output:
        try:
            with open(args.output, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            print(f"❌ Output file not readable: {exc}", file=sys.stderr)
            return None
        print(f"✅ Saved to: {args.output} ({len(text)} chars)", file=sys.stderr)
    else:
        text = result.stdout
        sys.stdout.write(text)
        sys.stdout.flush()

    if not text.strip():
        print(EMPTY_OUTPUT_WARNING, file=sys.stderr)
    return text


def collect_files(input_dir, recursive):
    """Split the tree into convertible files and skipped ones with a reason.

    Dot-directories are skipped: they hold tool state (.git, .venv), and the
    evals assert nothing from them ends up in the output.
    """
    found = []
    skipped = []
    for root, dirs, names in os.walk(input_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if root == input_dir and not recursive:
            dirs[:] = []
        for name in sorted(names):
            path = os.path.join(root, name)
            extension = os.path.splitext(name)[1].lower()
            if extension in SUPPORTED_EXTENSIONS:
                found.append(path)
            elif extension in ALREADY_MARKDOWN:
                skipped.append((path, "already Markdown"))
            else:
                skipped.append((path, "unsupported extension"))
    return found, skipped


def run_batch_jobs(jobs, uv_path, spec, options):
    """Convert every job in one interpreter. Returns one record per job."""
    manifest = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8", prefix="markitdown-jobs-"
    )
    try:
        json.dump({"jobs": jobs, "options": options}, manifest, ensure_ascii=False)
        manifest.close()

        cmd = uv_command(uv_path, spec, BATCH_SNIPPET) + [manifest.name]
        print(f"🚀 Converting {len(jobs)} files in one interpreter...", file=sys.stderr)
        try:
            result = subprocess.run(
                cmd, capture_output=True, encoding="utf-8", errors="replace",
                env=child_env(),
            )
        except OSError as exc:
            print(f"❌ Could not run uv: {exc}", file=sys.stderr)
            return [None] * len(jobs)

        records = {}
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records[record.get("input")] = record

        if result.returncode != 0 and not records:
            lines = [line for line in (result.stderr or "").splitlines() if line.strip()]
            print("❌ Batch run failed:", file=sys.stderr)
            for line in lines[-5:]:
                print(f"   {line}", file=sys.stderr)

        return [records.get(job["input"]) for job in jobs]
    finally:
        try:
            os.unlink(manifest.name)
        except OSError:
            pass


def disambiguate_outputs(jobs):
    """Stop same-stem sources in one directory from overwriting each other.

    report.txt and report.csv both map to report.md, so one conversion silently
    replaced the other. Every member of a colliding group keeps its source
    extension instead: report.txt.md and report.csv.md.
    """
    counts = {}
    for job in jobs:
        key = os.path.normcase(job["output"])
        counts[key] = counts.get(key, 0) + 1

    renamed = []
    for job in jobs:
        if counts[os.path.normcase(job["output"])] < 2:
            continue
        stem, _ = os.path.splitext(job["output"])
        extension = os.path.splitext(job["input"])[1].lstrip(".") or "file"
        job["output"] = f"{stem}.{extension}.md"
        renamed.append(job)

    if renamed:
        print("⚠️  Same output name from different sources; keeping the source "
              "extension:", file=sys.stderr)
        for job in renamed:
            print(f"   {os.path.basename(job['input'])} -> "
                  f"{os.path.basename(job['output'])}", file=sys.stderr)


def report_skipped(skipped):
    """Say what was passed over and why, so a missing file is never a mystery."""
    if not skipped:
        return
    by_reason = {}
    for path, reason in skipped:
        by_reason.setdefault(reason, []).append(path)
    for reason, paths in by_reason.items():
        print(f"⏭️  Skipped {len(paths)} file(s): {reason}", file=sys.stderr)
        for path in paths[:5]:
            print(f"   {path}", file=sys.stderr)
        if len(paths) > 5:
            print(f"   ... and {len(paths) - 5} more", file=sys.stderr)


def convert_batch(args, uv_path, spec):
    """Convert every supported file, mirroring the input tree into output_dir."""
    input_dir = args.input
    output_dir = args.output_dir or (input_dir.rstrip("/\\") + "_markdown")

    files, skipped = collect_files(input_dir, args.recursive)
    report_skipped(skipped)
    if not files:
        print(f"❌ No supported files found in {input_dir}", file=sys.stderr)
        return 1

    jobs = []
    for path in files:
        relative = os.path.relpath(path, input_dir)
        relative_stem = os.path.splitext(relative)[0]
        jobs.append({
            "input": path,
            "output": os.path.join(output_dir, relative_stem + ".md"),
        })

    disambiguate_outputs(jobs)
    ctor, convert_kwargs, stream_info = batch_options(args)
    options = {"ctor": ctor, "convert": convert_kwargs, "stream_info": stream_info}
    results = run_batch_jobs(jobs, uv_path, spec, options)

    converted = 0
    empty = []
    failed = []
    for job, record in zip(jobs, results):
        if record and record.get("ok"):
            converted += 1
            chars = record.get("chars", 0)
            if chars:
                print(f"✅ {job['output']} ({chars} chars)", file=sys.stderr)
            else:
                # Success with zero characters is almost always a scan, an image
                # or audio; reporting it as a plain ✅ hid that from the caller.
                empty.append(job["output"])
                print(f"⚠️  {job['output']} (0 chars — no extractable text: "
                      "scanned page, image, or audio without the "
                      "transcription extra)", file=sys.stderr)
            continue
        failed.append(job["input"])
        detail = (record or {}).get("error") or "no result (the converter stopped early)"
        # markitdown wraps the real cause in a multi-line message; keep the head
        # (exception type) and the tail (what actually threw).
        parts = [line.strip() for line in detail.splitlines() if line.strip()]
        shown = parts[0] if parts else detail
        if len(parts) > 1:
            shown = f"{shown} {parts[-1]}"
        if len(shown) > 240:
            shown = shown[:237] + "..."
        print(f"❌ {job['input']}: {shown}", file=sys.stderr)

    summary = f"📦 Batch finished: {converted} converted, {len(failed)} failed"
    if empty:
        summary += f", {len(empty)} empty"
    if skipped:
        summary += f", {len(skipped)} skipped"
    print(summary, file=sys.stderr)

    if args.json:
        # Machine-readable summary on stdout; progress stays on stderr, so
        # `convert.py docs --output-dir out --json > summary.json` works.
        payload = {
            "input": input_dir,
            "output_dir": output_dir,
            "converted": [
                {"input": job["input"], "output": job["output"],
                 "chars": (record or {}).get("chars", 0)}
                for job, record in zip(jobs, results)
                if record and record.get("ok") and (record.get("chars") or 0)
            ],
            "empty": [
                {"input": job["input"], "output": job["output"]}
                for job, record in zip(jobs, results)
                if record and record.get("ok") and not (record.get("chars") or 0)
            ],
            "failed": [
                {"input": job["input"],
                 "error": (record or {}).get("error") or "no result"}
                for job, record in zip(jobs, results)
                if not (record and record.get("ok"))
            ],
            "skipped": [{"input": path, "reason": reason} for path, reason in skipped],
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        sys.stdout.flush()

    return 1 if failed else 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown using markitdown "
                    "(files, URLs, stdin, or a whole directory)",
        epilog="Extras available: " + ", ".join(KNOWN_EXTRAS),
    )
    parser.add_argument(
        "input", nargs="?", default="-",
        help="Input file, directory, URL (http:/https:/file:/data:) or - for "
             "stdin (default: -)")

    # Wrapper-only options.
    parser.add_argument("--recursive", action="store_true",
                        help="Recurse into subdirectories (directory mode)")
    parser.add_argument("--output-dir", metavar="DIR",
                        help="Output directory for directory mode "
                             "(default: <input>_markdown)")
    parser.add_argument("--extra", action="append", default=[], metavar="NAME",
                        help="Add a markitdown extra to the uv environment "
                             "(repeatable); use 'all' for every backend")
    parser.add_argument("--json", action="store_true",
                        help="Directory mode: print a JSON summary to stdout")

    # Same names as markitdown's own CLI, forwarded verbatim in single mode.
    parser.add_argument("-o", "--output",
                        help="Output file path. Single input mode prints to "
                             "stdout when omitted")
    parser.add_argument("-x", "--extension",
                        help="Hint about the file extension (needed for stdin)")
    parser.add_argument("-m", "--mime-type", help="Hint about the MIME type")
    parser.add_argument("-c", "--charset", help="Hint about the charset")
    parser.add_argument("-d", "--use-docintel", action="store_true",
                        help="Use Azure Document Intelligence "
                             "(needs --extra az-doc-intel)")
    parser.add_argument("-e", "--endpoint",
                        default=os.environ.get("MARKITDOWN_DOCINTEL_ENDPOINT") or None,
                        help="Document Intelligence endpoint "
                             "(default: MARKITDOWN_DOCINTEL_ENDPOINT)")
    parser.add_argument("--use-cu", "--use-content-understanding",
                        action="store_true", dest="use_cu",
                        help="Use Azure Content Understanding "
                             "(needs --extra az-content-understanding)")
    parser.add_argument("--cu-endpoint",
                        default=os.environ.get("MARKITDOWN_CU_ENDPOINT") or None,
                        help="Content Understanding endpoint "
                             "(default: MARKITDOWN_CU_ENDPOINT)")
    parser.add_argument("--cu-analyzer", help="Content Understanding analyzer ID")
    parser.add_argument("--cu-file-types",
                        help="Comma-separated file types routed to Content "
                             "Understanding (e.g. pdf,jpeg,mp4)")
    parser.add_argument("-p", "--use-plugins", action="store_true",
                        help="Use 3rd-party markitdown plugins")
    parser.add_argument("--list-plugins", action="store_true",
                        help="List installed 3rd-party plugins and exit")
    parser.add_argument("--keep-data-uris", action="store_true",
                        help="Keep base64 data URIs (images) in the output "
                             "instead of truncating them")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    force_utf8_stdout()

    problem = validate_options(args)
    if problem:
        print(f"Error: {problem}", file=sys.stderr)
        sys.exit(1)

    uv_path = find_uv()
    if not uv_path:
        print("Error: uv not found. Install it first:", file=sys.stderr)
        print("  curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
        print("  Windows: uv lives under %APPDATA%\\Python\\Python3xx\\Scripts\\uv.exe",
              file=sys.stderr)
        sys.exit(1)

    spec = with_spec(args.extra)

    if args.list_plugins:
        # markitdown prints the plugin list itself; forward its exit code.
        result = subprocess.run(
            cli_command(uv_path, spec) + ["--list-plugins"], env=child_env()
        )
        sys.exit(result.returncode)

    is_stdin = args.input == "-"
    is_dir = not is_stdin and os.path.isdir(args.input)
    is_url = not is_stdin and is_uri(args.input)

    if not is_stdin and not is_dir and not is_url and not os.path.exists(args.input):
        print(f"Error: input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if is_dir:
        if args.output:
            print("Error: -o applies to single files; use --output-dir for directories",
                  file=sys.stderr)
            sys.exit(1)
        sys.exit(convert_batch(args, uv_path, spec))

    if args.output_dir:
        print("Error: --output-dir applies to directories", file=sys.stderr)
        sys.exit(1)
    if args.recursive:
        print("Error: --recursive applies to directories", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print("Error: --json applies to directory mode", file=sys.stderr)
        sys.exit(1)
    if args.output and os.path.isdir(args.output):
        print(f"Error: {args.output} is a directory; use --output-dir", file=sys.stderr)
        sys.exit(1)
    if is_stdin and not (args.extension or args.mime_type):
        # markitdown may still sniff the content, but a bare pipe usually is not
        # enough to pick a converter, so say what to add before it fails.
        print("Note: reading stdin; pass -x/--extension (e.g. -x pdf) if the "
              "format cannot be sniffed.", file=sys.stderr)

    text = convert_one(args, uv_path, spec)
    sys.exit(0 if text is not None else 1)


if __name__ == "__main__":
    main()
