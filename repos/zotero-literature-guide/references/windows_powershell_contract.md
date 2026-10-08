# Windows PowerShell Contract

Use this contract whenever the workflow writes Chinese text, pipes Python through PowerShell, or renders Chinese Markdown/HTML/PDF.

## Core Rule

Do not judge Chinese file integrity from PowerShell display alone. PowerShell may show mojibake even when the file is valid UTF-8.

But do treat PowerShell stdin as dangerous: a here-string piped into Python can replace Chinese characters with `?` if the console/input encoding is not UTF-8.

This applies to both Chinese content and Chinese filesystem paths. A path such as `30-文献调研` can become `30-????` before Python receives it if the UTF-8 prelude is missing.

## Safe Defaults

Before piping any Chinese-containing text or Python code through PowerShell, set:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
```

Prefer this pattern:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
@'
from pathlib import Path
Path("work/utf8_probe.txt").write_text("中文测试：原文 翻译 讲解", encoding="utf-8")
print(Path("work/utf8_probe.txt").read_text(encoding="utf-8").encode("unicode_escape").decode())
'@ | python -B -
```

Expected probe output should include Unicode escapes such as:

```text
\u4e2d\u6587\u6d4b\u8bd5
```

If the output contains literal question marks where Chinese should be, stop and fix encoding before writing guide files.

## Safer Than PowerShell Stdin

When generating large Chinese files, prefer one of these:

```text
1. Edit files with apply_patch.
2. Run an existing Python script file instead of piping a Chinese here-string.
3. Store Chinese source text in UTF-8 files and have Python read those files.
4. Use Python `Path.write_text(..., encoding="utf-8")` for Markdown/JSON/HTML.
```

Avoid long `python -c` one-liners containing Chinese text.

Do not write JSON reports with PowerShell redirection such as `*> guide_validation.json`, `> guide_validation.json`, or `Out-File` unless `-Encoding utf8` is explicit and verified. PowerShell can create UTF-16 JSON that looks readable in the terminal but fails UTF-8 consumers and the harness.

Prefer this pattern for validator JSON:

```powershell
@'
import json, subprocess, sys
from pathlib import Path
cmd = [sys.executable, "scripts/validate_guide.py", "--guide", "literature_guide.md", "--index", "extraction/paragraph_index.json", "--json"]
proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
data = json.loads(proc.stdout)
Path("guide_validation.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
'@ | python -B -
```

## Verifying Files

Use Python to verify actual file content:

```powershell
@'
from pathlib import Path
p = Path("literature_guide.md")
text = p.read_text(encoding="utf-8")
print(text[:200].encode("unicode_escape").decode())
'@ | python -B -
```

This checks the file bytes after decoding, not PowerShell's rendering of them.

For JSON:

```powershell
@'
import json
from pathlib import Path
data = json.loads(Path("term_glossary.json").read_text(encoding="utf-8-sig"))
print(json.dumps(data, ensure_ascii=False)[:200].encode("unicode_escape").decode())
'@ | python -B -
```

Use `utf-8-sig` when reading JSON created by PowerShell because Windows tools may add a UTF-8 BOM.

If a JSON file starts with UTF-16 BOM bytes `FF FE` or `FE FF`, regenerate it from source with Python UTF-8 writes before continuing. Do not normalize it silently without also recording the source command that created the bad encoding.

## Interpreting Common Failures

Terminal shows Chinese as mojibake:

```text
Likely display/console encoding issue.
Verify with Python unicode_escape before rewriting files.
```

Chinese becomes `????` inside generated Markdown:

```text
Actual corruption likely happened before Python received text.
Regenerate from source with UTF-8 PowerShell prelude or from a script file.
```

Chinese path becomes `????` inside Python:

```text
Actual corruption happened in PowerShell stdin.
Rerun with the UTF-8 prelude, or pass the path as a command-line argument to an existing script file instead of embedding it in a here-string.
```

Validation script says required Chinese blocks are missing:

```text
Check whether headings such as **原文**, **翻译**, **讲解** were corrupted to mojibake or question marks.
If corrupted, fix encoding and regenerate before debugging validator logic.
```

Do not keep corrupted Chinese headings or block labels in HTML comments as a workaround. Remove the comments and regenerate clean UTF-8 Markdown.

## PDF Rendering With Chinese Fonts

Render through an HTML/CSS or Pandoc/LaTeX route that explicitly names CJK-capable fonts. Do not rely on renderer defaults.

Recommended CSS font stack:

```css
body {
  font-family: "Noto Serif CJK SC", "Source Han Serif SC", "Microsoft YaHei", "SimSun", serif;
}

code, pre {
  font-family: "Cascadia Mono", "Consolas", monospace;
}
```

If using Pandoc + XeLaTeX, explicitly set a CJK main font when available:

```powershell
pandoc literature_guide.md -o literature_guide.pdf --pdf-engine=xelatex -V CJKmainfont="Microsoft YaHei"
```

Check installed CJK fonts before choosing the renderer variable:

```powershell
fc-list :lang=zh family
```

Prefer a normal academic Chinese font that is actually installed, for example `Microsoft YaHei`, `SimSun`, `FandolSong`, `STSong`, or another available CJK family. If `fontspec` reports the font cannot be found, choose another installed CJK font; do not rewrite Chinese content to work around a font problem.

If fonts are missing or PDF output drops Chinese glyphs, keep the Markdown/HTML as valid UTF-8, record the rendering risk in `build_log.md`, and try a different installed CJK font instead of rewriting the guide content.

## Build Log Requirement

When a run hits Chinese encoding/font problems, record:

```text
PowerShell version
Python version
whether UTF-8 prelude was set
renderer used for PDF
font stack or CJK font
verification command/result
whether issue was display-only or actual file corruption
```
