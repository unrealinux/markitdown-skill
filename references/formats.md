# Format-Specific Notes

This reference contains format-specific behavior, limitations, and tips for markitdown.

## PDF

### Text-based PDFs
- **Best result**: Clean extraction with preserved headings and structure
- **Limitation**: Complex layouts (multi-column) may have reading order issues
- **If output is empty**: the PDF has no text layer (it is a scan). There is no
  `--ocr` flag — see below.

### Scanned/Image PDFs
- **markitdown has no OCR engine.** A scanned PDF converts to empty output.
- **Workaround 1 — OCR first, then convert the text layer**:
  ```bash
  pdftoppm -r 300 -png scan.pdf page
  tesseract page-1.png page-1
  # repeat per page, then concatenate or convert page-1.txt
  ```
- **Workaround 2 — Azure Document Intelligence** (best accuracy, needs creds):
  ```python
  from markitdown import MarkItDown

  converter = MarkItDown(
      docintel_endpoint="https://<your-resource>.cognitiveservices.azure.com/"
  )
  ```
  Verified against markitdown 0.1.8: the kwargs are `docintel_endpoint`,
  `docintel_credential`, `docintel_file_types`, `docintel_api_version`. There is
  no `use_azure_odai` parameter. The CLI equivalent is `--use-docintel`, and the
  endpoint can also come from `MARKITDOWN_DOCINTEL_ENDPOINT`. Needs the
  `az-doc-intel` extra.

### Password-Protected PDFs
- markitdown cannot decrypt PDFs
- **Workaround**: Remove password externally first, then convert

## Word Documents (.docx / .doc)

### .docx (Modern)
- Excellent support: headings, tables, images, lists all preserved
- Tracked changes are NOT included by default
- To include tracked changes:
  ```python
  converter = MarkItDown(include_formatting=True)
  ```

### .doc (Legacy)
- Converted via LibreOffice or antiword backend
- Complex formatting may be lost
- **Tip**: Convert to .docx first for best results:
  ```bash
  soffice --headless --convert-to docx input.doc
  ```

### Special Elements
- **Footnotes**: Extracted as markdown footnotes `[^1]`
- **Headers/Footers**: Usually omitted (as they should be)
- **Embedded objects**: Not extracted (links to them may remain)

## Excel Spreadsheets (.xlsx / .xls)

### Sheet Handling
- Only the **first sheet** is converted by default
- To convert all sheets, use markitdown directly:
  ```python
  converter = MarkItDown()
  for sheet_name in workbook.sheetnames:
      md = converter.convert(f"file.xlsx::{sheet_name}")
  ```

### Tables
- Tables are emitted as Markdown tables; there is no CSV flag in this wrapper
- Formulas are evaluated and shown as values
- Hidden rows/columns are included
- For CSV, read the workbook with `pandas.read_excel` / `openpyxl` directly

### Charts
- Charts are NOT extracted as images
- Chart data tables may appear in the markdown

## PowerPoint (.pptx / .ppt)

### Slide Structure
- Each slide becomes a `## Slide N` heading
- Speaker notes are included if present
- Bullet points are preserved

### Content
- Text boxes: Extracted in reading order
- Images: Referenced but not embedded
- Tables: Converted to markdown tables

### Legacy .ppt
- Requires LibreOffice conversion first
- May lose animations and transitions (irrelevant for text extraction)

## Images (JPG, PNG, GIF, BMP, WEBP)

### No OCR
- markitdown extracts image **metadata (EXIF)**, not text. An image containing a
  paragraph of text converts to empty output — verified: a PNG reading
  `HELLO OCR 12345` produced zero characters.
- To get text: run `tesseract image.png out` first, or send the image to a vision
  model / Azure Document Intelligence.

### Best OCR Results (with external tesseract)
- High resolution (300+ DPI)
- Clear, undistorted text
- Good contrast

### Limitations
- Handwritten text: Poor accuracy
- Very stylized fonts: May misread
- Rotated text: May not detect orientation

## HTML Files

### Conversion
- Clean HTML converts well to Markdown
- Scripts and styles are stripped
- Links become markdown links

