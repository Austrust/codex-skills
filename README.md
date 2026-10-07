# Overleaf skill

An agent skill for native Git source synchronization, web compilation, and PDF
download on Overleaf Cloud or a compatible self-hosted instance. The optional
Python helper is scoped to the verified CE+ 6.3 web flow, with TLS verification
and ephemeral login sessions. Git does not replace a complete project backup.

Start with [overleaf/SKILL.md](overleaf/SKILL.md). Supporting references cover
authentication, actual remote branch discovery, concurrent web edits, annotation
limits, and self-hosted migration scope. No account, token, or personal instance
address is bundled.

## Install

Through the [personal skill collection](https://github.com/Austrust/codex-skills):

```powershell
.\scripts\install.ps1 -Target codex -Skill overleaf
```

Alternatively, copy only the `overleaf/` directory into your agent's skill
directory (for example `$CODEX_HOME/skills/overleaf`). Keep the source repository
outside the installed skill directory. Invoke with `$overleaf` and a project
link, or ask the agent to modify/synchronize an Overleaf project.

Example: “使用 $overleaf 修改这个项目，推送源码并验证网页编译。”

## Validate

Requires Python 3; runtime helper and protocol tests use only its standard library:

```sh
python -m unittest discover -s tests -v
python overleaf/scripts/overleaf_web.py --help
```

Tests exercise a loopback HTTP server, authentication/CSRF, export integrity,
compile failures, cross-origin PDF rejection, output protection, and secret-free
diagnostics. They need no real credentials and do not write to live projects.
