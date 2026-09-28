# markitdown Skill

这是一个基于 [microsoft/markitdown](https://github.com/microsoft/markitdown) 的技能，可以将各种文档格式转换为 Markdown。

## 功能

- 📄 PDF 转换（需要 PDF 自带文字层）
- 📝 Word 文档 (.docx)
- 📊 Excel 电子表格 (.xlsx, .xls)
- 📑 PowerPoint 演示文稿 (.pptx)
- 📓 Jupyter Notebook (.ipynb)、电子书 (.epub)、Outlook 邮件 (.msg，需 `--extra outlook`)
- 🖼️ 图片元数据（仅 .jpg/.jpeg/.png，**不做 OCR**）
- 🎵 音频元数据（转文字需 `--extra audio-transcription`）
- 🌐 HTML / 纯文本 / JSON / XML
- 🔗 URL 输入（http/https/file/data）与 stdin
- 📦 批量文件夹转换（保留子目录结构，`--json` 输出机器可读汇总）
- ☁️ `--extra` 一键解锁 Azure Document Intelligence / Content Understanding / 插件后端

## 安装

**需要 Python 3.10+ 和 [uv](https://astral.sh/uv)。** markitdown 本体由 uv 按需安装（首次运行会下载，之后走缓存），不需要手动 pip。

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 确认 uv 能找到 Python 3.12
uv python list
```

脚本默认安装的是 `markitdown[docx,xls,xlsx,pptx,pdf]`：基础包读不了 Office 和 PDF，会报 `MissingDependencyException`。首次转换会下载依赖（1-2 分钟），之后走缓存。需要其它后端（音频转写、Outlook 邮件、Azure DI、插件）时用 `--extra <name>`（可重复），或 `--extra all` 一次装全。

## 测试

```bash
python3 evals/make_fixtures.py && python3 evals/run_evals.py
```

夹具中的 txt/csv/html/docx/pdf/png 与目录树由标准库生成，不需要联网；`sample.xlsx` / `sample.pptx` 通过 uv + `openpyxl` + `python-pptx` 生成（手写 OOXML 很难同时满足这两个读取器），拿不到网络时这两条评测显示为 SKIP 而不是失败。

共 27 条评测，覆盖文本提取（txt/csv/html/docx/pdf/xlsx/pptx，其中 xlsx 夹具含两个工作表）、zip 自动解包、docx 脚注的真实渲染（`[[1]](#footnote-1)` 而不是 `[^1]`）、批量目录结构（含同名不同后缀不互相覆盖、跳过文件带原因上报）、坏文件与好文件混在一起时的退出码与报错、`-o` 落盘、`--json` 汇总、URL（`data:`）与 stdin 输入、`--help` 能力面、`--style-map` 与直接 `MarkItDown(style_map=...)` 结果一致、「markitdown 不能 OCR」这条已知限制（图片和音频都断言空输出 + stderr 警告 + 退出码 0），以及四条源码级守卫：包装脚本必须固定 `--python 3.12`、保留 URI/`--extra`/跳过上报，文档不得出现 markitdown 里不存在的参数名、与 0.1.8 实际行为矛盾的格式说明，或把 .doc/.ppt 当成走 LibreOffice。

批量模式在**同一个解释器**里转完所有文件（`import markitdown` 本身要 5 秒）。实测：4 个文件 21.9s → 6.0s，101 个文件约 9 秒。单文件模式绕不开这 5 秒，等 6-9 秒是正常的，不要当成卡死。

## 使用

```bash
# 转换单个文件（Markdown 输出到 stdout）
python3 <skill_dir>/scripts/convert.py document.pdf

# 保存到文件
python3 <skill_dir>/scripts/convert.py document.pdf -o output.md

# URL 和 stdin
python3 <skill_dir>/scripts/convert.py https://example.com/report.pdf
cat report.pdf | python3 <skill_dir>/scripts/convert.py - -x pdf

# 批量转换（--recursive 保留子目录结构，--json 输出机器可读汇总）
python3 <skill_dir>/scripts/convert.py ./documents --output-dir ./markdown --recursive --json

# 加后端：音频转写 / Azure DI / Outlook 邮件 / 全部
python3 <skill_dir>/scripts/convert.py meeting.mp3 --extra audio-transcription
python3 <skill_dir>/scripts/convert.py scan.pdf --extra az-doc-intel -d -e "$MARKITDOWN_DOCINTEL_ENDPOINT"
python3 <skill_dir>/scripts/convert.py mail.msg --extra outlook

# Word 自定义样式映射（输出与直接调 MarkItDown(style_map=...) 一致）
python3 <skill_dir>/scripts/convert.py report.docx --style-map "p[style-name='Quote'] => blockquote"

# 表格：xlsx/csv 会转成 Markdown 表格，没有 CSV 导出选项
python3 <skill_dir>/scripts/convert.py data.xlsx -o data.md
```

## 已知限制

- **不支持 OCR**：扫描件 PDF 和图片转出来是空的。需要先 OCR
  （`tesseract`），或加 `--extra az-doc-intel` 走 Azure Document Intelligence。
- **不支持 `.doc` / `.ppt`**：markitdown 0.1.8 没有这两个格式的转换器，也没有
  LibreOffice 通道，直接报 `UnsupportedFormatException`。先另存为 `.docx` /
  `.pptx`。批量模式会把它们列为 skipped。
- **图片只认 `.jpg` / `.jpeg` / `.png`**。
- **批量模式跳过 `.md` / `.markdown`**：转了也是逐字节复制，且 `--output-dir`
  指向输入目录时会覆盖源文件。
- **不支持导出 CSV**：表格以 Markdown 表格返回，要 CSV 请用 pandas/openpyxl。
- **不提取图片**：文档内的图片只保留引用（加 `--keep-data-uris` 可保留 base64）。
- **Windows**：用 `py` 而不是 `python`（PATH 上的 `python` 是 Store 占位符，无输出）。

## 文件结构

```
markitdown/
├── SKILL.md                  # 主技能文件
├── LICENSE                   # MIT（markitdown 本体为 MIT © Microsoft，运行时安装）
├── scripts/
│   └── convert.py            # 转换脚本
├── references/
│   └── formats.md            # 格式说明
└── evals/
    ├── evals.json            # 测试用例定义
    ├── make_fixtures.py      # 生成夹具（fixtures/ 不入库）
    └── run_evals.py          # 执行评测
```
