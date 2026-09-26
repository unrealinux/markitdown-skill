# markitdown Skill

这是一个基于 [microsoft/markitdown](https://github.com/microsoft/markitdown) 的技能，可以将各种文档格式转换为 Markdown。

## 功能

- 📄 PDF 转换（需要 PDF 自带文字层）
- 📝 Word 文档 (.docx, .doc)
- 📊 Excel 电子表格 (.xlsx)
- 📑 PowerPoint 演示文稿 (.pptx)
- 🖼️ 图片元数据（**不做 OCR**）
- 🎵 音频转文字（需 Azure/Whisper，走 Python API，不在本脚本内）
- 🌐 HTML 页面
- 📦 批量文件夹转换（保留子目录结构）

## 安装

**需要 Python 3.10+ 和 [uv](https://astral.sh/uv)。** markitdown 本体由 uv 按需安装（首次运行会下载，之后走缓存），不需要手动 pip。

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 确认 uv 能找到 Python 3.12
uv python list
```

脚本实际安装的是 `markitdown[docx,xls,xlsx,pptx,pdf]`：基础包读不了 Office 和 PDF，会报 `MissingDependencyException`。首次转换会下载依赖（1-2 分钟），之后走缓存。

## 测试

```bash
python3 evals/make_fixtures.py && python3 evals/run_evals.py
```

夹具中的 txt/csv/html/docx/pdf/png 与目录树由标准库生成，不需要联网；`sample.xlsx` / `sample.pptx` 通过 uv + `openpyxl` + `python-pptx` 生成（手写 OOXML 很难同时满足这两个读取器），拿不到网络时这两条评测显示为 SKIP 而不是失败。

共 9 条评测，覆盖文本提取（txt/csv/html/docx/pdf/xlsx/pptx）、批量目录结构，以及「markitdown 不能 OCR」这条已知限制。

## 使用

```bash
# 转换单个文件（Markdown 输出到 stdout）
python3 <skill_dir>/scripts/convert.py document.pdf

# 保存到文件
python3 <skill_dir>/scripts/convert.py document.pdf -o output.md

# 批量转换（--recursive 保留子目录结构）
python3 <skill_dir>/scripts/convert.py ./documents --output-dir ./markdown --recursive

# 表格：xlsx/csv 会转成 Markdown 表格，没有 CSV 导出选项
python3 <skill_dir>/scripts/convert.py data.xlsx -o data.md
```

## 已知限制

- **不支持 OCR**：扫描件 PDF 和图片转出来是空的。需要先 OCR
  （`tesseract`），或改用 markitdown 的 Azure Document Intelligence 接口。
- **不支持导出 CSV**：表格以 Markdown 表格返回，要 CSV 请用 pandas/openpyxl。
- **不提取图片**：文档内的图片只保留引用。
- **Windows**：用 `py` 而不是 `python`（PATH 上的 `python` 是 Store 占位符，无输出）。

## 文件结构

```
markitdown/
├── SKILL.md              # 主技能文件
├── scripts/
│   └── convert.py        # 转换脚本
├── references/
│   └── formats.md        # 格式说明
└── evals/
    └── evals.json        # 测试用例
```
