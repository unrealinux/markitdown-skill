# markitdown Skill

基于 [microsoft/markitdown](https://github.com/microsoft/markitdown) 0.1.8 的技能：把各种文档转成 Markdown。符合 [Agent Skills 规范](https://agentskills.io/specification)，可被 Pi、Claude Code 及其它实现加载。

**本文档是完整中文说明**（安装、全部开关、格式边界、出错排查、评测、打包）。
`SKILL.md` 与 `references/formats.md` 是给模型读的英文原文，原因见文末[关于语言](#关于语言)。

## 安装这个技能

把压缩包解到 agent 读取技能目录的位置。Pi 和 Claude Code 都读 `~/.agents/skills/`，其它实现填它自己的技能目录：

```bash
unzip markitdown-*.zip -d ~/.agents/skills/
```

解压出来的目录名必须是 `markitdown`（Agent Skills 规范要求 frontmatter 的 `name` 等于父目录名），不要改名、也不要再套一层目录。开发时建议用软链指向工作副本，否则仓库更新不会生效：

```bash
ln -s /path/to/markitdown-skill ~/.agents/skills/markitdown
```

验证装好了（Windows 把 `python3` 换成 `py`）：

```bash
SKILL=~/.agents/skills/markitdown
python3 $SKILL/scripts/convert.py --help          # 列出全部开关，不联网
python3 $SKILL/scripts/convert.py $SKILL/evals/fixtures/sample.txt   # 首次会下载依赖，约 1-2 分钟
```

agent 会自动按 `SKILL.md` 的 `description` 触发；也可以显式调用 `/skill:markitdown`。想彻底确认，跑一遍自带评测（29 条，离线）：

```bash
cd ~/.agents/skills/markitdown && python3 evals/run_evals.py
```

## 快速开始

```bash
SKILL=~/.agents/skills/markitdown

# 转成 Markdown，打到 stdout
python3 $SKILL/scripts/convert.py 报告.pdf

# 存成文件
python3 $SKILL/scripts/convert.py 报告.docx -o 报告.md

# 整个文件夹（含子目录）
python3 $SKILL/scripts/convert.py ./文档 --output-dir ./md --recursive
```

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
- 📴 可选**离线包**：自带 Python + markitdown，适合无外网、没装 Python、没有 uv 的机器

## 运行环境

**需要 Python 3.10+ 和 [uv](https://astral.sh/uv)。** markitdown 本体由 uv 按需安装（首次运行会下载，之后走缓存），不需要手动 pip。

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 确认 uv 能找到 Python 3.12
uv python list
```

脚本默认安装的是 `markitdown[docx,xls,xlsx,pptx,pdf]`：基础包读不了 Office 和 PDF，会报 `MissingDependencyException`。首次转换会下载依赖（1-2 分钟），之后走缓存。需要其它后端（音频转写、Outlook 邮件、Azure DI、插件）时用 `--extra <name>`（可重复），或 `--extra all` 一次装全。

## 命令行开关

```bash
python3 scripts/convert.py [输入] [选项]
```

`输入` 可以是文件、目录、URL（`http:` / `https:` / `file:` / `data:`），或 `-` 读 stdin；不写默认就是 `-`。

| 选项 | 作用 |
|---|---|
| `-o, --output FILE` | 单文件模式写到文件；不写则打到 stdout |
| `--output-dir DIR` | 目录模式输出目录，默认 `<输入目录>_markdown`（`.` 和 `..` 落到 `./markdown`） |
| `--recursive` | 目录模式递归子目录，输出镜像输入结构 |
| `--json` | 目录模式把汇总以 JSON 打到 stdout（进度仍在 stderr） |
| `--extra NAME` | 给这次运行加一个 markitdown extra，可重复：`audio-transcription`、`outlook`、`az-doc-intel`、`az-content-understanding`、`all` |
| `-x, --extension EXT` | 扩展名提示（stdin 必需，或无扩展名文件） |
| `-m, --mime-type TYPE` | MIME 类型提示 |
| `-c, --charset CS` | 字符集提示（如 `utf-8`） |
| `-d, --use-docintel` | 走 Azure Document Intelligence，需配合 `-e`（或环境变量 `MARKITDOWN_DOCINTEL_ENDPOINT`）和 `--extra az-doc-intel` |
| `-e, --endpoint URL` | Document Intelligence 端点 |
| `--use-cu` | 走 Azure Content Understanding，需 `--cu-endpoint`（或 `MARKITDOWN_CU_ENDPOINT`）和 `--extra az-content-understanding` |
| `--cu-endpoint` / `--cu-analyzer` / `--cu-file-types` | Content Understanding 端点 / 分析器 ID / 路由的文件类型（如 `pdf,jpeg,mp4`） |
| `-p, --use-plugins` | 启用第三方 markitdown 插件 |
| `--list-plugins` | 列出已安装插件后退出 |
| `--keep-data-uris` | 保留 base64 图片数据（默认截断） |
| `--style-map TEXT` | Word 样式映射，等价于 `MarkItDown(style_map=...)` |
| `-h, --help` | 帮助 |

退出码：`0` 成功（**空输出也算成功**，会在 stderr 提示），`1` 转换失败或参数错误。批量模式只要有一个文件失败就返回 1。

## 常见工作流

```bash
SKILL=~/.agents/skills/markitdown

# 读一个 PDF 看里面有什么
python3 $SKILL/scripts/convert.py report.pdf | head -50

# 抽取 Excel 数据（输出 Markdown 表格；要 CSV 请用 pandas/openpyxl）
python3 $SKILL/scripts/convert.py data.xlsx -o data.md

# 一整个文件夹，同名不同后缀不会互相覆盖
python3 $SKILL/scripts/convert.py ./documents --output-dir ./markdown --recursive --json

# 管道 / URL：直接喂给下游
cat report.pdf | python3 $SKILL/scripts/convert.py - -x pdf | grep -i "结论"
python3 $SKILL/scripts/convert.py https://example.com/report.pdf

# 扫描件：本技能没有 OCR，先 OCR 再转
tesseract invoice.png invoice --psm 6
python3 $SKILL/scripts/convert.py invoice.txt
```

## 支持格式与实测边界

| 类别 | 扩展名 | 说明 |
|---|---|---|
| 文档 | `.pdf`、`.docx` | PDF 需要文字层 |
| 表格 | `.xlsx`、`.xls`、`.csv` | **每个工作表**都转成 Markdown 表格，各自带 `## 工作表名` |
| 演示 | `.pptx` | 每页以 `<!-- Slide number: N -->` 标注；备注非空时输出 `### Notes:` |
| 网页 / 文本 | `.html`、`.htm`、`.txt`、`.text`、`.json`、`.jsonl`、`.xml` | 脚本和样式被剥离 |
| 笔记本 / 电子书 / 邮件 | `.ipynb`、`.epub`、`.msg` | `.msg` 需 `--extra outlook` |
| 图片 | `.jpg`、`.jpeg`、`.png` | 只有元数据，**不 OCR**；`gif` / `bmp` / `webp` 不被接受 |
| 音视频 | `.mp3`、`.wav`、`.m4a`、`.mp4` | 默认只有元数据；转文字需 `--extra audio-transcription` |
| 压缩包 | `.zip` | 自动解包，每个条目输出 `## File: <名字>` |
| 不支持 | `.doc`、`.ppt` | markitdown 0.1.8 里没有转换器，也没有 LibreOffice 通道，直接报 `UnsupportedFormatException` |

其它实测细节（都对着 0.1.8 的源码和真实文件验证过，不是抄文档）：

- **Word 脚注**渲染成内联 `[[1]](#footnote-1)` + 文末有序列表，不是 `[^1]` 语法。
- `include_formatting=True` 这个参数**不存在**，传了会被静默忽略；能改样式的只有 `style_map`。
- **多工作表**是全转，没有"只转第一个 sheet"的行为；`file.xlsx::Sheet` 这种写法也不被识别。
- `.zip` 会自动解包，不需要先 `unzip`。
- 批量模式跳过 `.md` / `.markdown`（转了等于复制，还可能覆盖源文件）。

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

## 出错排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `uv not found` | uv 没装或不在 PATH | 装 uv；Windows 通常在 `%APPDATA%\Python\Python3xx\Scripts\uv.exe`；**无外网就用离线包**，或把 `MARKITDOWN_PYTHON` 指向一个已装 markitdown 的解释器 |
| `MissingDependencyException` | 该格式的 extra 没装 | 默认已含 `docx,xls,xlsx,pptx,pdf`；`.msg` / 音频等要加 `--extra` |
| `UnsupportedFormatException` | markitdown 读不了这个格式 | `.doc` / `.ppt` 先另存；其它格式先转 PDF 或 `.docx` |
| PDF / 图片输出为空 | 没有文字层，或无 OCR | 先 `tesseract` OCR，或用 `--extra az-doc-intel` |
| 输出为空但退出码 0 | 同上，空输出不算失败 | 看 stderr 的 `⚠️ Empty output` 提示 |
| stderr 出现 `\U0001f680` 这类转义 | 老版本包装脚本没切 UTF-8 | 升级到当前版本（`force_utf8_stdout` 已修） |
| 等 6-9 秒没反应 | `import markitdown` 本身约 5 秒 | 正常，别中断；批量模式只付一次 |
| 第一次转换卡很久 | uv 在下载 markitdown 及依赖 | 首次 1-2 分钟，之后走缓存 |
| `-d` 报端点缺失 | 用了 Document Intelligence 没给端点 | 加 `-e`，或设 `MARKITDOWN_DOCINTEL_ENDPOINT` |
| 中文乱码 | 源文件不是 UTF-8 | 另存为 UTF-8 再转 |

## 评测

```bash
python3 evals/make_fixtures.py && python3 evals/run_evals.py
```

夹具中的 txt/csv/html/docx/pdf/png 与目录树由标准库生成，不需要联网；`sample.xlsx` / `sample.pptx` 通过 uv + `openpyxl` + `python-pptx` 生成（手写 OOXML 很难同时满足这两个读取器），拿不到网络时这两条评测显示为 SKIP 而不是失败。发行包内已带夹具，所以解压后直接跑 `run_evals.py` 即可，全程离线。

共 32 条评测，覆盖文本提取（txt/csv/html/docx/pdf/xlsx/pptx，其中 xlsx 夹具含两个工作表）、zip 自动解包、docx 脚注的真实渲染（`[[1]](#footnote-1)` 而不是 `[^1]`）、批量目录结构（含同名不同后缀不互相覆盖、跳过文件带原因上报）、坏文件与好文件混在一起时的退出码与报错、`-o` 落盘、`--json` 汇总、URL（`data:`）与 stdin 输入、`--help` 能力面、`--style-map` 与直接 `MarkItDown(style_map=...)` 结果一致、默认输出目录 `<input>_markdown`、打包脚本的 zip 清单（顶层只有 `markitdown/`、不含构建垃圾）、离线包支持（优先用 `vendor/python`、`--extra` 被忽略、构建脚本裁剪+自检）、「markitdown 不能 OCR」这条已知限制（图片和音频都断言空输出 + stderr 警告 + 退出码 0），以及四条源码级守卫：包装脚本必须固定 `--python 3.12`、保留 URI/`--extra`/跳过上报，文档不得出现 markitdown 里不存在的参数名、与 0.1.8 实际行为矛盾的格式说明，或把 .doc/.ppt 当成走 LibreOffice。

批量模式在**同一个解释器**里转完所有文件（`import markitdown` 本身要 5 秒）。实测：4 个文件 21.9s → 6.0s，101 个文件约 9 秒。单文件模式绕不开这 5 秒，等 6-9 秒是正常的，不要当成卡死。

## 离线安装包（无外网 / 无 Python / 无 uv）

面向完全隔离的机器（内网、没装 Python、没有 uv）。包里自带一个独立 CPython 和已经装好的 markitdown，目标机解压就能跑。

在自己这台能联网的机器上构建：

```bash
py scripts/build_offline_bundle.py                                  # 首次：下载解释器和依赖
py scripts/build_offline_bundle.py --keep-python --skip-install      # 之后复用，只重新打包
py scripts/build_offline_bundle.py --extras docx,xls,xlsx,pptx,pdf   # 自定义烘进去的 extras
```

产物 `dist/markitdown-<版本>-offline-<平台>.zip`，实测 **76.3 MiB**（Python 3.12.14 + `markitdown[docx,xls,xlsx,pptx,pdf]`，压缩前 204 MiB）。

目标机器上：解压到任意位置，直接跑——不装任何东西、不联网。

```bat
markitdown\scripts\convert.py 你的文档.pdf
markitdown\scripts\convert.py D:\文档 --output-dir D:\md --recursive
```

原理：`convert.py` 启动时先找 `vendor/python/`（也可以用环境变量 `MARKITDOWN_PYTHON` 指定别的解释器），找到就直接用它跑，**完全跳过 uv 和网络**，并会在 stderr 打一行 `🔌 Offline bundle interpreter:` 让你确认走的是哪条路径。

**限制**

- **平台绑定**：解释器和编译型依赖（numpy/pandas/onnxruntime/lxml）只对构建时的平台+架构有效。要 Windows ARM64 或 Linux，就在对应平台上各构建一次。
- **`--extra` 在离线包里无效**：依赖是烘进去的，加了只打一条警告然后忽略。要别的后端就在构建时用 `--extras` 加。
- **音频转写、Azure DI / CU 仍然需要网络**——那是服务调用，不是安装问题。
- **交付方式**：76 MiB 走 U 盘 / 内网共享 / 微信，不适合当邮件附件。
- 构建时会裁掉 `pip`、`Scripts/`、Tcl/Tk、`sympy`+`mpmath`（共省 115 MiB），裁完自动跑自检（导入 onnxruntime + 转换 7 种格式的夹具），自检不过就中止构建。

## 打包发布

```bash
py scripts/package_skill.py                        # dist/markitdown-<版本>.zip
py scripts/package_skill.py --version 1.0.0 --out /tmp
py scripts/package_skill.py --vendor <解释器目录> --label offline-win-x64   # 打离线包
```

产物是**一个顶层目录** `markitdown/`，里面是 `SKILL.md`、`README.md`、`LICENSE`、`scripts/`、`references/`、`evals/`。
这个目录名必须是 `markitdown`（Agent Skills 规范要求 `name` 等于父目录名），
所以不能直接压仓库根目录（那个目录叫 `markitdown-skill`）。

- 包含 `evals/fixtures/`（本地存在时），所以解压后可以直接 `py evals/run_evals.py`，**不需要联网**
- 不包含 `.git/`、`__pycache__/`、`*.pyc`、`dist/`
- 输出**可复现**：文件排序 + 固定时间戳，同一份源码永远同一个 sha256（实测两次构建一致）
- 版本号取自 `SKILL.md` 的 `metadata.version`

分发方式：

```bash
# 1. 手动安装：见前面的「安装这个技能」

# 2. GitHub Release 附件：把 zip 传上去，用打印出的 sha256 给用户校验
gh release create v0.1.2 dist/markitdown-0.1.2.zip --notes-file dist/RELEASE_NOTES-0.1.2.md

# 3. npm 包 + Pi 目录（pi.dev/packages）：package.json 里加 pi.skills + pi-package 关键字
```

## 文件结构

```
markitdown/
├── SKILL.md                  # 主技能文件（英文，模型读）
├── README.md                 # 完整中文说明（本文件，人读）
├── LICENSE                   # MIT（markitdown 本体为 MIT © Microsoft，运行时安装）
├── scripts/
│   ├── convert.py            # 转换脚本
│   ├── package_skill.py      # 打包成可分发的 zip
│   └── build_offline_bundle.py  # 构建离线包（自带解释器，无外网可用）
├── references/
│   └── formats.md            # 各格式细节（英文）
├── evals/
│   ├── evals.json            # 测试用例定义
│   ├── make_fixtures.py      # 生成夹具（fixtures/ 不入库）
│   └── run_evals.py          # 执行评测
└── vendor/                   # 可选，只在离线包里出现
    └── python/               # 独立 CPython + 已装好的 markitdown
```

## 关于语言

- **`README.md`（本文件）= 完整中文说明**，面向人：安装、开关、格式边界、排查、评测、打包。
- **`SKILL.md` = 英文**，面向模型。生态里（Anthropic 的 skills 合集、Pi 的示例）都用英文写指令，混语言对模型没有收益，反而更容易和上游文档脱节。它的 frontmatter `description` 里已经加了中文触发词，所以中文请求一样会被路由到这个技能。
- **`references/formats.md` = 英文**，因为它是 `SKILL.md` 的下级资料，模型按需读取。
- 脚本注释与 commit message 也是英文，便于和上游 markitdown 对照。

如果你确实需要一份中文的 `SKILL.md`（例如面向只用中文团队维护），可以复制成 `references/SKILL.zh-CN.md` 作为参考；但不建议直接替换 `SKILL.md`，因为那是规范入口、也是和其它实现互通的那份。
