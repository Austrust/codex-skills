# Overleaf skill

An agent skill that uses native Git for source discovery, editing, synchronization,
and verification on Overleaf Cloud or a compatible self-hosted instance. Ordinary
build checks run locally. When a server build is needed, a compatible CE+ 6.3
Python helper is preferred; browser automation is the fallback for capabilities
that require it. TLS verification and ephemeral login sessions are preserved.
Git does not replace a complete project backup.

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

Example: “使用 $overleaf 通过 Git 修改这个项目，推送源码并在本地编译。”

## Tool selection

- A supplied Git URL goes directly to Git; no browser menu check is needed.
- Clone/fetch, edit, commit/push, then fetch and inspect the remote source with Git.
- Use local `latexmk` or another available compiler for ordinary build checks.
- For required server verification or a build unavailable locally,
  use `overleaf/scripts/overleaf_web.py` on a verified compatible instance with
  web credentials. A Git token is not a web password.
- Use the browser for requested UI work or a required capability that lacks a
  compatible non-browser route. Optional server checks do not trigger a visit.
- On network failure, inspect execution permissions and use the tool's supported
  permission path before changing connection settings or switching to a browser.

Report Git synchronization, local compilation, and server compilation separately.

## Validate

Requires Python 3; runtime helper and protocol tests use only its standard library:

```sh
python -m unittest discover -s tests -v
python overleaf/scripts/overleaf_web.py --help
```

Tests exercise a loopback HTTP server, authentication/CSRF, export integrity,
compile failures, cross-origin PDF rejection, output protection, and secret-free
diagnostics. They need no real credentials and do not write to live projects.
