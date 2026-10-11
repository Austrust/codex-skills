# CE+ server export and compilation helper

`scripts/overleaf_web.py` uses Python 3's standard library and an ephemeral
cookie session. It was derived from a successfully verified CE+
`6.3.0-ext-v5.1` / Overleaf 6.3.0 workflow. These routes are internal APIs,
not a promised public contract. Prefer this non-browser route for a required
server build or source ZIP export on a compatible instance with web credentials.
Use local compilation for ordinary source checks and native Git for source
synchronization and verification. The helper does not apply to Cloud SSO or an
unverified instance; browser use is a fallback only if a required operation
cannot be completed through a compatible non-browser route.

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

If only a Git token is available, finish the authorized Git work and local build.
Obtain web authentication or use an allowed browser fallback only when server
verification is required. Do not turn an optional server check into a browser
visit or assume that the Git token is also a web password.

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
dumping login responses or private download URLs. Start with the helper's
returned diagnostic and local compiler logs after a failure; inspect the editor
only when necessary server details are unavailable otherwise. An old PDF is not
a passing new build.

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
