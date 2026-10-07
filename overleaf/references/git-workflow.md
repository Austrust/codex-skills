# Native Git workflow

## Authentication and remote selection

Copy the Git URL from the project's Git integration menu. Typical forms:

```text
Cloud:       https://git.overleaf.com/<project-id>
Self-hosted: https://git@latex.example.org/git/<project-id>
```

When prompted, use username `git` and a personal Git authentication token from
Account Settings. The web email/password pair is not Git authentication.
Generate or revoke tokens only within the user's authorized account task.
Never print a token, put it in a remote URL, or store it in a project file.
An existing secure OS credential manager is preferable. If automation uses
`GIT_ASKPASS`, let a temporary helper read the token from a private process
environment; keep the helper free of secret values and remove it afterward.
Disable persistent credential saving for a deliberately temporary token with
the per-invocation option `-c credential.helper=`. Never use plaintext
`credential.helper store` as a shortcut.

## New checkout

Use a fresh destination that does not contain someone else's files:

```sh
git clone <copied-git-url> <project-directory>
git -C <project-directory> status --short --branch
git -C <project-directory> remote -v
git -C <project-directory> ls-remote --symref origin HEAD
```

Read the `ref: refs/heads/<branch> HEAD` result. Do not infer the remote branch
from the local branch name. If the server omits symbolic HEAD, inspect
`ls-remote --heads`, use the sole supported branch if unambiguous, or resolve
the ambiguity before pushing.

## Existing checkout

Read applicable project instructions, `git status`, remotes, and diffs first.
If `origin` is GitHub/Gitea, keep it and add a named remote such as `overleaf`
only after confirming the project URL. Do not replace an unrelated remote.

```sh
git remote add overleaf <copied-git-url>
git ls-remote --symref overleaf HEAD
git fetch overleaf
```

Do not merge unrelated Git histories merely to transfer source. A separate
Overleaf clone is often safer: reconcile the source files and commit within
that clone, retaining the development repository's history and branches.

For a clean clone with matching history, integrate with a fast-forward when
possible:

```sh
git pull --ff-only <overleaf-remote> <remote-branch>
```

If local changes or divergent commits prevent this, inspect the difference and
preserve the work before choosing a merge, rebase, or an isolated checkout.
Do not automatically stash a user's files, reset, clean, or overwrite them.

## Review, publish, and verify

```sh
git diff --check
git diff -- <intended-files>
git add -- <intended-files>
git diff --cached
git commit -m "<concrete requested change>"
git push <overleaf-remote> HEAD:refs/heads/<remote-branch>
git fetch <overleaf-remote>
```

If nothing changed, do not manufacture a commit. Stage only the intended
files. Keep generated build artifacts out unless the project actually tracks
them. Verify the pushed files through the editor or a fresh source ZIP;
concurrent browser edits can create a different subsequent remote commit.

Keep development branches on the ordinary Git repository. Overleaf does not
support multiple branches, tags, LFS, or nested Git submodules. Symlinks become
ordinary files and executable permissions are not preserved.

Moving or renaming a Git file becomes deletion/recreation on the web side and
can lose its comments or tracked changes. Even other Git pushes may displace
annotations. If collaborators actively use them, identify the affected files
and agree on a suitable edit path before a destructive metadata change; use
the browser when retaining annotations is essential. Folder renames can leave
an empty old folder; handle this in the editor rather than guessing a delete.

## Diagnose the actual failure

- Authentication failure: check token validity, username, project membership,
  and the copied integration URL. Do not substitute the web password.
- Rejected reference: confirm the branch, fetch new web edits, and inspect
  unsupported files or project limits before retrying.
- Missing Git menu: check entitlement or the instance's Git Bridge capability;
  ordinary CE does not acquire native Git by changing a user setting.
- TLS/network failure: verify DNS, certificates, proxy behavior, and the
  instance endpoint. A per-command DNS override with correct SNI may help
  diagnose a fake-DNS proxy; avoid global proxy changes, fixed DDNS IPs, and
  TLS bypasses.

Sources checked 2026-10-07:

- [Overleaf native Git documentation](https://docs.overleaf.com/integrations-and-add-ons/git-integration-and-github-synchronization/git-integration)
- [Git authentication tokens](https://docs.overleaf.com/integrations-and-add-ons/git-integration-and-github-synchronization/git-integration/git-integration-authentication-tokens)
