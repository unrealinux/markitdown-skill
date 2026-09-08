# Format-Specific Notes

This reference contains format-specific behavior, limitations, and tips for markitdown.

## PDF

### Text-based PDFs
- **Best result**: Clean extraction with preserved headings and structure
- **Tip**: If text extraction fails, try `--ocr` flag
- **Limitation**: Complex layouts (multi-column) may have reading order issues

### Scanned/Image PDFs
- **Requirement**: `--ocr` flag needed
- **Dependencies**: `pip3 install pdf2image pytesseract` + system `tesseract`
- **Alternative**: Use Azure backend for better accuracy:
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
- Use `--tables` flag for clean CSV extraction
- Formulas are evaluated and shown as values
- Hidden rows/columns are included

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

### Automatic OCR
- markitdown auto-detects text in images
- No `--ocr` flag needed for images (unlike PDFs)
- Accuracy depends on image quality and resolution

### Best Results
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

## CSV and Plain Text

### CSV
- Direct conversion with proper column handling
- Use `--tables` flag for cleaner output

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
| Empty output for PDF | Scanned document | Use `--ocr` |
| Encoding warnings | Non-UTF8 files | Convert to UTF-8 first |
| Slow conversion | Large files | Process in batches |
| Missing images | Image references broken | Check original file paths |
| Table formatting broken | Complex merged cells | Use `--tables` flag |

## Performance Tips

1. **Batch processing**: Use `--recursive` for directories
2. **Parallel conversion**: Run multiple instances for independent files
3. **Stream output**: Use stdout for piped processing
4. **Skip unnecessary formats**: Don't use OCR if not needed

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
