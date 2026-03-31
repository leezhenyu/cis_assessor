"""
CIS Assessor — Configuration Constants
"""

import os
from pathlib import Path

# --- Tool Info ---
TOOL_NAME = "CIS Oracle Linux 9 Assessor"
TOOL_VERSION = "1.0.0"
BENCHMARK_NAME = "CIS Oracle Linux 9 Benchmark"
BENCHMARK_VERSION = "v2.0.0"

# --- Paths ---
PACKAGE_DIR = Path(__file__).parent.resolve()
DATA_DIR = PACKAGE_DIR / "data"
RULES_JSON = DATA_DIR / "parsed_rules.json"

# --- Profile Strings (as stored in parsed_rules.json) ---
PROFILE_L1_SERVER = "Level 1 - Server"
PROFILE_L2_SERVER = "Level 2 - Server"
PROFILE_L1_WORKSTATION = "Level 1 - Workstation"
PROFILE_L2_WORKSTATION = "Level 2 - Workstation"

# Map (level, type) -> list of applicable profile strings
PROFILE_MAP = {
    (1, "server"):      [PROFILE_L1_SERVER],
    (2, "server"):      [PROFILE_L1_SERVER, PROFILE_L2_SERVER],
    (1, "workstation"): [PROFILE_L1_WORKSTATION],
    (2, "workstation"): [PROFILE_L1_WORKSTATION, PROFILE_L2_WORKSTATION],
}

# --- Status Values ---
STATUS_PASS    = "PASS"
STATUS_FAIL    = "FAIL"
STATUS_MANUAL  = "MANUAL"
STATUS_ERROR   = "ERROR"
STATUS_SKIP    = "SKIP"

# --- Assessment Types ---
TYPE_AUTOMATED = "Automated"
TYPE_MANUAL    = "Manual"

# --- Defaults ---
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_OUTPUT_DIR      = "./output"
DEFAULT_FORMATS         = ["html", "json", "csv"]

# --- Evidence ---
EVIDENCE_DIR_NAME = "evidence"
EVIDENCE_MANIFEST  = "evidence_manifest.json"

# --- Report Filenames ---
REPORT_HTML = "report.html"
REPORT_JSON = "report.json"
REPORT_CSV  = "summary.csv"

# --- Scoring ---
# Manual and Error results are excluded from the score denominator
SCOREABLE_STATUSES = {STATUS_PASS, STATUS_FAIL}
