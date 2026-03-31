"""
CIS Assessor — Data Models
All dataclasses that flow through the assessment pipeline.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Rule:
    """A single CIS benchmark rule loaded from parsed_rules.json."""
    id: str                      # e.g. "1.1.1.1"
    title: str                   # e.g. "Ensure cramfs kernel module is not available"
    assessment_type: str         # "Automated" | "Manual"
    profiles: List[str]          # ["Level 1 - Server", "Level 1 - Workstation"]
    description: str
    rationale: str
    audit: str                   # Full audit text (may contain bash script)
    remediation: str
    default_value: str

    # Derived fields (populated by rule_loader)
    section: str = ""            # e.g. "1.1.1"
    has_script: bool = False     # True if audit contains #!/usr/bin/env bash

    def __post_init__(self):
        if not self.section:
            parts = self.id.split(".")
            self.section = ".".join(parts[:-1]) if len(parts) > 1 else self.id
        self.has_script = "#!/usr/bin/env bash" in self.audit


@dataclass
class ExecutionResult:
    """Raw output from running an audit script/command."""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    execution_error: Optional[str] = None  # e.g. "command not found"


@dataclass
class EvaluationResult:
    """Pass/fail decision with reasoning."""
    status: str       # STATUS_PASS | STATUS_FAIL | STATUS_MANUAL | STATUS_ERROR
    strategy: str     # e.g. "script_verdict", "empty_output", "exit_code"
    reason: str       # Human-readable explanation


@dataclass
class AuditResult:
    """Complete result for a single rule assessment."""
    rule_id: str
    rule_title: str
    rule_section: str
    assessment_type: str
    profiles: List[str]

    # Outcome
    status: str                  # PASS | FAIL | MANUAL | ERROR | SKIP
    evaluation_strategy: str     # How pass/fail was determined
    evaluation_reason: str       # Human explanation

    # Evidence
    raw_stdout: str = ""
    raw_stderr: str = ""
    exit_code: int = -1
    timed_out: bool = False
    execution_error: Optional[str] = None
    evidence_path: str = ""

    # Timing
    duration_ms: int = 0
    timestamp: str = ""          # ISO-8601


@dataclass
class SystemInfo:
    """Information about the target host being assessed."""
    hostname: str
    ip_addresses: List[str]
    os_name: str
    os_version: str
    os_id: str                   # e.g. "ol" for Oracle Linux
    kernel_version: str
    architecture: str
    selinux_status: str
    run_as_user: str
    uptime: str


@dataclass
class AssessmentSummary:
    """Computed summary statistics for a completed assessment."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    manual: int = 0
    errors: int = 0
    skipped: int = 0
    score_percent: float = 0.0

    def compute(self, results: list):
        from config import STATUS_PASS, STATUS_FAIL, STATUS_MANUAL, STATUS_ERROR, STATUS_SKIP
        self.total = len(results)
        self.passed  = sum(1 for r in results if r.status == STATUS_PASS)
        self.failed  = sum(1 for r in results if r.status == STATUS_FAIL)
        self.manual  = sum(1 for r in results if r.status == STATUS_MANUAL)
        self.errors  = sum(1 for r in results if r.status == STATUS_ERROR)
        self.skipped = sum(1 for r in results if r.status == STATUS_SKIP)
        scoreable = self.passed + self.failed
        self.score_percent = round((self.passed / scoreable * 100), 1) if scoreable > 0 else 0.0


@dataclass
class AssessmentReport:
    """The complete assessment report — host info + all results + summary."""
    # Benchmark metadata
    benchmark_name: str
    benchmark_version: str
    profile: str
    assessment_date: str         # ISO-8601 start time
    assessment_end: str          # ISO-8601 end time
    assessment_duration_s: float
    assessor_version: str

    # Host
    system: SystemInfo

    # Results
    results: List[AuditResult] = field(default_factory=list)
    summary: AssessmentSummary = field(default_factory=AssessmentSummary)

    # Section breakdown (populated after results collected)
    section_stats: dict = field(default_factory=dict)

    def compute_summary(self):
        self.summary.compute(self.results)
        self._compute_section_stats()

    def _compute_section_stats(self):
        from config import STATUS_PASS, STATUS_FAIL
        stats = {}
        for r in self.results:
            sec = r.rule_section or r.rule_id.rsplit(".", 1)[0]
            if sec not in stats:
                stats[sec] = {"pass": 0, "fail": 0, "manual": 0, "error": 0}
            if r.status == STATUS_PASS:
                stats[sec]["pass"] += 1
            elif r.status == STATUS_FAIL:
                stats[sec]["fail"] += 1
            elif r.status == "MANUAL":
                stats[sec]["manual"] += 1
            else:
                stats[sec]["error"] += 1
        self.section_stats = stats