### Complex Pages
- JavaScript-rendered content: NOT captured (only server-rendered HTML)
- **Workaround**: Use browser automation (playwright/selenium) first to generate HTML

## Audio Files (MP3, WAV, M4A)

### Requirements (markitdown 0.1.8)
- The `audio-transcription` extra: `speech_recognition` + `pydub` + **ffmpeg** on PATH
- `speech_recognition` decides the backend; with no cloud credentials configured it
  falls back to the Google Web Speech API, so transcription needs network access
- There is **no** `use_azure_transcription` or `use_local_whisper` kwarg — those
  names appear in older docs and raise nothing but confusion

### Usage
```bash
uv run --with "markitdown[audio-transcription]" markitdown meeting.mp3
```

### Limitations
- Background music/noise reduces accuracy
- Multiple speakers: Basic separation only
- Long files may exceed the free Web Speech quota (video is limited to ~1 minute)
- **Not reachable through this wrapper**, which installs no audio extra and
  exposes no transcription options; use markitdown directly.

## CSV and Plain Text

### CSV
- Direct conversion with proper column handling
- The whole file becomes one Markdown table

### Text Files
- Already in text format — markitdown passes through unchanged
- Encoding detection is automatic

## Archive Files (.zip)

### Behavior
- Archives are NOT automatically extracted
- **Workaround**: Extract first, then convert contents:
  ```bash
  unzip archive.zip -d extracted/
  markitdown extracted/
  ```

## Known Issues and Workarounds

| Issue | Cause | Workaround |
|-------|-------|------------|
| Empty output for PDF | Scanned document, no text layer | OCR first (tesseract), or Azure Doc Intelligence |
| Empty output for image | markitdown does not OCR images | OCR first, or use a vision model |
| Encoding mismatch | Source file is not UTF-8 | Re-save as UTF-8, then retry |
| Slow conversion | Large files | Process in batches |
| Missing images | Images are referenced, not extracted | Extract them from the source document yourself |
| Table formatting broken | Complex merged cells | Read the workbook with `openpyxl` |

## Performance Tips

1. **Batch processing**: pass a directory with `--output-dir` (add `--recursive` for subfolders)
2. **Parallel conversion**: run multiple instances for independent files
3. **Stream output**: single-file mode writes to stdout, so you can pipe it
4. **Warm the cache**: the first run downloads markitdown via uv; later runs reuse it
5. **Skip what you cannot read**: don't send scans or images through this tool expecting text

## Advanced Backends (markitdown 0.1.8)

All of these need `markitdown[all]` (or the specific extra) and are **not**
exposed by this skill's wrapper, which installs only
`markitdown[docx,xls,xlsx,pptx,pdf]`.

### Images via a vision model

`_image_converter.py` sends the image to a multimodal LLM when `llm_client` and
`llm_model` are both set. This is the closest thing to OCR that markitdown has:

```python
from openai import OpenAI
from markitdown import MarkItDown

converter = MarkItDown(llm_client=OpenAI(), llm_model="gpt-4o")
print(converter.convert("invoice.png").text_content)
```

Optional `llm_prompt` overrides the default instruction. `_pptx_converter.py`
accepts the same two kwargs for slide pictures.

### Azure Document Intelligence

```python
converter = MarkItDown(
    docintel_endpoint="https://<your-resource>.cognitiveservices.azure.com/",
    docintel_credential=AzureKeyCredential("<key>"),   # optional
    docintel_file_types=["pdf", "jpeg"],               # optional routing filter
    docintel_api_version="2024-11-30",                   # optional
)
```

CLI: `markitdown --use-docintel --docintel-endpoint <url> file.pdf`.
Requires the `az-doc-intel` extra.

### Azure Content Understanding

CLI flags `--use-cu` / `--cu-endpoint` / `--cu-analyzer` / `--cu-file-types`, with
`MARKITDOWN_CU_ENDPOINT` as the environment fallback. Requires the
`az-content-understanding` extra.

### Metadata extraction

`MarkItDown(exiftool_path="/usr/bin/exiftool")` lets the image and audio
converters report EXIF/metadata; without exiftool they return no metadata at all.
