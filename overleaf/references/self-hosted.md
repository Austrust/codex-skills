# Self-hosted capability and data scope

Verified compatibility baseline (2026-10-07): community CE+
`6.3.0-ext-v5.1`, upstream Overleaf 6.3.0, matching Git Bridge 6.3.0, and
TeX Live 2026. Native Git clone, source push into the editor, web edits pulled
through Git, and server XeLaTeX/Biber compilation were successfully exercised.
This is a tested baseline, not an instruction to upgrade another instance.

Native Git requires a configured Git Bridge and suitable project permissions.
Stock Community Edition does not include this capability. CE+ is a community
extension; distinguish its support and update channel from Overleaf Cloud or
licensed Server Pro. Check the actual deployment when diagnosing availability.

For ordinary writing, obtain the instance URL and project link from the user
or private runtime configuration. Avoid hardcoding an owner's host, account,
server IP, or device path into a portable skill. No special administrator
account or server SSH access is needed to edit an accessible project.

If the user requests deployment or migration, inspect the existing deployment
and follow its instructions before changing it. A complete CE+ migration
includes application/project data, MongoDB data, Redis state as required by
the deployment, **Git Bridge storage**, private configuration/session secrets,
and the exact image versions. A project Git clone or source ZIP covers source
files only. Prefer a verified backup restored into new volumes; do not destroy
the current deployment to prepare a trial. Verify login, source synchronization,
and an actual build at the destination before switching traffic. Log each SSH
operation when the server-management workspace requires it, with secrets
redacted.

Primary configuration references:

- [CE+ Git integration](https://github.com/yu-i-i/overleaf-cep/wiki/Extended-CE:-Git-Integration)
- [Overleaf on-premises Git Bridge configuration](https://docs.overleaf.com/on-premises/configuration/overleaf-toolkit/server-pro-only-configuration/git-integration)
