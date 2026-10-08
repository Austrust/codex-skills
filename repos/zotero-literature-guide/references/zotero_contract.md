# Zotero Contract

Read this before preparing or executing Zotero writes.

## Safety Model

Guide generation is dry-run by default:

```text
build-guide -> local files and manifest only
attach-to-zotero -> only after explicit user confirmation
```

Do not edit the Zotero database directly. Use Zotero's supported local interface, API, or a manifest for manual/automated attachment.

For batch runs, generation agents are never allowed to write Zotero. They may only produce local `outputs/<item_key>/` packages. Use local package evidence, not agent IDs, as the source of truth:

```text
status.json
attachment_manifest.json
harness reports
zotero_attach_report.json after write
```

If package agents are complete or blocked at a user decision gate, stop agent monitors and delete heartbeat files immediately. A heartbeat loop must not continue after all active work is either done or waiting for user choice.

## Local Lookup

Default read route:

```text
http://127.0.0.1:23119/api/users/0
```

If the OpenAI Zotero plugin is installed, prefer its helper for readiness and read-only discovery:

```text
<plugin-root>/skills/zotero/scripts/zotero.py status --json
<plugin-root>/skills/zotero/scripts/zotero.py search "<query>" --json --with-bibtex-keys
<plugin-root>/skills/zotero/scripts/zotero.py children <item_key> --json
<plugin-root>/skills/zotero/scripts/zotero.py file-url <attachment_key>
<plugin-root>/skills/zotero/scripts/zotero.py fulltext <attachment_key> --out <file>
<plugin-root>/skills/zotero/scripts/zotero.py export-bibtex --item-key <item_key>
```

Resolve `<plugin-root>` from the installed Codex plugin cache or from the active plugin skill path. Treat the helper as a stable wrapper around Zotero Desktop's local API and connector server. Still save package-local `source/zotero_item.json`, `source/zotero_children.json`, and `source/zotero_lookup.json`; the helper supplements provenance but does not replace those files.

Use this local API for item and child attachment lookup:

```text
GET /items/<itemKey>?format=json
GET /items/<itemKey>/children?format=json
```

Before lookup, check:

```text
GET http://127.0.0.1:23119/connector/ping
```

On Windows/PowerShell, prefer `curl.exe` or Python `urllib` for Zotero local API checks. Do not rely on PowerShell `Invoke-WebRequest`; it can fail with an unexpected closed connection even when Zotero is healthy.

Examples:

```powershell
curl.exe -sS http://127.0.0.1:23119/connector/ping
curl.exe -sS "http://127.0.0.1:23119/api/users/0/items/<item_key>/children?format=json"
```

`connector/ping` only proves Zotero's Connector endpoint is reachable. It does not prove Better BibTeX/ztoolkit debug bridge has loaded. For bridge writes, wait for Zotero to finish startup and retry the bridge URL if the first attempt produces no result file.

Save all raw lookup responses under `source/` in the guide package. Do not query or mutate `zotero.sqlite` directly.

Use `scripts/zotero_local_lookup.py` as the default implementation. It should:

```text
save zotero_item.json
save zotero_children.json
filter PDF child attachments
resolve file:/// enclosure URLs to local paths
fallback to zotero_data_dir/storage/<attachment_key>/<filename>
emit zotero_lookup.json
```

There are two distinct Zotero helpers:

```text
OpenAI Zotero plugin helper:
  use for status/probe, title search, children listing, file-url, fulltext, BibTeX export, and BibTeX/RIS import.

Zotero Guide Helper plugin:
  use as the default confirmed guide-PDF attachment writer.
```

The Zotero Guide Helper plugin health endpoint is:

```text
GET http://127.0.0.1:23119/guide-helper/health
```

Use it for write-back only when the health payload reports:

```text
ok=true
plugin=zotero-guide-helper
writeEnabled=true
authRequiredForWrites=true
```

If the endpoint is missing or returns another payload, recommend installing the bundled XPI:

```text
<skill-root>/assets/zotero-guide-helper/zotero-guide-helper.xpi
```

After installation, retry the health endpoint. Use the Better BibTeX/ztoolkit debug bridge only when plugin installation is blocked or the user explicitly asks for the fallback.

## Metadata Priority

Use metadata in this order:

```text
1. Zotero item fields
2. metadata.yaml override
3. PDF/MinerU detected metadata
4. DOI/Crossref lookup if missing or obviously abnormal
```

If Zotero metadata and PDF metadata disagree:

```text
do not update Zotero
use Zotero metadata in the guide
record metadata_mismatch in build_log.md
record PDF title as source_pdf_title
```

## Attachment Defaults

Default Zotero attachment:

```text
local file: literature_guide.pdf
Zotero display title: 文献导读.pdf
attachment mode: stored
```

Do not attach by default:

```text
literature_guide.md
extracted.md
assets/
attachment_manifest.json
build_log.md
status.json
```

Keep those in the local package.

## Required Tags

When the user confirms attachment, add these tags by default:

