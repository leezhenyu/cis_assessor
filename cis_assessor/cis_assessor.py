#!/usr/bin/env python3
"""
CIS Oracle Linux 9 Assessor — Main CLI Entry Point

Usage:
  sudo python3 cis_assessor.py --level 1 --type server
  sudo python3 cis_assessor.py --level 2 --type server --format html
  sudo python3 cis_assessor.py --level 1 --type server --rules 1.1.1.1,1.4.1
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running from the cis_assessor/ package directory
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    TOOL_NAME, TOOL_VERSION, BENCHMARK_NAME, BENCHMARK_VERSION,
    DEFAULT_TIMEOUT_SECONDS, DEFAULT_OUTPUT_DIR, DEFAULT_FORMATS,
    STATUS_PASS, STATUS_FAIL, STATUS_MANUAL, STATUS_ERROR, STATUS_SKIP,
    PROFILE_MAP,
)
from models import AssessmentReport, AssessmentSummary
from loader.rule_loader import load_profile_rules
from engine.assessment_engine import run_assessment
from evidence.evidence_store import init_evidence_dir, save_evidence, save_manifest
from report.report_generator import generate_reports
from utils.system_info import collect_system_info, check_root
from utils.logger import get_logger

# ─── ANSI Colors ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _color_status(status: str) -> str:
    colors = {
        STATUS_PASS:   GREEN  + "✅ PASS"   + RESET,
        STATUS_FAIL:   RED    + "❌ FAIL"   + RESET,
        STATUS_MANUAL: YELLOW + "📋 MANUAL" + RESET,
        STATUS_ERROR:  YELLOW + "⚠️  ERROR"  + RESET,
        STATUS_SKIP:   GRAY   + "⏭  SKIP"   + RESET,
    }
    return colors.get(status, status)


def _print_banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║         CIS Oracle Linux 9 Benchmark Assessor                ║
║         {BENCHMARK_VERSION}  ·  Tool v{TOOL_VERSION}                          ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def _make_output_dir(base: str, hostname: str, timestamp: str) -> Path:
    safe_ts = timestamp[:19].replace(":", "-").replace("T", "_")
    dir_name = f"{hostname}_{safe_ts}"
    out = Path(base) / dir_name
    out.mkdir(parents=True, exist_ok=True)
    return out


def _parse_id_list(s: str) -> list:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def _progress_printer(verbose: bool):
    """Returns a progress callback for the assessment engine."""
    status_counts = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_MANUAL: 0, STATUS_ERROR: 0, STATUS_SKIP: 0}

    def callback(idx: int, total: int, result):
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        pct = int(idx / total * 100)
        bar_len = 30
        filled = int(bar_len * idx / total)
        bar = "█" * filled + "░" * (bar_len - filled)

        if verbose:
            icon = _color_status(result.status)
            print(f"  [{idx:>3}/{total}] {icon}  {result.rule_id:<10} {result.rule_title[:55]}")
        else:
            # Compact progress bar (overwrite same line)
            p = f"  [{bar}] {pct:>3}%  " \
                f"{GREEN}{status_counts[STATUS_PASS]}P{RESET} " \
                f"{RED}{status_counts[STATUS_FAIL]}F{RESET} " \
                f"{YELLOW}{status_counts[STATUS_MANUAL]}M{RESET} " \
                f"{YELLOW}{status_counts.get(STATUS_ERROR, 0)}E{RESET}" \
                f"   {result.rule_id}"
            print(f"\r{p}", end="", flush=True)
            if idx == total:
                print()  # newline at end

    return callback


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="cis_assessor",
        description=f"{TOOL_NAME} v{TOOL_VERSION} — CIS Oracle Linux 9 Benchmark v2.0.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 cis_assessor.py --level 1 --type server
  sudo python3 cis_assessor.py --level 2 --type server --format html --output-dir /var/reports
  sudo python3 cis_assessor.py --level 1 --type workstation --rules 1.1.1.1,1.4.1
  sudo python3 cis_assessor.py --level 1 --type server --skip-manual --timeout 30
  sudo python3 cis_assessor.py --level 2 --type server --dry-run
        """,
    )

    # Required
    parser.add_argument(
        "--level", "-l", type=int, choices=[1, 2], required=True,
        help="CIS benchmark level (1 or 2)"
    )
    parser.add_argument(
        "--type", "-t", choices=["server", "workstation"], required=True,
        dest="system_type",
        help="Target system type"
    )

    # Optional
    parser.add_argument(
        "--output-dir", "-o", default=DEFAULT_OUTPUT_DIR, metavar="DIR",
        help=f"Output directory for reports (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--format", "-f", dest="formats",
        default=",".join(DEFAULT_FORMATS), metavar="FORMATS",
        help="Comma-separated report formats: html,json,csv (default: all)"
    )
    parser.add_argument(
        "--rules", metavar="IDs",
        help="Only assess these rule IDs (comma-separated, e.g. 1.1.1.1,1.4.1)"
    )
    parser.add_argument(
        "--skip-rules", metavar="IDs",
        help="Skip these rule IDs (comma-separated)"
    )
    parser.add_argument(
        "--skip-manual", action="store_true",
        help="Skip manual rules entirely (default: mark as MANUAL)"
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, metavar="SECS",
        help=f"Per-rule audit timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose output (show each rule inline)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List rules that would be assessed without running them"
    )
    parser.add_argument(
        "--no-root-warn", action="store_true",
        help="Suppress the non-root warning"
    )
    parser.add_argument(
        "--version", action="version",
        version=f"{TOOL_NAME} v{TOOL_VERSION}"
    )

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    _print_banner()

    log_file = None  # Will be set after output dir is created
    logger = get_logger("cis_assessor", verbose=args.verbose)

    # ── Root check ──────────────────────────────────────────────────────
    if not check_root() and not args.no_root_warn:
        print(f"{YELLOW}⚠️  Warning: Not running as root. Many CIS checks require "
              f"root access and may fail or return incomplete results.{RESET}\n")

    # ── Resolve options ─────────────────────────────────────────────────
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    include_ids = _parse_id_list(args.rules)
    exclude_ids = _parse_id_list(args.skip_rules)

    # Get the canonical profile name
    profile_key = (args.level, args.system_type)
    profile_list = PROFILE_MAP.get(profile_key, [])
    if args.level == 2:
        profile_display = f"Level 2 - {args.system_type.title()} (includes Level 1)"
    else:
        profile_display = f"Level 1 - {args.system_type.title()}"

    # ── Load Rules ────────────────────────────────────────────────────
    print(f"{BOLD}📋 Loading rules for: {CYAN}{profile_display}{RESET}")
    try:
        rules = load_profile_rules(
            level=args.level,
            system_type=args.system_type,
            include_ids=include_ids if include_ids else None,
            exclude_ids=exclude_ids if exclude_ids else None,
        )
    except FileNotFoundError as e:
        print(f"{RED}❌ Error: {e}{RESET}")
        sys.exit(1)

    automated = sum(1 for r in rules if r.assessment_type == "Automated")
    manual    = sum(1 for r in rules if r.assessment_type == "Manual")
    print(f"   {BOLD}{len(rules)}{RESET} rules loaded  "
          f"({GREEN}{automated} automated{RESET}, {YELLOW}{manual} manual{RESET})\n")

    # ── Dry-run mode ─────────────────────────────────────────────────
    if args.dry_run:
        print(f"{BOLD}🔍 Dry-run mode — rules that WOULD be assessed:{RESET}\n")
        for r in rules:
            type_str = f"{GRAY}(Manual){RESET}" if r.assessment_type == "Manual" else "(Auto) "
            print(f"  {CYAN}{r.id:<12}{RESET} {type_str}  {r.title}")
        print(f"\n{BOLD}Total:{RESET} {len(rules)} rules")
        return 0

    # ── Collect System Info ───────────────────────────────────────────
    print(f"{BOLD}🖥  Collecting system information...{RESET}")
    system_info = collect_system_info()
    print(f"   Hostname   : {BOLD}{system_info.hostname}{RESET}")
    print(f"   IP Address : {', '.join(system_info.ip_addresses)}")
    print(f"   OS         : {system_info.os_name}")
    print(f"   Kernel     : {system_info.kernel_version}")
    print(f"   Run As     : {system_info.run_as_user}\n")

    # ── Prepare Output Directory ──────────────────────────────────────
    start_time = datetime.now(tz=timezone.utc).astimezone()
    start_iso  = start_time.isoformat()
    output_dir = _make_output_dir(args.output_dir, system_info.hostname, start_iso)
    evidence_dir = init_evidence_dir(output_dir)

    # Set up file logging into the output dir
    logger = get_logger("cis_assessor",
                        log_file=str(output_dir / "assessment.log"),
                        verbose=args.verbose)

    print(f"{BOLD}📂 Output directory:{RESET} {output_dir}\n")

    # ── Pre-populate report ───────────────────────────────────────────
    report = AssessmentReport(
        benchmark_name=BENCHMARK_NAME,
        benchmark_version=BENCHMARK_VERSION,
        profile=profile_display,
        assessment_date=start_iso,
        assessment_end="",
        assessment_duration_s=0.0,
        assessor_version=TOOL_VERSION,
        system=system_info,
    )

    # ── Run Assessment ────────────────────────────────────────────────
    print(f"{BOLD}{'═' * 62}")
    print(f"🚀 Starting Assessment  [{start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}]")
    print(f"{'═' * 62}{RESET}\n")

    wall_start = time.monotonic()

    # Build a rule_map for evidence store
    rule_map = {r.id: r for r in rules}

    def progress(idx, total, result):
        # Save evidence immediately (while we have the result)
        rule = rule_map.get(result.rule_id)
        ev_path = save_evidence(result, evidence_dir, rule=rule)
        result.evidence_path = ev_path

        # Print progress
        _progress_printer(args.verbose)(idx, total, result)

    results = run_assessment(
        rules=rules,
        timeout=args.timeout,
        skip_manual=args.skip_manual,
        verbose=args.verbose,
        progress_callback=progress,
    )

    wall_end = time.monotonic()
    end_time = datetime.now(tz=timezone.utc).astimezone()

    # ── Finalize Report ───────────────────────────────────────────────
    report.results = results
    report.assessment_end = end_time.isoformat()
    report.assessment_duration_s = round(wall_end - wall_start, 2)
    report.compute_summary()

    save_manifest(results, output_dir)

    # ── Print Summary ─────────────────────────────────────────────────
    s = report.summary
    print(f"\n{BOLD}{'═' * 62}")
    print(f"📊 Assessment Complete  [{end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}]")
    print(f"{'═' * 62}{RESET}")
    print(f"   Total rules : {BOLD}{s.total}{RESET}")
    print(f"   {GREEN}✅ Pass    : {s.passed}{RESET}")
    print(f"   {RED}❌ Fail    : {s.failed}{RESET}")
    print(f"   {YELLOW}📋 Manual  : {s.manual}{RESET}")
    print(f"   {YELLOW}⚠️  Error   : {s.errors}{RESET}")
    if s.skipped:
        print(f"   {GRAY}⏭  Skipped : {s.skipped}{RESET}")
    print()
    score_color = GREEN if s.score_percent >= 85 else (YELLOW if s.score_percent >= 60 else RED)
    print(f"   {BOLD}Score      : {score_color}{s.score_percent}%{RESET} "
          f"({s.passed}/{s.passed + s.failed} automated)")
    print(f"   Duration   : {report.assessment_duration_s:.1f}s\n")

    # ── Print Failures (if any) ───────────────────────────────────────
    failed = [r for r in results if r.status == STATUS_FAIL]
    if failed:
        print(f"{BOLD}{RED}❌ Failed Rules ({len(failed)}):{RESET}")
        for r in failed:
            reason_short = r.evaluation_reason[:80].replace("\n", " ")
            print(f"   {CYAN}{r.rule_id:<12}{RESET} {r.rule_title[:55]}")
            print(f"               {GRAY}→ {reason_short}{RESET}")
        print()

    errors = [r for r in results if r.status == STATUS_ERROR]
    if errors:
        print(f"{BOLD}{YELLOW}⚠️  Errors ({len(errors)}):{RESET}")
        for r in errors:
            print(f"   {CYAN}{r.rule_id:<12}{RESET} {r.rule_title[:55]}")
            print(f"               {GRAY}→ {r.evaluation_reason[:80]}{RESET}")
        print()

    # ── Generate Reports ──────────────────────────────────────────────
    print(f"{BOLD}📄 Generating reports ({', '.join(formats)})...{RESET}")
    generated = generate_reports(report, output_dir, formats)
    for fmt, path in generated.items():
        print(f"   {CYAN}{fmt.upper():5}{RESET} → {path}")

    print(f"\n{BOLD}{GREEN}✅ Assessment complete. Reports saved to:{RESET}")
    print(f"   {output_dir}\n")

    # Return non-zero exit code if there are failures (useful for CI/CD)
    return 1 if s.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
