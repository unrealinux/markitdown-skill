---
name: markitdown
description: "Use this skill whenever the user wants to read, extract, or convert any document file to Markdown. Triggers include: any mention of 'PDF', 'Word', 'docx', 'doc', 'PowerPoint', 'pptx', 'Excel', 'xlsx', 'spreadsheet', 'image with text', 'scan', 'OCR', 'extract text', 'convert to markdown', 'read this document', 'what is in this file', 'summarize this document'. Also triggers when the user provides a file path and asks to see its content in text form. Use for any document format that needs to be transformed into readable Markdown."
license: MIT (from microsoft/markitdown)
---

# MarkItDown — Document to Markdown Converter

A universal document reader powered by [microsoft/markitdown](https://github.com/microsoft/markitdown). Converts files of all formats into clean, structured Markdown.

## Quick Reference

| Task | Approach |
|------|----------|
| **Convert single file** | Run `scripts/convert.py <file>` |
| **Batch convert folder** | Run `scripts/convert.py <folder>` |
| **Extract tables only** | Add `--tables` flag |
| **Extract images** | Add `--images <dir>` flag |
| **OCR on scanned docs** | Add `--ocr` flag (auto-enabled for images/PDFs with no text) |

## Prerequisites

**Python 3.10+ is required** for markitdown. This skill uses `uv` for Python/environment management.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify Python 3.12 is available
~/.local/bin/uv python list
```

markitdown package is auto-installed on first use via uv.

## Usage

### Basic conversion

```bash
# Convert a single file to stdout
python3 <skill_dir>/scripts/convert.py document.pdf

# Save to file
python3 <skill_dir>/scripts/convert.py document.docx -o output.md
```

### Batch conversion

```bash
# Convert all files in a directory
python3 <skill_dir>/scripts/convert.py /path/to/folder -o ./output/

# Wildcard patterns
python3 <skill_dir>/scripts/convert.py *.pdf --output-dir ./markdown/
```

### Content extraction

```bash
# Extract only tables (returns CSV format)
python3 <skill_dir>/scripts/convert.py data.xlsx --tables

# Extract and save images to a directory
python3 <skill_dir>/scripts/convert.py scanned.pdf --images ./images/

# Force OCR (useful for image-based PDFs)
python3 <skill_dir>/scripts/convert.py scan.jpg --ocr
```

## Supported Formats

See `references/formats.md` for detailed format-specific notes.

| Category | Formats | Notes |
|----------|---------|-------|
| Documents | `.pdf`, `.docx`, `.doc` | PDF OCR requires `pdf2image` + `pytesseract` |
| Spreadsheets | `.xlsx`, `.xls`, `.csv` | Tables extracted with structure preserved |
| Presentations | `.pptx`, `.ppt` | Slides converted to ordered Markdown |
| Images | `.jpg`, `.png`, `.gif`, `.bmp`, `.webp` | Auto-OCR if text detected |
| Web | `.html`, `.htm` | Stripped of scripts/styles |
| Archives | `.zip` (with documents) | Extracts and converts contained files |
| Audio | `.mp3`, `.wav`, `.m4a` | Speech-to-text via Azure or local |

## Script Reference

The bundled script at `scripts/convert.py` wraps markitdown with sensible defaults:

```bash
~/.local/bin/uv run --with markitdown --python 3.12 python scripts/convert.py INPUT [-o OUTPUT] [--tables] [--ocr] [--recursive] [--output-dir DIR]
```

Or set up an alias for convenience:
```bash
alias markitdown='~/.local/bin/uv run --with markitdown --python 3.12 python ~/.agents/skills/markitdown/scripts/convert.py'
markitdown document.pdf -o output.md
```

## Error Handling

Common issues and fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: markitdown` | Package not installed | Run `pip3 install markitdown` |
| `pdf2image` missing | OCR on PDFs | Install `pip3 install pdf2image pytesseract` + system tesseract |
| Blank output from PDF | Scanned/image PDF without OCR | Use `--ocr` flag |
| Encoding warnings | Non-standard document encoding | Try `--ocr` or convert to PDF first |

## Workflow Examples

### "Read this PDF and tell me what's in it"
```bash
python3 <skill_dir>/scripts/convert.py report.pdf | head -50
```

### "Extract all tables from this Excel file"
```bash
python3 <skill_dir>/scripts/convert.py data.xlsx --tables
```

### "Convert my scanned invoice to text"
```bash
python3 <skill_dir>/scripts/convert.py invoice.jpg --ocr
```

### "Turn this folder of docs into Markdown"
```bash
python3 <skill_dir>/scripts/convert.py ./documents --output-dir ./markdown --recursive
```

## When to Use This Skill

Use markitdown instead of raw tools when:
- You need a **single tool** for multiple document formats
- The document is in an **unusual or legacy format** (.doc, .ppt)
- You want **clean Markdown output** rather than raw text extraction
- The user hasn't specified which format tool to use

Prefer direct tools (pypdf, python-docx, etc.) when:
- You need to **modify/create** documents (not just read)
- You need **pixel-perfect** PDF layout preservation
- Working with very large files where markitdown may be slow

## Next Steps

- For format-specific details and known limitations, read `references/formats.md`
- For programmatic Python usage, see the [markitdown GitHub](https://github.com/microsoft/markitdown)
- For advanced OCR configuration, see the references file
