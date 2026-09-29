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


def pe_imports(path):
    """DLL names a PE file imports, or [] when it is not a PE we can read.

    Used to prove the bundle carries every non-mangled VC++ runtime DLL its own
    wheels ask for — onnxruntime imports MSVCP140.dll by plain name and does not
    ship it, which only fails on machines without the VC++ redistributable.
    """
    import struct

    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return []
    if data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    coff = pe + 4
    sections_count = struct.unpack_from("<H", data, coff + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        directories = optional + 112
    elif magic == 0x10B:
        directories = optional + 96
    else:
        return []
    import_rva = struct.unpack_from("<I", data, directories + 8)[0]
    if not import_rva:
        return []

    sections = []
    table = optional + optional_size
    for index in range(sections_count):
        base = table + index * 40
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, base + 8)
        sections.append((va, max(vsize, rawsize), raw))

    def to_offset(rva):
        for va, size, raw in sections:
            if va <= rva < va + size:
                return raw + (rva - va)
        return None

    offset = to_offset(import_rva)
    if offset is None:
        return []
    names = []
    while True:
        entry = struct.unpack_from("<IIIII", data, offset)
        if not any(entry):
            break
        name_offset = to_offset(entry[3])
        if name_offset is not None:
            end = data.index(b"\0", name_offset)
            names.append(data[name_offset:end].decode("ascii", "replace"))
        offset += 20
    return names


def missing_vc_runtime(root):
    """Non-mangled MSVCP*/CONCRT* imports that the bundle itself does not satisfy."""
    present = set()
    imported = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            present.add(name.lower())
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if not name.lower().endswith((".dll", ".pyd", ".exe")):
                continue
            full = os.path.join(dirpath, name)
            for imported_name in pe_imports(full):
                upper = imported_name.upper()
                # The mangled per-wheel copies (msvcp140-<hash>.dll) are bundled
                # by numpy/pandas themselves; only the plain names matter here.
                if upper.startswith(("MSVCP", "CONCRT")) and "-" not in imported_name:
                    imported.setdefault(imported_name, set()).add(full)
    return {name: users for name, users in imported.items()
            if name.lower() not in present}


def bundle_vc_runtime(root):
    """Copy the VC++ runtime DLLs the bundle imports but does not ship.

    onnxruntime.dll and onnxruntime_pybind11_state.pyd import MSVCP140.dll and
    MSVCP140_1.dll by plain name and ship neither, so on a machine without the
    VC++ 2015-2022 redistributable markitdown dies the moment magika loads
    onnxruntime. This machine has the redistributable, which is exactly how the
    gap stayed invisible until the import tables were read out of the binaries.
    The DLL search finds a module's own directory first, so a copy next to
    python.exe and next to onnxruntime.dll settles it. These DLLs are
    redistributable with an application under the Visual C++ license.
    """
    if sys.platform != "win32":
        return {}
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    missing = missing_vc_runtime(root)
    if not missing:
        print("  every imported VC++ runtime DLL is already inside the bundle")
        return {}

    targets = [root, os.path.join(root, "Lib", "site-packages", "onnxruntime", "capi")]
    copied = {}
    for name, users in sorted(missing.items()):
        source = os.path.join(system32, name)
        if not os.path.exists(source):
            raise SystemExit(f"{name} is imported by {len(users)} bundled binary(ies) "
                             f"but was not found in {system32}")
        for target in targets:
            if os.path.isdir(target):
                shutil.copy2(source, os.path.join(target, name))
        copied[name] = os.path.getsize(source)
        print(f"  + {name}: {os.path.getsize(source) / 1024:.0f} KiB "
              f"(needed by {', '.join(os.path.basename(u) for u in list(users)[:2])})")

    still_missing = missing_vc_runtime(root)
    if still_missing:
        raise SystemExit(f"VC++ runtime still unresolved: {sorted(still_missing)}")
    return copied


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

    print(f"1/6 standalone Python {args.python_version} ({args.label})")
    root = install_interpreter(uv, install_root, args.python_version, args.keep_python)
    python = interpreter_path(root)
    print(f"  interpreter: {python}")

    print(f"2/6 markitdown[{','.join(extras)}]")
    if args.skip_install:
        print("  skipped")
    else:
        install_packages(python, extras)

    print("3/6 trim")
    trim(root)

    print("4/6 VC++ runtime")
    bundle_vc_runtime(root)

    print("5/6 sanity check")
    sanity_check(python)

    print("6/6 package")
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
