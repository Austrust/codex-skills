---
name: mechanical-drawing
description: 从 3D 模型（STEP / build123d）生成规范机械加工工程图（A4/A3，第一角投影、ISO 128/129 视图与尺寸、ISO 7200 标题栏），并叠加中文标题、技术要求与标注术语。Use when the user asks for 加工图 / 工程图 / 图纸 / technical drawing / 出图 from CAD models or STEP files, or complains that generated drawings are 不规范。
---

# 机械加工工程图（规范出图）

目标：交付可直接用于加工的 A4/A3 工程图（PDF + PNG）：视图/剖视合规、尺寸齐全、标题栏完整、
技术要求到位、文字中文可读。默认第一角投影。

## 工具选型（2026-11 核过）

- 首选 [draftwright](https://github.com/pzfreo/draftwright)（GitHub 52★；PyPI `draftwright` 0.6.1，Rust 引擎 + CLI）：
  STEP 输入 → 自动特征识别/视图/剖视/尺寸/ISO 7200 标题栏，输出 SVG/PDF/DXF，附
  `problems` 审查 JSON（含 fix_before_printing 级问题）。AGPL-3.0。
  - 安装：在统一 CAD 环境 venv 中 `pip install draftwright pymupdf`。
- 备选 [build123d-techdraw](https://github.com/szubster/build123d-techdraw)（0.9.0，Apache-2.0，ISO 1302 粗糙度/GD&T），
  但要求 `build123d>=0.13`（OCP 8.0），与 OCP 7.9 + build123d 0.11 + cadquery 2.8 的统一 CAD 环境不兼容；
  若要用需另建环境。
- FreeCAD TechDraw：标准最全，但本机 FreeCAD 为 snap，在 DSH 服务 cgroup 内不能运行（需登录会话），
  不适合自动化流水线。

## 标准基线

- 视图/投影：ISO 128、ISO 129、ISO 5456（第一角）；GB 对照 GB/T 14692、GB/T 4458。
- 图幅/图框：ISO 5457 / GB/T 14689（A4 横版 297×210）。
- 标题栏：ISO 7200（draftwright 内置；GB/T 10609.1 为 180×56 中文栏，如需 GB 栏需另做模板）。
- 未注公差：ISO 2768-mK（对应 GB/T 1804-m 常用等级）。
- 表面结构：ISO 1302（draftwright 的 AP242 PMI 支持；无 PMI 时在技术要求中写 Ra 要求）。
- 直径符号：中文图用 “φ”（SimHei 无 ⌀/ø/Ø，叠加时必须替换）。

## 出图流程

1. **确认基准**：零件 3D 模型（STEP 首选，装配体拆件）；记录图号、材料、数量、比例、版次、日期。
2. **draftwright 生成**：
   ```bash
   draftwright render part.step --spec notes.json \
     --title "中文图名" --number MHD261-05B --material PMMA --revision B --date 2026-11-27 \
     --company "SCI-MHD-261" --tolerance "ISO 2768-mK" --drawn-by "-" --approved-by "-" \
     --size A4 -o out --formats pdf
   ```
   `notes.json` 里放技术要求（先用占位文本，见第 3 步宽度技巧）：
   `{"schema":"draftwright.spec/3","notes":[{"id":"n:1","text":"..."}]}`
3. **中文叠加（PyMuPDF）**：
   - 中文文本无法被 draftwright 内置 IBM Plex 绘制；生成时把每个非 ASCII 字符写成 `WW`
     （2 个 W ≈ 一个汉字宽度），使引擎预留的文本框/备注栏宽度与中文实际宽度匹配；
   - 用 PyMuPDF 嵌入黑体（如 `~/.local/share/fonts/mscore/simhei.ttf`，或系统 SimHei），
     白色覆盖原占位文字后在原位重写中文；标题写成“中文  ENGLISH”双语并居中于图名栏；
   - 覆盖白块左侧要留 8–10 pt：draftwright 的“⌀”等符号字形会向左溢出文本框；
   - `⌀/ø/Ø → φ`，`⌴/⊔/↧ → 沉孔/深`，`THRU→通孔`、`EQ SP ON→均布于`、`BC→分布圆`、
     `OD→外径`、`DETAIL→局部放大`、`SECTION→剖视`、`ISO VIEW→轴测图（示意）`、`SCALE→比例`；
   - 保存前 `doc.subset_fonts()`，否则 PDF 会因嵌入整份中文字体涨到数 MB。
4. **人工修正标注**：draftwright 的特征识别是启发式，密封槽/凸环等非标特征可能被标成“沉孔”、
   重复或漏标。按几何在生成工具的 `parts_meta.py` 的 `overrides` 表里逐条“原文 → 修正中文（或 None 删除）”，
   重出图；不要直接改 PDF 文本。
5. **自动审查**：读 draftwright 的 problems JSON：
   - `fix_before_printing` 必须清零或逐条说明（`text_glyph_missing` 是中文占位导致，可忽略）；
   - `feature_not_dimensioned`、`unrecognised features`、`extension_through_feature` 等需人工判断；
     必要时补技术要求或调整 spec。
6. **成图检查清单**：
   - [ ] 视图/剖视足够表达内外结构；剖视有 45° 剖面线；中心线/中心标记齐全；
   - [ ] 关键尺寸齐全（外形、孔径/孔位、槽宽/槽深、台阶/深度、螺纹/配合），无重复与矛盾；
   - [ ] 标题栏：图名（中英）、图号、材料、数量、比例、版次、日期、单位/幅面、设计/审核栏；
   - [ ] 技术要求：未注公差、未注圆角、去毛刺、表面粗糙度、数量、材料、特殊工艺；
   - [ ] 中文无缺字（φ、≤、± 等符号逐字检查）；PDF 矢量、文字可搜索；A4 横版单页/多页正确；
   - [ ] 旧版图纸明确作废/替代关系。

## 安装到技能目录

- DSH/agents 目标：复制本目录到 `~/.agents/skills/mechanical-drawing/`（或 `$AGENTS_HOME/skills/`）。
- Codex 目标：复制本目录到 `~/.codex/skills/mechanical-drawing/`（或 `$CODEX_HOME/skills/`）。
- 本集合中可用 PowerShell 安装器：`scripts/install.ps1 -Target both -Skill mechanical-drawing`；
  无 PowerShell 时手工复制，并用
  `python scripts/validate.py --skill mechanical-drawing --installed-root <skills 目录>` 校验文件一致性。

## 示例落地（SCI-MHD-261 动密封组件）

- 生成工具：`02_动密封/动密封模型build123d/图纸/生成工具/`（`parts_meta.py` 定义图名/备注/标注修正，
  `make_drawings.py` 出图，`overlay_cn.py` 中文叠加，`run.sh` 一键重出）。
- 成图：`02_动密封/动密封模型build123d/图纸/`（MHD261-05B…09B）。
- 复现：`cd 图纸/生成工具 && ./run.sh`。
