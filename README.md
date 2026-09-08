# markitdown Skill

这是一个基于 [microsoft/markitdown](https://github.com/microsoft/markitdown) 的技能，可以将各种文档格式转换为 Markdown。

## 功能

- 📄 PDF 转换（支持 OCR）
- 📝 Word 文档 (.docx, .doc)
- 📊 Excel 电子表格 (.xlsx)
- 📑 PowerPoint 演示文稿 (.pptx)
- 🖼️ 图片 OCR
- 🎵 音频转文字
- 🌐 HTML 页面
- 📦 批量文件夹转换

## 安装

**需要 Python 3.10+**

```bash
# 安装 Python 3.12（如果还没有）
brew install python@3.12

# 安装 markitdown
pip3 install markitdown
```

## 使用

```bash
# 转换单个文件
python3 <skill_dir>/scripts/convert.py document.pdf -o output.md

# 批量转换
python3 <skill_dir>/scripts/convert.py ./documents --output-dir ./markdown --recursive

# 提取表格
python3 <skill_dir>/scripts/convert.py data.xlsx --tables
```

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
