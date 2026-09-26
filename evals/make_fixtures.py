#!/usr/bin/env python3
"""Generate the fixtures used by evals/run_evals.py.

Standard library only, so the evals are reproducible on any machine:

    py evals/make_fixtures.py      # or python3 evals/make_fixtures.py

Rebuilds evals/fixtures/ from scratch every run.
"""

import os
import shutil
import struct
import sys
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def setup_stdio():
    """Force UTF-8 so fixture content with emoji cannot break this script."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def write_png(path, width=64, height=32, rgb=(0, 0, 0)):
    """Write a tiny solid-colour PNG (no text: markitdown has no OCR)."""
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    blob = b"\x89PNG\r\n\x1a\n"
    blob += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    blob += chunk(b"IDAT", zlib.compress(raw, 9))
    blob += chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(blob)


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def paragraph(text, style=None):
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return (
        f"<w:p>{properties}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"
    )


def table(rows):
    cells = "".join(
        "<w:tr>"
        + "".join(
            f'<w:tc><w:p><w:r><w:t xml:space="preserve">{value}</w:t></w:r></w:p></w:tc>'
            for value in row
        )
        + "</w:tr>"
        for row in rows
    )
    return f"<w:tbl>{cells}</w:tbl>"


def write_docx(path):
    """Build a minimal but valid .docx (heading, paragraph, table)."""
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + paragraph("Fixture Heading", style="Heading1")
        + paragraph("Fixture paragraph with 中文 and 😀 preserved.")
        + table([["Alpha", "Beta"], ["1", "2"]])
        + "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", document)


def write_pdf(path, text="PDF fixture text 12345"):
    """Write a minimal single-page PDF with a real text layer (no OCR needed)."""
    stream = f"BT /F1 14 Tf 20 60 Td ({text}) Tj ET".encode("latin-1")
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 120] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    startxref = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\n"
        f"startxref\n{startxref}\n%%EOF\n"
    ).encode("ascii")

    with open(path, "wb") as handle:
        handle.write(bytes(out))


def main():
    setup_stdio()
    if os.path.isdir(FIXTURES):
        shutil.rmtree(FIXTURES)
    os.makedirs(FIXTURES)

    with open(os.path.join(FIXTURES, "sample.txt"), "w", encoding="utf-8") as handle:
        handle.write("中文测试 plain text fixture\nemoji 😀 arrow → circled ①\n")

    with open(os.path.join(FIXTURES, "sample.csv"), "w", encoding="utf-8") as handle:
        handle.write("name,score\nAlpha,1\nBeta,2\n")

    with open(os.path.join(FIXTURES, "sample.html"), "w", encoding="utf-8") as handle:
        handle.write(
            "<html><head><title>Fixture</title>"
            "<script>console.log('should be stripped');</script>"
            "<style>body{color:red}</style></head>"
            "<body><h1>Fixture Heading</h1>"
            "<p>HTML paragraph with 中文.</p>"
            "<table><tr><th>Alpha</th><th>Beta</th></tr>"
            "<tr><td>1</td><td>2</td></tr></table></body></html>"
        )

    write_docx(os.path.join(FIXTURES, "sample.docx"))
    write_pdf(os.path.join(FIXTURES, "sample.pdf"))
    write_png(os.path.join(FIXTURES, "sample.png"))

    tree = os.path.join(FIXTURES, "tree")
    for relative, text in [
        ("top.txt", "top level file\n"),
        ("a/report.txt", "A report\n"),
        ("b/report.txt", "B report\n"),
        ("b/sub/deep.txt", "deep note\n"),
        (".hidden/skipme.txt", "hidden file should be skipped\n"),
        ("notes.md", "markdown is not an input extension\n"),
    ]:
        target = os.path.join(tree, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)

    print(f"fixtures written to {FIXTURES}")


if __name__ == "__main__":
    main()
