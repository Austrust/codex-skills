"""Lean report templates and schema 2 structural checks (standard library only)."""
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

STATUSES = {"complete", "partial", "blocked", "exploratory"}
REPRO = {"reproducible", "partially_reproducible", "not_reproducible", "not_assessed"}
EVIDENCE = {"executed_this_session", "existing_file", "inferred_from_code", "user_provided", "gui_manual", "unknown"}


def report_template(task, language, mode, profile):
    zh = language.startswith("zh")
    headings = (["结果与背景", "方法与输入", "检查与限制", "复现与输出"]
                if zh else ["Result and context", "Method and inputs", "Checks and limitations", "Reproduction and outputs"])
    prompts = ([
        "问题、数据来源、关键结果和单位；只保留读者需要的背景。",
        "输入路径/版本、关键参数及依据、实际执行证据。",
        "相关检查及实际结果；仅说明影响使用的缺口。",
        "工作目录、命令、代码版本、必要环境；链接有用的产物。"
    ] if zh else [
        "Question, data family, finding and units; essential context only.",
        "Input paths/version, consequential parameters and basis, actual execution evidence.",
        "Relevant checks and observed outcomes; material gaps only.",
        "Working directory, command, code version, relevant environment; link useful outputs."
    ])
    status = "exploratory" if mode == "exploratory" else "partial"
    text = f"# {task}\n\n<!-- scientific-data-report profile={profile} -->\n\nAudit status: {status}\nReproducibility: not_assessed\n\n"
    return text + "\n\n".join(f"## {h}\n\nTODO: {p}" for h, p in zip(headings, prompts)) + "\n"


def manifest_template(package_dir, task, mode):
    return {
        "schema_version": "2.0", "profile": "audited",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "task": {"title": task, "mode": mode},
        "report_package_root": str(package_dir.resolve()),
        "audit_status": "exploratory" if mode == "exploratory" else "partial",
        "reproducibility": "not_assessed",
        "inputs": [], "steps": [], "outputs": [], "checks": [],
        "reproduction": {}, "limitations": [],
        "draft": True,
    }


