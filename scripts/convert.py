#!/usr/bin/env python3
"""
MarkItDown wrapper script for skill use.
Converts various document formats to Markdown.

Note: Requires Python 3.10+ and markitdown package.
Uses uv for Python/environment management.
"""

import argparse
import os
import sys
import subprocess
import shutil


def find_uv():
    """Find uv executable."""
    print("🔍 Searching for uv...", file=sys.stderr)
    candidates = [
        os.path.expanduser("~/.local/bin/uv"),
        "uv",
        "/usr/local/bin/uv",
        "/opt/homebrew/bin/uv",
        os.path.expandvars(r"%APPDATA%\\Python\\Python314\\Scripts\\uv.exe"),
        os.path.expanduser("~/AppData/Roaming/Python/Python314/Scripts/uv.exe"),
        os.path.expanduser("~/.local/bin/uv.exe"),
    ]
    for cmd in candidates:
        if shutil.which(cmd) or os.path.exists(cmd):
            print(f"✅ Found uv at: {cmd}", file=sys.stderr)
            return cmd
    print("❌ uv not found", file=sys.stderr)
    return None


def find_python312(uv_path):
    """Find Python 3.12 via uv."""
    if uv_path:
        print("🔍 Searching for Python 3.12...", file=sys.stderr)
        result = subprocess.run(
            [uv_path, "python", "find", "3.12"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            # uv prints the resolved interpreter path first (works cross-platform)
            for line in lines:
                resolved = line.strip()
                if resolved and os.path.exists(resolved):
                    print(f"✅ Found Python 3.12 at: {resolved}", file=sys.stderr)
                    return resolved
            for line in lines:
                if 'python3.12' in line or '/python3.12' in line:
                    for candidate in [
                        os.path.expanduser("~/.local/bin/python3.12"),
                        os.path.expanduser("~/.local/share/uv/python/cpython-3.12-macos-x86_64-none/bin/python3.12"),
                    ]:
                        if os.path.exists(candidate):
                            print(f"✅ Found Python 3.12 at: {candidate}", file=sys.stderr)
                            return candidate
    print("❌ Python 3.12 not found", file=sys.stderr)
    return None


def ensure_markitdown(uv_path, python_path):
    """Ensure markitdown is installed."""
    # Try running with uv run --with
    result = subprocess.run(
        [uv_path, "run", "--with", "markitdown", "--python", python_path, 
         "-c", "import markitdown; print('OK')"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def convert_with_uv(input_path, output_path=None, tables=False, ocr=False):
    """Convert file using uv run with markitdown."""
    uv_path = find_uv()
    if not uv_path:
        print("Error: uv not found. Please install uv:", file=sys.stderr)
        print("  curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
        return False
    
    python_path = find_python312(uv_path)
    if not python_path:
        print("Error: Python 3.12 not found via uv.", file=sys.stderr)
        return False
    
    # Create temp script
    import tempfile
    script_content = f'''
from markitdown import MarkItDown
import sys

converter = MarkItDown()

try:
    result = converter.convert("{input_path}")
    print(str(result))
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
'''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script_content)
        temp_script = f.name
    
    print(f"📄 Converting: {input_path}", file=sys.stderr)
    print(f"🚀 Running conversion via uv...", file=sys.stderr)
    
    try:
        cmd = [uv_path, "run", "--with", "markitdown", "--python", python_path, "python", temp_script]
        
        print(f"📊 Command: {' '.join(cmd)}", file=sys.stderr)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Conversion error: {result.stderr}", file=sys.stderr)
            return False
        
        markdown_text = result.stdout
        
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_text)
            print(f"✅ Saved to: {output_path}", file=sys.stderr)
            print(f"📝 Output length: {len(markdown_text)} characters", file=sys.stderr)
        else:
            print(markdown_text)
        
        return True
    finally:
        os.unlink(temp_script)


def convert_batch(input_dir, output_dir, recursive=False):
    """Convert all supported files in a directory."""
    import glob
    
    extensions = ['*.pdf', '*.docx', '*.doc', '*.xlsx', '*.xls', 
                  '*.pptx', '*.ppt', '*.html', '*.htm', '*.jpg', '*.jpeg',
                  '*.png', '*.gif', '*.bmp', '*.webp', '*.csv', '*.txt']
    
    files = []
    for ext in extensions:
        if recursive:
            files.extend(glob.glob(f"{input_dir}/**/{ext}", recursive=True))
        else:
            files.extend(glob.glob(f"{input_dir}/{ext}"))
    
    if not files:
        print(f"No supported files found in {input_dir}", file=sys.stderr)
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    for filepath in files:
        filename = os.path.basename(filepath)
        name, _ = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{name}.md")
        print(f"Converting: {filename}...", file=sys.stderr)
        convert_with_uv(filepath, output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown using markitdown"
    )
    parser.add_argument("input", help="Input file or directory")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("--tables", action="store_true", help="Extract tables as CSV")
    parser.add_argument("--ocr", action="store_true", help="Force OCR mode")
    parser.add_argument("--recursive", action="store_true", 
                        help="Recursively process directories (batch mode)")
    parser.add_argument("--output-dir", metavar="DIR", 
                        help="Output directory for batch mode")
    
    args = parser.parse_args()
    
    # Batch mode
    if args.recursive or os.path.isdir(args.input):
        if not args.output_dir:
            args.output_dir = args.input + "_markdown"
        convert_batch(args.input, args.output_dir, recursive=args.recursive)
        return
    
    # Single file mode
    if not os.path.isfile(args.input):
        print(f"Error: {args.input} is not a file", file=sys.stderr)
        sys.exit(1)
    
    if not args.output:
        name, _ = os.path.splitext(args.input)
        args.output = name + ".md"
    
    success = convert_with_uv(args.input, args.output, tables=args.tables, ocr=args.ocr)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
