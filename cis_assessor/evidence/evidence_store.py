"""
CIS Assessor — Evidence Store
Saves per-rule audit evidence to disk.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import AuditResult
from config import EVIDENCE_DIR_NAME, EVIDENCE_MANIFEST


def init_evidence_dir(output_dir: Path) -> Path:
    """Create and return the evidence subdirectory."""
    evidence_dir = output_dir / EVIDENCE_DIR_NAME
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def save_evidence(result: AuditResult, evidence_dir: Path, rule: "Rule" = None) -> str:
    """
    Save raw evidence for a single rule.
    Returns the path to the saved evidence file.
    """
    filename = f"{result.rule_id}.txt"
    filepath = evidence_dir / filename

    # Format status with icon
    icon = {"PASS": "✅", "FAIL": "❌", "MANUAL": "📋", "ERROR": "⚠️", "SKIP": "⏭️"}.get(result.status, "?")

    # Gather rule details (for audit text)
    audit_text = ""
    remediation_text = ""
    description_text = ""
    if rule:
        audit_text = rule.audit
        remediation_text = rule.remediation
        description_text = rule.description

    lines = [
        "=" * 80,
        f"CIS Oracle Linux 9 Benchmark v2.0.0",
        f"Rule ID   : {result.rule_id}",
        f"Title     : {result.rule_title}",
        f"Type      : {result.assessment_type}",
        f"Profiles  : {', '.join(result.profiles)}",
        f"Date/Time : {result.timestamp}",
        f"Status    : {icon} {result.status}",
        f"Duration  : {result.duration_ms}ms",
        "=" * 80,
    ]

    if description_text:
        lines += ["", "--- DESCRIPTION ---", description_text]

    lines += ["", "--- EVALUATION ---",
              f"Strategy  : {result.evaluation_strategy}",
              f"Reasoning : {result.evaluation_reason}"]

    if audit_text:
        lines += ["", "--- AUDIT PROCEDURE ---", audit_text]

    lines += ["", "--- STDOUT ---",
              result.raw_stdout if result.raw_stdout.strip() else "(no output)"]

    if result.raw_stderr and result.raw_stderr.strip():
        lines += ["", "--- STDERR ---", result.raw_stderr]

    lines += ["", f"--- EXIT CODE ---", str(result.exit_code)]

    if result.timed_out:
        lines += ["", "⚠️  AUDIT TIMED OUT"]

    if result.execution_error:
        lines += ["", f"--- EXECUTION ERROR ---", result.execution_error]

    if remediation_text and result.status in ("FAIL", "ERROR"):
        lines += ["", "--- REMEDIATION ---", remediation_text]

    lines += ["", "=" * 80]

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def save_manifest(results: List[AuditResult], output_dir: Path):
    """Save a JSON index of all evidence files."""
    manifest = {
        "generated_at": datetime.now(tz=timezone.utc).astimezone().isoformat(),
        "total": len(results),
        "rules": [
            {
                "rule_id": r.rule_id,
                "title": r.rule_title,
                "status": r.status,
                "evidence_file": r.evidence_path,
                "timestamp": r.timestamp,
            }
            for r in results
        ],
    }
    manifest_path = output_dir / EVIDENCE_DIR_NAME / EVIDENCE_MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
