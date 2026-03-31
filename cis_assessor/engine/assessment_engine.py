"""
CIS Assessor — Assessment Engine
Orchestrates iterating rules, running audits, evaluating results.
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import Rule, AuditResult, ExecutionResult, EvaluationResult
from config import (
    STATUS_MANUAL, STATUS_ERROR, STATUS_SKIP,
    TYPE_MANUAL, DEFAULT_TIMEOUT_SECONDS
)
from engine.audit_runner import run_audit
from engine.result_evaluator import evaluate
from utils.logger import get_logger

logger = get_logger("cis_assessor.engine")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat()


def assess_single_rule(
    rule: Rule,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    skip_manual: bool = False,
) -> AuditResult:
    """Run the assessment for one rule and return its AuditResult."""
    ts_start = time.monotonic()
    timestamp = _now_iso()

    # --- Skip Manual rules if requested ---
    if rule.assessment_type == TYPE_MANUAL and skip_manual:
        return AuditResult(
            rule_id=rule.id,
            rule_title=rule.title,
            rule_section=rule.section,
            assessment_type=rule.assessment_type,
            profiles=rule.profiles,
            status=STATUS_SKIP,
            evaluation_strategy="skipped",
            evaluation_reason="Manual rule skipped by --skip-manual flag",
            timestamp=timestamp,
            duration_ms=0,
        )

    # --- Mark Manual rules (but still try to collect evidence) ---
    if rule.assessment_type == TYPE_MANUAL:
        exec_result, script_used = run_audit(rule.id, rule.audit, timeout)
        duration_ms = int((time.monotonic() - ts_start) * 1000)
        return AuditResult(
            rule_id=rule.id,
            rule_title=rule.title,
            rule_section=rule.section,
            assessment_type=rule.assessment_type,
            profiles=rule.profiles,
            status=STATUS_MANUAL,
            evaluation_strategy="manual",
            evaluation_reason="Manual review required — automated assessment not possible",
            raw_stdout=exec_result.stdout,
            raw_stderr=exec_result.stderr,
            exit_code=exec_result.exit_code,
            timed_out=exec_result.timed_out,
            execution_error=exec_result.execution_error,
            timestamp=timestamp,
            duration_ms=duration_ms,
        )

    # --- Automated rules ---
    exec_result, script_used = run_audit(rule.id, rule.audit, timeout)
    eval_result: EvaluationResult = evaluate(rule, exec_result)
    duration_ms = int((time.monotonic() - ts_start) * 1000)

    return AuditResult(
        rule_id=rule.id,
        rule_title=rule.title,
        rule_section=rule.section,
        assessment_type=rule.assessment_type,
        profiles=rule.profiles,
        status=eval_result.status,
        evaluation_strategy=eval_result.strategy,
        evaluation_reason=eval_result.reason,
        raw_stdout=exec_result.stdout,
        raw_stderr=exec_result.stderr,
        exit_code=exec_result.exit_code,
        timed_out=exec_result.timed_out,
        execution_error=exec_result.execution_error,
        timestamp=timestamp,
        duration_ms=duration_ms,
    )


def run_assessment(
    rules: List[Rule],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    skip_manual: bool = False,
    verbose: bool = False,
    progress_callback: Optional[Callable[[int, int, AuditResult], None]] = None,
) -> List[AuditResult]:
    """
    Run assessment for a list of rules.
    Calls progress_callback(current_index, total, result) after each rule.
    Returns list of AuditResult.
    """
    results: List[AuditResult] = []
    total = len(rules)

    for idx, rule in enumerate(rules, start=1):
        if verbose:
            logger.debug(f"  [{idx:>3}/{total}] Assessing {rule.id}: {rule.title[:60]}")

        try:
            result = assess_single_rule(rule, timeout=timeout, skip_manual=skip_manual)
        except Exception as e:
            # Safety net — engine should never crash
            logger.error(f"  UNEXPECTED ERROR on rule {rule.id}: {e}")
            result = AuditResult(
                rule_id=rule.id,
                rule_title=rule.title,
                rule_section=rule.section,
                assessment_type=rule.assessment_type,
                profiles=rule.profiles,
                status=STATUS_ERROR,
                evaluation_strategy="engine_exception",
                evaluation_reason=f"Unexpected engine error: {str(e)[:200]}",
                timestamp=_now_iso(),
                duration_ms=0,
            )

        results.append(result)

        if progress_callback:
            progress_callback(idx, total, result)

    return results
