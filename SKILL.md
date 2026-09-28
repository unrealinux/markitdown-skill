---
name: markitdown
description: "Use this skill whenever the user wants to read, extract, or convert any document file to Markdown. Triggers include: any mention of 'PDF', 'Word', 'docx', 'doc', 'PowerPoint', 'pptx', 'Excel', 'xlsx', 'spreadsheet', 'image with text', 'scan', 'OCR', 'extract text', 'convert to markdown', 'read this document', 'what is in this file', 'summarize this document'. Also triggers when the user provides a file path and asks to see its content in text form. Use for any document format that needs to be transformed into readable Markdown."
license: MIT (see LICENSE; markitdown itself is MIT © Microsoft and is installed at runtime)
compatibility: Requires Python 3.10+ and uv; the first run downloads markitdown from PyPI, so it needs network access (later runs use the uv cache).
metadata:
  version: 0.1.0
  author: unrealinux
  homepage: https://github.com/unrealinux/markitdown-skill
---

# MarkItDown — Document to Markdown Converter

A universal document reader powered by [microsoft/markitdown](https://github.com/microsoft/markitdown). Converts files of all formats into clean, structured Markdown.

## Quick Reference

| Task | Approach |
|------|----------|
| **Convert a file, URL or stdin** | `scripts/convert.py <file-or-url>` — Markdown to stdout; `-` reads stdin, `-x pdf` hints the format |
| **Save to a file** | Add `-o output.md` |
| **Batch convert folder** | `scripts/convert.py <folder> --output-dir <dir>` (default: `<folder>_markdown`) |
| **Include subfolders** | Add `--recursive` (output mirrors the input tree) |
| **Machine-readable batch report** | Add `--json` (JSON on stdout, progress stays on stderr) |
| **Reach another markitdown backend** | Add `--extra <name>`: `audio-transcription`, `outlook`, `az-doc-intel`, `az-content-understanding`, `all` |
| **Azure Document Intelligence** | `--use-docintel -e <endpoint>` plus `--extra az-doc-intel` |
| **Azure Content Understanding** | `--use-cu --cu-endpoint <endpoint>` plus `--extra az-content-understanding` |
| **Third-party plugins** | `-p`, or `--list-plugins` to see what is installed |
| **Keep base64 images** | `--keep-data-uris` (the default truncates data URIs) |
| **Custom DOCX styles** | `--style-map "p[style-name='Quote'] => blockquote"` — constructs `MarkItDown(style_map=...)` |

**Not provided:** OCR and CSV export. markitdown ships no OCR engine — scanned PDFs and pictures of text come back empty. See [Limitations](#limitations).

## Prerequisites

**Python 3.10+ is required** for markitdown. This skill uses `uv` for Python/environment management.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify Python 3.12 is available
~/.local/bin/uv python list
```

markitdown package is auto-installed on first use via uv, as
`markitdown[docx,xls,xlsx,pptx,pdf]`. The extras matter: the bare package cannot
read `.docx`, `.xlsx`, `.pptx` or `.pdf` and raises `MissingDependencyException`.
Expect a 1-2 minute download on the very first conversion; later runs hit the cache.

**Windows:** use `py` (the `python` on PATH is the Windows Store stub and prints nothing) and no `~/.local/bin` prefix. uv usually lives at `%APPDATA%\Python\Python3xx\Scripts\uv.exe`, and this wrapper asks uv for Python 3.12 explicitly. Every example below writes `python3`; on Windows substitute `py`. Example:

```bash
py "<skill_dir>/scripts/convert.py" document.pdf -o output.md
```

## Usage

### Basic conversion

```bash
# Markdown to stdout
python3 <skill_dir>/scripts/convert.py document.pdf

# Save to file
python3 <skill_dir>/scripts/convert.py document.docx -o output.md
```

### URL, stdin and streaming

`http:`, `https:`, `file:` and `data:` inputs are passed to markitdown as-is;
it fetches or decodes them itself.

```bash
python3 <skill_dir>/scripts/convert.py https://example.com/report.pdf
python3 <skill_dir>/scripts/convert.py "data:text/plain;base64,aGVsbG8="

# stdin: '-' plus a format hint when the content cannot be sniffed
cat report.pdf | python3 <skill_dir>/scripts/convert.py - -x pdf
```

### Other backends (`--extra`)

Each of these adds one markitdown extra to the uv environment for that run:

```bash
# Audio transcription (speech_recognition + pydub; ffmpeg on PATH for mp3/mp4)
python3 <skill_dir>/scripts/convert.py meeting.mp3 --extra audio-transcription

# Outlook .msg
python3 <skill_dir>/scripts/convert.py mail.msg --extra outlook

# Azure Document Intelligence / Content Understanding
python3 <skill_dir>/scripts/convert.py scan.pdf --extra az-doc-intel -d -e "$MARKITDOWN_DOCINTEL_ENDPOINT"
python3 <skill_dir>/scripts/convert.py scan.pdf --extra az-content-understanding --use-cu --cu-endpoint "$MARKITDOWN_CU_ENDPOINT"

# Every backend at once (large download; only the first run pays it)
python3 <skill_dir>/scripts/convert.py scan.pdf --extra all

# DOCX style mapping (documented in references/formats.md)
python3 <skill_dir>/scripts/convert.py report.docx --style-map "p[style-name='Quote'] => blockquote"
```

`--style-map` is the one option markitdown's CLI cannot express, so that input is
run through this wrapper's own snippet (batch mode uses the same code path). Its
output is byte-identical to `MarkItDown(style_map=...).convert(...)`, verified by
eval 27.

### Batch conversion

```bash
# One .md per supported file (top level only)
python3 <skill_dir>/scripts/convert.py /path/to/folder --output-dir ./output

# Include subdirectories; output mirrors the input tree, so same-named
# files in different folders no longer overwrite each other
python3 <skill_dir>/scripts/convert.py /path/to/folder --output-dir ./markdown --recursive
```

Batch mode converts every file inside **one** interpreter, because importing
markitdown costs about 5 seconds on its own. Measured on this machine: 4 files
went from 21.9s to 6.0s, and 101 files finish in ~9s. A failed file is reported on
its own line while the rest still convert; the exit code is 1 if any file failed.
Files that directory mode will not convert are listed first, with the reason
(`unsupported extension`, `already Markdown`). `--json` prints the same summary
as JSON on stdout instead of only human-readable stderr lines.

Single-file mode cannot avoid that import, so expect ~6-9 seconds even for a tiny
file. That delay is normal — do not kill the process and retry.

## Limitations

- **No OCR engine.** A scanned PDF or an image of text converts to empty output.
  Three routes that actually work, none of them a flag on this wrapper:
  - OCR first: `tesseract page.png out`, then convert the text.
  - Vision model: `MarkItDown(llm_client=client, llm_model="gpt-4o")` — the image
    converter sends pictures to an LLM (see `references/formats.md`).
  - Azure Document Intelligence: `MarkItDown(docintel_endpoint="https://<resource>.cognitiveservices.azure.com/")`,
    or the CLI's `--use-docintel`, with `MARKITDOWN_DOCINTEL_ENDPOINT` as the
    environment fallback. Note: there is no `use_azure_odai` parameter in 0.1.8.
- **No CSV export.** Spreadsheets and tables come back as Markdown tables. Use
  `pandas` or `openpyxl` directly when you need CSV.
- **No image extraction.** Images inside documents are referenced, not written to disk.
- **No audio transcription by default.** `.mp3` / `.wav` / `.m4a` / `.mp4` return
  metadata only (usually nothing) unless you add `--extra audio-transcription`.
  The missing dependency is swallowed, so without the extra you get empty output
  and exit code 0 rather than an error.
- **`.doc` / `.ppt` are not supported.** markitdown 0.1.8 has no converter for
  them and **no LibreOffice path** — they raise `UnsupportedFormatException`.
  Convert to `.docx` / `.pptx` first. Directory mode lists them as skipped.
- **Images are `.jpg` / `.jpeg` / `.png` only.** Those three are the extensions
  the image converter accepts; other image formats are not read at all.
- **`.md` / `.markdown` are skipped in directory mode.** Converting them would be
  a byte-for-byte copy, and with `--output-dir` pointing at the input it could
  overwrite the source. Single-file mode still converts them on request.
- **Empty output is not an error.** A scanned page, an image, or audio without
  the transcription extra converts to zero characters with exit code 0.
  Single-file mode says so on stderr; batch mode prints `⚠️ ... (0 chars ...)`
  and counts an `N empty` total instead of a clean `✅`.

## Supported Formats

See `references/formats.md` for detailed format-specific notes.

| Category | Formats | Notes |
|----------|---------|-------|
| Documents | `.pdf`, `.docx` | PDF needs a text layer (no OCR) |
| Spreadsheets | `.xlsx`, `.xls`, `.csv` | Every sheet becomes a Markdown table |
| Presentations | `.pptx` | Each slide marked with `<!-- Slide number: N -->` |
| Web / text | `.html`, `.htm`, `.txt`, `.text`, `.json`, `.jsonl`, `.xml` | Scripts and styles stripped; `text/*` passes through |
| Notebooks / books / mail | `.ipynb`, `.epub`, `.msg` | `.msg` needs `--extra outlook` |
| Images | `.jpg`, `.jpeg`, `.png` | Metadata only — **no OCR**, text in images is lost |
| Audio / video | `.mp3`, `.wav`, `.m4a`, `.mp4` | Metadata only unless `--extra audio-transcription` |
| Archives | `.zip` | Auto-unpacked, each entry under `## File:` |
| Not supported | `.doc`, `.ppt` | no LibreOffice path; raises `UnsupportedFormatException` |

## Script Reference

The bundled script at `scripts/convert.py` wraps markitdown, and does its own
`uv run`, so there is no need to launch it through uv:

```bash
python3 scripts/convert.py INPUT [-o OUTPUT] [--output-dir DIR] [--recursive]
    [--json] [--extra NAME]... [-x EXT] [-m MIME] [-c CHARSET]
    [-d -e ENDPOINT] [--use-cu --cu-endpoint ENDPOINT] [-p] [--keep-data-uris]
```

Or set up an alias for convenience. The script runs uv itself, so the alias is
just a path to this skill's copy of the script (`python3` on Unix, `py` on
Windows):

```bash
alias markitdown='python3 scripts/convert.py'   # from the skill directory
markitdown document.pdf -o output.md
```

## Error Handling

Common issues and fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| `uv not found` | uv missing or not on PATH | Install uv; on Windows it lives under `%APPDATA%\Python\Python3xx\Scripts\uv.exe` |
| `MissingDependencyException` (`markitdown[docx]` hint) | markitdown installed without format extras | The wrapper pins `markitdown[docx,xls,xlsx,pptx,pdf]`; a bare `pip install markitdown` cannot read Office files or PDFs |
| `Conversion failed: UnsupportedFormatException` | File type markitdown cannot read | Convert to PDF or `.docx` first |
| Blank output from PDF | Scanned PDF without a text layer | OCR it first — this wrapper has no OCR |
| Blank output from image | markitdown never OCRs images | OCR it first (`tesseract`) |
| `UnicodeEncodeError: 'gbk' codec` | Older wrapper without UTF-8 stdio | Update `scripts/convert.py` (it sets `PYTHONUTF8=1`) |
| `UnicodeDecodeError` reading the `.md` | Source file is not UTF-8 | Re-save the source as UTF-8, then retry |

## Workflow Examples

### "Read this PDF and tell me what's in it"
```bash
python3 <skill_dir>/scripts/convert.py report.pdf | head -50
```

### "Extract the data from this Excel file"
```bash
python3 <skill_dir>/scripts/convert.py data.xlsx -o data.md
```
Returns Markdown tables. For CSV, use `pandas` or `openpyxl` directly.

### "Convert my scanned invoice to text"
```bash
# No OCR here: OCR first, then convert the text layer
tesseract invoice.png invoice --psm 6
python3 <skill_dir>/scripts/convert.py invoice.txt
```

### "Turn this folder of docs into Markdown"
```bash
python3 <skill_dir>/scripts/convert.py ./documents --output-dir ./markdown --recursive
```

## Evals

`evals/run_evals.py` drives this wrapper over generated fixtures and asserts the
converted text. Fixtures are built by stdlib only, so a fresh clone can run them:

```bash
python3 evals/make_fixtures.py && python3 evals/run_evals.py
```

The stdlib-built fixtures (txt, csv, html, docx, pdf, png, directory tree) need no
network. `sample.xlsx` and `sample.pptx` are generated through uv with
`openpyxl` + `python-pptx`, because hand-rolled OOXML has to satisfy those
readers exactly; if uv or the network is unavailable the two office evals are
reported as SKIP rather than failed.

Covers 29 evals: txt / csv / html / docx / pdf / xlsx / pptx text extraction
(the xlsx fixture has two sheets, so a first-sheet-only regression fails); a
`.zip` that must come back auto-unpacked under `## File:`; batch mode with nested
directories (same-named files must not overwrite, hidden directories skipped,
nothing leaked to stdout, and skipped files reported with a reason); a directory
holding one corrupt `.docx` (the good file must still convert, the bad one must
not be written, exit code 1, root cause in stderr); `-o` writing a file while
stdout stays empty; the no-OCR limitation for images, plus a silent WAV, both
asserted as empty output **with** the stderr warning and exit code 0; a footnoted
`.docx` that must render as `[[1]](#footnote-1)` + a trailing list and never as
`[^1]`; a `data:` URI, stdin with `-x`, and the `--help` surface; `--json`
batch output (counts per bucket, plus the default `<input>_markdown` output
directory); a `--style-map` run that must match the direct
`MarkItDown(style_map=...)` output; the packaging script's archive manifest
(single top-level `markitdown/` folder, no build junk); and four source-level
guards that fail the run
when the wrapper drops `--python 3.12`, loses URI/`--extra`/skip-report support,
or when the docs reintroduce a parameter markitdown does not have or a format
claim that contradicts 0.1.8.

## When to Use This Skill

Use markitdown instead of raw tools when:
- You need a **single tool** for multiple document formats
- The input is a **URL or a stream**, not a local file
- You want **clean Markdown output** rather than raw text extraction
- The user hasn't specified which format tool to use

Prefer direct tools (pypdf, python-docx, etc.) when:
- You need to **modify/create** documents (not just read)
- You need **pixel-perfect** PDF layout preservation
- Working with very large files where markitdown may be slow

## Next Steps

- For format-specific details and known limitations, read `references/formats.md`
- For programmatic Python usage, see the [markitdown GitHub](https://github.com/microsoft/markitdown)
- For a backend that needs constructor kwargs this wrapper does not expose
  (`llm_client`/`llm_model` for vision; `exiftool_path` — set `EXIFTOOL_PATH` or
  put exiftool on PATH instead), add the matching `--extra` and call the
  markitdown Python API directly. `style_map` is exposed: `--style-map`.
