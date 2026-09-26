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
  converter = MarkItDown(use_azure_odai=True)
  ```

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

### Requirements
- Azure Speech Services API key, OR
- Local Whisper model (`pip3 install openai-whisper`)

### Usage
```python
converter = MarkItDown(use_azure_transcription=True)
# or local whisper:
converter = MarkItDown(use_local_whisper=True)
```

### Limitations
- Background music/noise reduces accuracy
- Multiple speakers: Basic separation only
- Long files: May time out without Azure backend
- **Not reachable through this wrapper**, which exposes no transcription options;
  call the markitdown Python API directly.

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

## Azure Backend (Advanced)

For production use with better accuracy:

```python
from markitdown import MarkItDown

# Azure Document Intelligence
converter = MarkItDown(
    use_azure_odai=True,
    azure_endpoint="https://<your-resource>.cognitiveservices.azure.com/",
    azure_model="prebuilt-read"
)

# Azure Speech Translation
converter = MarkItDown(
    use_azure_transcription=True,
    azure_speech_key="your-key",
    azure_speech_region="eastus"
)
```

Requires: `pip3 install "markitdown[all]"` and Azure credentials.