def validate_report(v, folder, manifest):
    report = folder / "REPORT.md"
    if not report.is_file():
        v.error("required file missing: REPORT.md")
        return
    text = report.read_text(encoding="utf-8-sig")
    if not text.strip():
        v.error("REPORT.md is empty")
    if re.search(r"\b(TODO|TBD|FILL_ME)\b", text, re.I):
        (v.warn if v.allow_draft else v.error)("REPORT.md contains unfinished template text")
    fields = {}
    for field, choices in [("Audit status", STATUSES), ("Reproducibility", REPRO)]:
        match = re.search(r"^" + field + r":\s*(\S+)\s*$", text, re.M)
        fields[field] = match.group(1) if match else None
        if fields[field] not in choices:
            v.error(f"REPORT.md has missing or invalid {field}")
    if fields["Audit status"] == "complete" and fields["Reproducibility"] != "reproducible":
        v.error("complete report requires a usable rerun procedure and reproducible status")
    if "profile=audited" in text and not manifest:
        v.error("audited report requires AUDIT_MANIFEST.json")
    # Check ordinary inline Markdown links, including image links; do not fetch URLs.
    for target in re.findall(r"\]\((<[^>]+>|[^)\n]+)\)", text):
        target = target.strip()
        if target.startswith("<"):
            target = target[1:target.index(">")]
        else:
            target = re.split(r'\s+["\']', target, maxsplit=1)[0]
        if target.startswith("#") or urlparse(target).scheme not in {"", "file"}:
            continue
        local = unquote(target.split("#", 1)[0])
        if local and not (folder / local).exists():
            v.error(f"broken local report link: {local}")
    if not manifest:
        return
    if manifest.get("profile") != "audited":
        v.error("schema 2 manifest profile must be audited")
    for key, field in [("audit_status", "Audit status"), ("reproducibility", "Reproducibility")]:
        if manifest.get(key) != fields[field]:
            v.error(f"report/manifest disagreement: {key}")
    if manifest.get("draft"):
        (v.warn if v.allow_draft else v.error)("manifest is still marked draft")
    for key in ["generated_at", "task", "report_package_root"]:
        if not manifest.get(key):
            v.error(f"manifest requires {key}")
    complete = manifest.get("audit_status") == "complete"
    groups = {}
    for key in ["inputs", "steps", "outputs", "checks", "limitations"]:
        items = manifest.get(key)
        if not isinstance(items, list):
            v.error(f"{key} must be a list")
            items = []
        groups[key] = items
    if complete:
        for key in ["inputs", "steps", "outputs", "checks"]:
            if not groups[key]:
                v.error(f"complete audit requires {key}")
        if manifest.get("draft"):
            v.error("complete audit cannot be draft")
    ids = {}
    for kind in ["inputs", "steps", "outputs"]:
        ids[kind] = set()
        for item in groups[kind]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                v.error(f"{kind} entry requires string id")
                continue
            if item["id"] in ids[kind]:
                v.error(f"duplicate {kind} id: {item['id']}")
            ids[kind].add(item["id"])
    def unresolved(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip().lower() in {"", "unknown", "missing", "not_assessed"}
        if isinstance(value, dict):
            return not value or any(unresolved(x) for x in value.values())
        return False
    for kind in ["inputs", "steps", "outputs"]:
        for item in groups[kind]:
            if not isinstance(item, dict):
                continue
            required = {"inputs": ["path", "identity"],
                        "steps": ["method", "parameters", "method_basis", "evidence_type"],
                        "outputs": ["path", "evidence_type"]}[kind]
            for key in required:
                if key not in item or item[key] is None or item[key] == "":
                    v.error(f"{kind} {item.get('id')} requires {key}")
            if complete and kind == "inputs" and unresolved(item.get("identity")):
                v.error(f"complete audit needs input identity: {item.get('id')}")
            if kind != "inputs":
                if item.get("evidence_type") not in EVIDENCE:
                    v.error(f"invalid evidence_type: {item.get('id')}")
                if complete and item.get("evidence_type") in {"unknown", "inferred_from_code"}:
                    v.error(f"complete audit lacks observed evidence: {item.get('id')}")
            if kind == "outputs":
                output_path = item.get("path")
                if isinstance(output_path, str) and not (folder / output_path).exists():
                    v.error(f"output not found: {output_path}")
            relations = {"steps": [("inputs", "inputs")],
                         "outputs": [("derived_from_inputs", "inputs"), ("derived_from_steps", "steps")]}.get(kind, [])
            for key, group in relations:
                refs = item.get(key)
                if not isinstance(refs, list) or not refs or not all(isinstance(x, str) for x in refs):
                    v.error(f"{kind} {item.get('id')} needs nonempty {key} IDs")
                elif set(refs) - ids[group]:
                    v.error(f"unknown lineage IDs in {item.get('id')}.{key}")
    for check in groups["checks"]:
        if not isinstance(check, dict) or not check.get("check") or not check.get("result"):
            v.error("each check requires check and result")
    reproduction = manifest.get("reproduction")
    if not isinstance(reproduction, dict):
        v.error("reproduction must be an object")
    elif complete:
        for key in ["working_directory", "procedure", "code_identity", "environment"]:
            if unresolved(reproduction.get(key)):
                v.error(f"complete audit requires reproduction.{key}")
    if manifest.get("audit_status") == "blocked" and not groups["limitations"]:
        v.error("blocked audit must explain the blocking limitation")
    # Reject scaffold markers anywhere in structured records.
    def walk(value):
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str) and re.search(r"\b(TODO|TBD|FILL_ME)\b", value, re.I):
            (v.warn if v.allow_draft else v.error)("manifest contains unfinished template text")
    walk(manifest)