```text
codex-literature-guide
guide-needs-review
```

Do not add a Zotero note by default.

## Duplicate Guide Attachments

Before attaching, inspect existing item attachments.

If existing guide attachment(s) are detected, stop and ask for one of:

```text
replace
keep-both
cancel
```

Default behavior is to stop. Do not replace, delete, or add a second guide attachment unless the user explicitly chooses `replace` or `keep-both`. If the user chooses to keep the original/old attachment, treat that as `cancel` for the new guide write and leave the new package local.

Detection signals:

```text
title: 文献导读.pdf
filename: literature_guide.pdf
tag: codex-literature-guide
known attachment key from prior manifest
```

PowerShell terminal mojibake such as `鏂囩尞瀵艰.pdf` is not proof that the Zotero title is wrong. Scripts should write Chinese titles as UTF-8 JSON strings or Unicode escapes and compare the decoded Zotero API title `文献导读.pdf`. Duplicate detection should consider title, filename, tag, and prior manifest key together.

Do not overwrite or delete existing attachments without explicit user choice.

## Attachment Eligibility

Only attach when:

```text
literature_guide.pdf exists
literature_guide.pdf size > 0
attachment_manifest.json exists
guide_validation status is pass or warn
harness_report status is pass, or warn only for an explicitly accepted non-content extraction risk
status.json state is ready_to_attach
status.json status is ready-to-attach
if status.json contains translation_model, content_review records Codex/human review with reviewer, reviewed_at, and scope/report evidence
```

`attachment_manifest.json` should be generated with `scripts/build_attachment_manifest.py --status-json <package>/status.json --harness-report-json <package>/harness_report.json`. A manifest created without these gates is not sufficient evidence for Zotero writing.

Do not attach when:

```text
guide_validation status is fail
harness_report status is fail
status.json contains translation_model and no evidence-bearing Codex/human review has promoted the content out of needs-review
PDF is missing
paragraph numbering is not continuous
required 原文/翻译/讲解 blocks are missing
many image references are missing
```

If validation or harness is `warn`, attachment is allowed only when the warning is documented and accepted. A warning caused by external/local model draft generation is not enough for final attach unless the user explicitly asks to attach a draft.

Batch attach eligibility must be reported as a decision table before any write:

```text
ready
warn
duplicate gate
PDF gate
blocked
```

Only rows the user explicitly approves may proceed to the Zotero write stage.

## Manifest Shape

Use `attachment_manifest.json`:

```json
{
  "schema_version": "0.1",
  "zotero_item_key": "ABCD1234",
  "attachment_mode": "stored",
  "package_dir": "C:/path/to/package",
  "guide_pdf": {
    "path": "C:/path/to/package/literature_guide.pdf",
    "title": "文献导读.pdf",
    "mime_type": "application/pdf"
  },
  "default_tags": [
    "codex-literature-guide",
    "guide-needs-review"
  ],
  "optional_updates": {
    "note": null
  },
  "existing_guide_attachments": [],
  "zotero_source_attachment_key": "SOURCEPDF1",
  "zotero_guide_attachment_key": null,
  "status": "ready_to_attach"
}
```

Keep `zotero_source_attachment_key` and `zotero_guide_attachment_key` separate everywhere. The source key is the original paper PDF child used for extraction; the guide key is the newly imported `文献导读.pdf` child. Never copy one into the other.

## Confirmed Attachment Execution

Goal: after the user explicitly confirms, attach only `literature_guide.pdf` to the Zotero parent item as a stored PDF attachment. Keep all other package files local.

Preferred route: Zotero Guide Helper plugin.

1. Verify Zotero is running and the Zotero Guide Helper plugin is loaded:

```powershell
curl.exe -sS http://127.0.0.1:23119/guide-helper/health
```

2. If health fails or does not report `plugin=zotero-guide-helper`, recommend installing:

```text
<skill-root>/assets/zotero-guide-helper/zotero-guide-helper.xpi
```

Do not silently fall back to the debug bridge. Install the plugin first unless installation is blocked or the user explicitly requests the fallback.

3. Confirm eligibility from `attachment_manifest.json`, `status.json`, and the pre-attach harness.
4. Run duplicate preflight with the plugin list endpoint:

```powershell
curl.exe -sS "http://127.0.0.1:23119/guide-helper/items/<item_key>/guide-attachments"
```

Detect duplicates by title `文献导读.pdf`, filename `literature_guide.pdf`, tag `codex-literature-guide`, or known attachment key from the manifest. If duplicates exist, stop for `replace / keep-both / cancel`; the MVP plugin supports `error` and `keep-both`, not replace/delete.

5. Attach with the bundled client:

```powershell
python <skill-root>\scripts\zotero_guide_helper_attach.py `
  --manifest <package>\attachment_manifest.json `
  --report <package>\zotero_helper_attach_report.json
```

The client computes SHA256, calls `POST /guide-helper/attach-guide`, re-queries Zotero local API children, verifies title, `imported_file`, `application/pdf`, required tags, and storage SHA256.

