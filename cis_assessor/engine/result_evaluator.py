"""
CIS Assessor — Result Evaluator
Determines PASS/FAIL from audit execution output using multiple strategies.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import Rule, ExecutionResult, EvaluationResult
from config import STATUS_PASS, STATUS_FAIL, STATUS_MANUAL, STATUS_ERROR


# ─── Strategy: Embedded Script Verdict ──────────────────────────────────────

def _eval_script_verdict(output: str) -> Optional[EvaluationResult]:
    """
    Check for explicit PASS/FAIL markers produced by CIS benchmark scripts.
    These scripts print lines like:
      - Audit Result:
          ** PASS **
      or
          ** FAIL **
    """
    if "** PASS **" in output:
        return EvaluationResult(
            status=STATUS_PASS,
            strategy="script_verdict",
            reason="Audit script explicitly reported PASS",
        )
    if "** FAIL **" in output:
        # Extract failure reason if available
        reason = "Audit script explicitly reported FAIL"
        m = re.search(r'Reason\(s\) for audit failure[:\s]*(.*?)(?:\n- Correctly set|\Z)', output, re.DOTALL | re.IGNORECASE)
        if m:
            detail = m.group(1).strip()
            if detail:
                reason += f": {detail[:200]}"
        return EvaluationResult(
            status=STATUS_FAIL,
            strategy="script_verdict",
            reason=reason,
        )
    return None


# ─── Strategy: Empty Output Expected ────────────────────────────────────────

_EXPECTS_EMPTY_RE = re.compile(
    r'nothing should be returned|should return nothing|no output|'
    r'verify\s+(?:that\s+)?(?:no\s+lines?\s+are|nothing)',
    re.IGNORECASE
)


def _eval_empty_expected(rule: Rule, stdout: str) -> Optional[EvaluationResult]:
    """
    Some CIS rules say the command should produce no output on a compliant system.
    If we detect this pattern in the audit text and stdout is empty → PASS.
    """
    if not _EXPECTS_EMPTY_RE.search(rule.audit):
        return None
    stripped = stdout.strip()
    if not stripped:
        return EvaluationResult(
            status=STATUS_PASS,
            strategy="empty_output",
            reason="Command produced no output as expected for a compliant system",
        )
    else:
        return EvaluationResult(
            status=STATUS_FAIL,
            strategy="empty_output",
            reason=f"Expected no output, but found: {stripped[:200]}",
        )


# ─── Strategy: Package Not Installed ────────────────────────────────────────

_PKG_NOT_INSTALLED_RE = re.compile(r'package\s+\S+\s+is\s+not\s+installed', re.IGNORECASE)
_PKG_INSTALLED_RE     = re.compile(r'^[\w\-]+\-[\d\.]+', re.MULTILINE)


def _eval_package_check(rule: Rule, stdout: str) -> Optional[EvaluationResult]:
    """
    Handle rules that check whether a package is or is NOT installed.
    Two sub-cases:
      1. "package X is not installed"  → expected in audit  → PASS when output matches
      2. "rpm -q X" returns package version → PASS (it IS installed)
    """
    audit_lower = rule.audit.lower()

    # Case 1: rule expects package to NOT be installed
    if 'not installed' in audit_lower:
        if _PKG_NOT_INSTALLED_RE.search(stdout):
            return EvaluationResult(
                status=STATUS_PASS,
                strategy="package_check",
                reason="Package correctly not installed",
            )
        elif stdout.strip():
            return EvaluationResult(
                status=STATUS_FAIL,
                strategy="package_check",
                reason=f"Package appears to be installed: {stdout.strip()[:100]}",
            )

    # Case 2: rule expects package to be installed (rpm -q returns version string)
    if 'rpm -q' in audit_lower and '<version>' in audit_lower:
        stdout_clean = stdout.strip()
        if stdout_clean and not 'not installed' in stdout_clean.lower():
            return EvaluationResult(
                status=STATUS_PASS,
                strategy="package_check",
                reason=f"Package is installed: {stdout_clean[:100]}",
            )
        else:
            return EvaluationResult(
                status=STATUS_FAIL,
                strategy="package_check",
                reason="Package is not installed but should be",
            )

    return None


# ─── Strategy: Exit Code Fallback ───────────────────────────────────────────

def _eval_exit_code(exec_result: ExecutionResult) -> EvaluationResult:
    """Last-resort: use the script exit code."""
    if exec_result.timed_out:
        return EvaluationResult(
            status=STATUS_ERROR,
            strategy="exit_code",
            reason=f"Audit timed out: {exec_result.execution_error}",
        )
    if exec_result.execution_error and not exec_result.stdout:
        return EvaluationResult(
            status=STATUS_ERROR,
            strategy="exit_code",
            reason=f"Execution error: {exec_result.execution_error}",
        )
    if exec_result.exit_code == 0:
        return EvaluationResult(
            status=STATUS_PASS,
            strategy="exit_code",
            reason="Audit script exited with code 0 (success)",
        )
    return EvaluationResult(
        status=STATUS_FAIL,
        strategy="exit_code",
        reason=f"Audit script exited with code {exec_result.exit_code}",
    )


# ─── Master Evaluator ────────────────────────────────────────────────────────

def evaluate(rule: Rule, exec_result: ExecutionResult) -> EvaluationResult:
    """
    Determine PASS/FAIL/ERROR for a rule given its execution result.
    Tries strategies in priority order.
    """
    # Execution or timeout errors take immediate precedence
    if exec_result.timed_out:
        return EvaluationResult(
            status=STATUS_ERROR,
            strategy="timeout",
            reason=f"Audit script timed out: {exec_result.execution_error or ''}",
        )
    if exec_result.execution_error and exec_result.exit_code == -1 and not exec_result.stdout:
        return EvaluationResult(
            status=STATUS_ERROR,
            strategy="execution_error",
            reason=f"Could not execute audit: {exec_result.execution_error}",
        )

    stdout = exec_result.stdout

    # 1. Script-embedded verdict (most reliable)
    result = _eval_script_verdict(stdout)
    if result:
        return result

    # 2. Empty-output expected
    result = _eval_empty_expected(rule, stdout)
    if result:
        return result

    # 3. Package installation check
    result = _eval_package_check(rule, stdout)
    if result:
        return result

    # 4. Exit code fallback
    return _eval_exit_code(exec_result)
