# CE+ web export and compilation helper

`scripts/overleaf_web.py` uses Python 3's standard library and an ephemeral
cookie session. It was derived from a successfully verified CE+
`6.3.0-ext-v5.1` / Overleaf 6.3.0 workflow. These routes are internal APIs,
not a promised public contract. Prefer the browser for Cloud, SSO, or an
instance whose route/response compatibility has not been established.

```sh
python scripts/overleaf_web.py --url https://latex.example.org --email <email> download <project-id> --output project.zip
python scripts/overleaf_web.py --url https://latex.example.org --email <email> compile <project-id> --compiler xelatex --root main.tex --output paper.pdf
```

The password is prompted privately. Noninteractive callers can supply it
through private standard input with `--password-stdin`, placed before the
subcommand. Do not place a literal password in a shell command or pipe it from
a committed file. This is the **web password**, separate from the Git token.
No cookie, token, or password is saved. Existing output files are protected;
use `--overwrite` only when replacing the chosen output is intended.

The helper:

1. Reads CSRF from `/login`, posts the login JSON, and verifies `/project`.
2. Exports `/project/<id>/download/zip`, validating the ZIP before saving.
3. For compile, posts `{compiler, rootResourcePath, check: "silent"}` to
   `/project/<id>/compile`, requires a successful build, and downloads the PDF
   URL returned by the server. It validates both the origin and PDF signature.

Compilation is an explicit action. It produces server build outputs but does
not rewrite project sources or change the stored compiler setting. The helper
does not create projects, manage users/tokens, upload files, or delete data.
Compiler choices: `pdflatex`, `xelatex`, `lualatex`; root path must be a relative
`.tex` file. Errors return a nonzero exit code and a bounded diagnostic without
dumping login responses or private download URLs. Inspect build details in the
editor after a compilation failure; an old PDF is not a passing new build.

TLS certificates are always verified. `--connect-address <address>` is an
optional per-invocation DNS diagnostic override; the hostname and SNI stay the
same. It does not make a dynamic address a permanent configuration. HTTP is
accepted only for a loopback test instance.

If an endpoint's status or response shape differs, stop and check the current
server implementation. Do not guess replacement write routes. In this tested
version, compile/settings/upload use the `X-CSRF-Token` header; adding `_csrf`
to those JSON or multipart bodies can fail strict request validation.

From the source repository root, test the helper without a real account or project:

```sh
python -m unittest discover -s tests -v
```