6. Treat HTTP 409 as a duplicate gate, not a failure to work around. Ask the user for `replace / keep-both / cancel`. `keep-both` requires explicit approval and maps to `--duplicate-policy keep-both`; replace is not implemented in the MVP plugin.
7. Only after verification passes, update `zotero_attach_report.json`, `attachment_manifest.json`, and `status.json` to `attached`. Record:
   - `attached_via: zotero_guide_helper_plugin`
   - `actual_attachment_mode: stored`
   - `zotero_source_attachment_key`
   - `zotero_guide_attachment_key`
   - `zotero_attachment.key` for the guide PDF only
   - `zotero_attachment.links.enclosure.href` or plugin `storagePath`

### Better BibTeX Bridge Fallback

Use this route only when the Zotero Guide Helper plugin cannot be installed or the user explicitly asks for fallback. It modifies Zotero through Zotero's own JavaScript runtime, not by editing `zotero.sqlite` directly.

Preconditions:

```text
Zotero is installed and can be restarted.
Better BibTeX / ztoolkit debug bridge is installed.
The package has literature_guide.pdf and attachment_manifest.json.
The parent Zotero item key is known.
```

Execution pattern:

1. Read the parent item key from `attachment_manifest.json`.
2. Resolve the parent internal `itemID` from Zotero local API when possible; if needed, use a read-only immutable SQLite query only for lookup, never for mutation.
3. Run a PowerShell/Python-side duplicate preflight against the before-write children response. If duplicate signals exist, stop for `replace / keep-both / cancel`.
4. Fully stop Zotero and wait until the process has exited. Do not write the temporary bridge password while Zotero is still running, because Zotero may rewrite `prefs.js` during shutdown and erase the password.
5. Create a timestamped `prefs.js` backup, then write a temporary random `extensions.zotero.debug-bridge.password` in the active Zotero profile.
6. Start Zotero from its installation directory with that directory as `WorkingDirectory`. Do not use hidden-window/background starts for bridge writes; they can leave the local API or ztoolkit bridge unavailable.
7. Wait until Zotero local API is reachable, then wait/retry for Better BibTeX/ztoolkit bridge readiness. A successful `connector/ping` is not enough.
8. Open a `zotero://ztoolkit-debug?...` URL that points to a local JavaScript file. If the expected bridge result file is not written, stop, clean the temporary password, restart Zotero from the installation directory, then diagnose/retry instead of assuming success or blindly repeating URL opens.
9. In that JavaScript file, run Zotero runtime APIs equivalent to:

```javascript
const item = await Zotero.Items.getByLibraryAndKeyAsync(libraryID, itemKey);
if (!item) throw new Error(`Parent item not found: ${itemKey}`);
const children = item.getAttachments().map(id => Zotero.Items.get(id)).filter(Boolean);
const duplicate = children.find(child => {
  const title = child.getField('title');
  const tags = child.getTags().map(t => t.tag);
  const file = child.getFilePath && child.getFilePath();
  return title === '文献导读.pdf'
    || tags.includes('codex-literature-guide')
    || (file && /literature_guide\.pdf$/i.test(file));
});
if (duplicate) throw new Error(`Duplicate guide attachment: ${duplicate.key}`);
const att = await Zotero.Attachments.importFromFile({
  file: guidePdfPath,
  parentItemID: item.id,
});
att.setField('title', '文献导读.pdf');
att.addTag('codex-literature-guide');
att.addTag('guide-needs-review');
await att.saveTx();
Zotero.Prefs.clear('extensions.zotero.debug-bridge.password', true);
```

The runtime JavaScript must do only these operations: resolve the parent by item key, run a second duplicate check, import `literature_guide.pdf` as a stored child attachment, set title `文献导读.pdf`, add the default tags, write a result JSON, and clear the temporary bridge password.

Verify after either route:

- `GET http://127.0.0.1:23119/api/users/0/items/<item_key>/children?format=json` shows the new child; use `curl.exe` or Python `urllib`.
- child title is `文献导读.pdf`.
- `linkMode` is `imported_file` / stored.
- `contentType` is `application/pdf`.
- tags include `codex-literature-guide` and `guide-needs-review`.
- Zotero storage PDF exists.
- storage PDF SHA256 equals the package `literature_guide.pdf` SHA256.
- If the fallback bridge was used, `prefs.js` no longer contains `extensions.zotero.debug-bridge.password`.

Security and data-safety rules:

```text
Never mutate zotero.sqlite directly.
Never leave the debug bridge password in prefs.js.
Always keep a prefs.js timestamped backup before changing the temporary bridge password.
Do not report success unless Zotero local API and file-hash verification both pass.
If password cleanup fails, stop and report the exact profile path requiring manual cleanup.
If the bridge result file is missing, first clean `prefs.js` and restart Zotero from its installation directory, then diagnose bridge loading/timing. Do not treat an opened bridge URL as proof of success.
```
