#!/usr/bin/env python3
"""Build the offline bundle: a standalone Python with markitdown inside the skill.

    py scripts/build_offline_bundle.py                    # win-x64 default label
    py scripts/build_offline_bundle.py --keep-python       # reuse the interpreter
    py scripts/build_offline_bundle.py --extras docx,pdf   # smaller bundle

The result is `dist/markitdown-<version>-offline-<label>.zip` (label defaults to
the current platform, e.g. `offline-win-x64`). It runs on a machine with **no
network, no Python and no uv**: the archive contains a standalone CPython under
`vendor/python/` with markitdown already installed, and convert.py prefers that
interpreter over uv.

This script itself needs network once — it downloads the interpreter and the
wheels. Set UV_DEFAULT_INDEX (or PIP_INDEX_URL) to use a mirror.

Trimming is deliberate and verified afterwards. `pip`, `Scripts/` and the
Tcl/Tk/idle tooling are dead weight for a headless converter, and sympy+mpmath
(70 MiB) are only onnxruntime's symbolic shape tools, not its inference path —
the sanity check below imports onnxruntime and converts every fixture, so a bad
trim fails the build instead of the user's first conversion.
"""

import argparse
import glob
import importlib.util
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(SKILL_ROOT, "evals", "fixtures")

# Removed from the bundled interpreter. Relative to the interpreter root; missing
# entries are skipped, so one list serves Windows, macOS and Linux layouts.
TRIM = [
    "Scripts", "bin",
    "Lib/tkinter", "Lib/idlelib", "Lib/lib2to3", "Lib/ensurepip",
    "Lib/site-packages/pip",
    "Lib/site-packages/sympy", "Lib/site-packages/mpmath",
    "tcl",
]

# Fixture files the sanity check converts. Every one of these exercises a
# different converter (text, docx, xlsx, pdf, pptx, zip, html).
SANITY_FIXTURES = [
    "sample.txt", "sample.docx", "sample.xlsx", "sample.pdf",
    "sample.pptx", "sample.zip", "sample.html",
]


