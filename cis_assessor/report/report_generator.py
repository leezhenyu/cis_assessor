"""
CIS Assessor — Report Generators (HTML, JSON, CSV)
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import AssessmentReport
from config import REPORT_HTML, REPORT_JSON, REPORT_CSV, TOOL_NAME, TOOL_VERSION


# ─── HTML Report ─────────────────────────────────────────────────────────────

def _render_html(report: AssessmentReport, output_dir: Path) -> str:
    """Render the HTML report using Jinja2."""
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        raise RuntimeError(
            "jinja2 is required for HTML reports. Install it with: pip install jinja2"
        )

    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report_template.html")
    html = template.render(report=report)

    out_path = output_dir / REPORT_HTML
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


# ─── JSON Report ─────────────────────────────────────────────────────────────

def _render_json(report: AssessmentReport, output_dir: Path) -> str:
    """Render a machine-readable JSON report."""

    def result_to_dict(r):
        return {
            "rule_id":             r.rule_id,
            "rule_title":          r.rule_title,
            "rule_section":        r.rule_section,
            "assessment_type":     r.assessment_type,
            "profiles":            r.profiles,
            "status":              r.status,
            "evaluation_strategy": r.evaluation_strategy,
            "evaluation_reason":   r.evaluation_reason,
            "exit_code":           r.exit_code,
            "timed_out":           r.timed_out,
            "execution_error":     r.execution_error,
            "evidence_path":       r.evidence_path,
            "duration_ms":         r.duration_ms,
            "timestamp":           r.timestamp,
            "raw_stdout":          r.raw_stdout,
            "raw_stderr":          r.raw_stderr,
        }

    payload = {
        "metadata": {
            "tool":                TOOL_NAME,
            "tool_version":        TOOL_VERSION,
            "benchmark":           report.benchmark_name,
            "benchmark_version":   report.benchmark_version,
            "profile":             report.profile,
            "assessment_date":     report.assessment_date,
            "assessment_end":      report.assessment_end,
            "duration_seconds":    round(report.assessment_duration_s, 2),
        },
        "host": {
            "hostname":       report.system.hostname,
            "ip_addresses":   report.system.ip_addresses,
            "os_name":        report.system.os_name,
            "os_version":     report.system.os_version,
            "kernel_version": report.system.kernel_version,
            "architecture":   report.system.architecture,
            "selinux_status": report.system.selinux_status,
            "run_as_user":    report.system.run_as_user,
            "uptime":         report.system.uptime,
        },
        "summary": {
            "total":         report.summary.total,
            "passed":        report.summary.passed,
            "failed":        report.summary.failed,
            "manual":        report.summary.manual,
            "errors":        report.summary.errors,
            "skipped":       report.summary.skipped,
            "score_percent": report.summary.score_percent,
        },
        "results": [result_to_dict(r) for r in report.results],
    }

    out_path = output_dir / REPORT_JSON
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return str(out_path)


# ─── CSV Report ──────────────────────────────────────────────────────────────

def _render_csv(report: AssessmentReport, output_dir: Path) -> str:
    """Render a flat CSV summary suitable for spreadsheets / GRC import."""
    out_path = output_dir / REPORT_CSV

    columns = [
        "rule_id", "rule_section", "rule_title", "assessment_type",
        "profiles", "status", "evaluation_strategy", "evaluation_reason",
        "exit_code", "timed_out", "duration_ms", "timestamp", "evidence_path",
        "hostname", "assessment_date", "profile",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in report.results:
            writer.writerow({
                "rule_id":             r.rule_id,
                "rule_section":        r.rule_section,
                "rule_title":          r.rule_title,
                "assessment_type":     r.assessment_type,
                "profiles":            " | ".join(r.profiles),
                "status":              r.status,
                "evaluation_strategy": r.evaluation_strategy,
                "evaluation_reason":   r.evaluation_reason.replace("\n", " "),
                "exit_code":           r.exit_code,
                "timed_out":           r.timed_out,
                "duration_ms":         r.duration_ms,
                "timestamp":           r.timestamp,
                "evidence_path":       r.evidence_path,
                "hostname":            report.system.hostname,
                "assessment_date":     report.assessment_date,
                "profile":             report.profile,
            })

    return str(out_path)


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def generate_reports(
    report: AssessmentReport,
    output_dir: Path,
    formats: list = None,
) -> dict:
    """
    Generate all requested report formats.
    Returns a dict: {format: filepath}
    """
    if formats is None:
        formats = ["html", "json", "csv"]

    output_dir.mkdir(parents=True, exist_ok=True)
    generated = {}

    if "json" in formats:
        path = _render_json(report, output_dir)
        generated["json"] = path

    if "csv" in formats:
        path = _render_csv(report, output_dir)
        generated["csv"] = path

    if "html" in formats:
        path = _render_html(report, output_dir)
        generated["html"] = path

    return generated