def load_module(name, path):
    """Import a sibling script without requiring a package or changing sys.path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(cmd, **kwargs):
    print("  $", " ".join(str(part) for part in cmd))
    return subprocess.run(cmd, **kwargs)


def install_interpreter(uv, install_root, python_version, keep):
    """Return the path to a standalone interpreter, installing it if needed."""
    existing = sorted(glob.glob(os.path.join(install_root, "cpython-*")))
    for candidate in existing:
        for relative in ("python.exe", "bin/python3", "python3"):
            if os.path.exists(os.path.join(candidate, relative)):
                if keep:
                    print(f"  reusing {candidate}")
                    return candidate
    if existing and not keep:
        shutil.rmtree(install_root, ignore_errors=True)

    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = install_root
    result = run([uv, "python", "install", python_version], env=env)
    if result.returncode != 0:
        raise SystemExit("could not install a standalone interpreter")

    for candidate in sorted(glob.glob(os.path.join(install_root, "cpython-*"))):
        for relative in ("python.exe", "bin/python3", "python3"):
            if os.path.exists(os.path.join(candidate, relative)):
                return candidate
    raise SystemExit(f"interpreter not found under {install_root}")


def interpreter_path(root):
    for relative in ("python.exe", "bin/python3", "python3"):
        candidate = os.path.join(root, relative)
        if os.path.exists(candidate):
            return candidate
    raise SystemExit(f"no python executable under {root}")


def install_packages(python, extras):
    """Install markitdown and its format extras into the bundled interpreter."""
    requirement = "markitdown[" + ",".join(extras) + "]"
    cmd = [python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
           "--break-system-packages", "--no-warn-script-location", requirement]

    # pip does not read UV_* variables, so forward a mirror if one is configured.
    mirror = os.environ.get("UV_DEFAULT_INDEX") or os.environ.get("PIP_INDEX_URL")
    if mirror:
        cmd += ["--index-url", mirror]
        print(f"  using index: {mirror}")
    result = run(cmd)
    if result.returncode != 0:
        raise SystemExit("pip install failed (network needed for this step)")


def trim(root):
    """Delete the parts a headless converter never touches."""
    freed = 0
    for relative in TRIM:
        target = os.path.join(root, *relative.split("/"))
        if not os.path.exists(target):
            continue
        size = sum(os.path.getsize(os.path.join(d, f))
                   for d, _, fs in os.walk(target) for f in fs)
        shutil.rmtree(target, ignore_errors=True)
        freed += size
        print(f"  - {relative}: {size / 1024 / 1024:.1f} MiB")
        # Leave no metadata claiming a package that is gone.
        name = os.path.basename(relative)
        for stale in glob.glob(os.path.join(root, "Lib", "site-packages",
                                            f"{name}-*.dist-info")):
            shutil.rmtree(stale, ignore_errors=True)
    print(f"  trimmed {freed / 1024 / 1024:.1f} MiB")


def sanity_check(python):
    """Prove the trimmed bundle still converts every fixture."""
    fixture_paths = [os.path.join(FIXTURES, name) for name in SANITY_FIXTURES]
    missing = [path for path in fixture_paths if not os.path.exists(path)]
    if missing:
        raise SystemExit(f"missing fixtures (run evals/make_fixtures.py): {missing}")

    snippet = (
        "import json, sys\n"
        "import onnxruntime\n"
        "from markitdown import MarkItDown\n"
        "paths = json.loads(sys.argv[1])\n"
        "converter = MarkItDown()\n"
        "for path in paths:\n"
        "    converter.convert(path)\n"
        "print('sanity ok:', len(paths), 'files, onnxruntime',\n"
        "      onnxruntime.__version__, ', python', sys.version.split()[0])\n"
    )
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [python, "-c", snippet, __import__("json").dumps(fixture_paths)],
        capture_output=True, encoding="utf-8", errors="replace", env=env,
    )
    if result.returncode != 0:
        print((result.stdout or "") + (result.stderr or ""), file=sys.stderr)
        raise SystemExit("sanity check failed after trimming")
    print("  " + (result.stdout or "").strip())


def dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def default_label():
    system = {"Windows": "win", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system(), platform.system().lower())
    machine = {"AMD64": "x64", "x86_64": "x86_64", "arm64": "arm64",
               "aarch64": "arm64"}.get(platform.machine(), platform.machine().lower())
    return f"offline-{system}-{machine}"


def main():
    convert = load_module("markitdown_convert", os.path.join(HERE, "convert.py"))
    packaging = load_module("markitdown_packaging",
                            os.path.join(HERE, "package_skill.py"))
    # Building without UTF-8 stdio dies on the first emoji under cp936 — the same
    # trap convert.py and package_skill.py document. Reuse theirs rather than
    # adding a third copy.
    convert.force_utf8_stdout()

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python-version", default="3.12",
                        help="Interpreter version to bundle (default: 3.12)")
    parser.add_argument("--extras", default=",".join(convert.BASE_EXTRAS),
                        help="markitdown extras baked into the bundle")
    parser.add_argument("--label", default=default_label(),
                        help="File-name suffix (default: platform based)")
    parser.add_argument("--build-dir", default=os.path.join(SKILL_ROOT, "build"),
                        help="Where the interpreter tree is assembled")
    parser.add_argument("--out", default=os.path.join(SKILL_ROOT, "dist"),
                        help="Where the zip is written")
    parser.add_argument("--keep-python", action="store_true",
                        help="Reuse an interpreter from a previous run")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip pip (interpreter already prepared)")
    args = parser.parse_args()

    uv = convert.find_uv()
    if not uv:
        raise SystemExit("uv is required to fetch the standalone interpreter")

    install_root = os.path.join(args.build_dir, args.label)
    extras = [extra.strip() for extra in args.extras.split(",") if extra.strip()]

    print(f"1/5 standalone Python {args.python_version} ({args.label})")
    root = install_interpreter(uv, install_root, args.python_version, args.keep_python)
    python = interpreter_path(root)
    print(f"  interpreter: {python}")

    print(f"2/5 markitdown[{','.join(extras)}]")
    if args.skip_install:
        print("  skipped")
    else:
        install_packages(python, extras)

    print("3/5 trim")
    trim(root)

    print("4/5 sanity check")
    sanity_check(python)

    print("5/5 package")
    frontmatter = packaging.read_frontmatter(os.path.join(SKILL_ROOT, "SKILL.md"))
    version = frontmatter.get("metadata.version") or "0.0.0"
    folder = frontmatter.get("name") or "markitdown"
    files = packaging.collect_files(SKILL_ROOT)
    entries = [(os.path.join(SKILL_ROOT, rel), rel) for rel in files]
    vendor_entries = packaging.collect_vendor(root)
    entries += vendor_entries

    out_path = os.path.join(args.out, f"{folder}-{version}-{args.label}.zip")
    digest = packaging.build(SKILL_ROOT, out_path, folder, entries)

    vendor_bytes = sum(os.path.getsize(source) for source, _ in vendor_entries)
    print(f"\n📦 {out_path}")
    print(f"   version: {version}   label: {args.label}")
    print(f"   skill files: {len(files)}")
    print(f"   bundled interpreter: {vendor_bytes / 1024 / 1024:.1f} MiB "
          f"({len(vendor_entries)} files)")
    print(f"   archive size: {os.path.getsize(out_path) / 1024 / 1024:.1f} MiB")
    print(f"   sha256: {digest}")
    print("\n   On the target machine: unzip anywhere and run")
    print(f"     {folder}\\scripts\\convert.py your-document.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
