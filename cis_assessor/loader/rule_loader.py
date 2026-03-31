"""
CIS Assessor — Rule Loader
Loads rules from parsed_rules.json and filters by profile.
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Set

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import Rule
from config import (
    RULES_JSON, PROFILE_MAP, PROFILE_L1_SERVER, PROFILE_L2_SERVER,
    PROFILE_L1_WORKSTATION, PROFILE_L2_WORKSTATION,
    TYPE_AUTOMATED, TYPE_MANUAL
)


def _parse_rule_id(title: str) -> str:
    """Extract rule ID like '1.1.1.1' from the title string."""
    m = re.match(r'^(\d+(?:\.\d+)*)\s+', title)
    return m.group(1) if m else ""


def _parse_assessment_type(title: str) -> str:
    """Extract 'Automated' or 'Manual' from title."""
    if "(Automated)" in title:
        return TYPE_AUTOMATED
    if "(Manual)" in title:
        return TYPE_MANUAL
    return TYPE_AUTOMATED  # assume automated if unlabeled


def _clean_title(title: str) -> str:
    """Strip the rule ID and assessment type suffix from title."""
    t = re.sub(r'^\d+(?:\.\d+)*\s+', '', title)       # remove leading "1.1.1.1 "
    t = re.sub(r'\s*\((Automated|Manual)\)\s*$', '', t)  # remove "(Automated)"
    return t.strip()


def _normalize_profiles(profiles: List[str]) -> List[str]:
    """Normalize profile strings to match the PROFILE_* constants."""
    normalized = []
    for p in profiles:
        # Strip bullet characters and extra whitespace
        clean = re.sub(r'^[•\-\*\s]+', '', p).strip()
        # Map to canonical form
        if re.search(r'Level\s*1.*Server', clean, re.IGNORECASE):
            normalized.append(PROFILE_L1_SERVER)
        elif re.search(r'Level\s*2.*Server', clean, re.IGNORECASE):
            normalized.append(PROFILE_L2_SERVER)
        elif re.search(r'Level\s*1.*Workstation', clean, re.IGNORECASE):
            normalized.append(PROFILE_L1_WORKSTATION)
        elif re.search(r'Level\s*2.*Workstation', clean, re.IGNORECASE):
            normalized.append(PROFILE_L2_WORKSTATION)
    return list(dict.fromkeys(normalized))  # deduplicate while preserving order


def load_all_rules(json_path: Path = RULES_JSON) -> List[Rule]:
    """Load and parse all rules from parsed_rules.json."""
    if not json_path.exists():
        raise FileNotFoundError(f"Rules file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rules = []
    for entry in raw:
        title = entry.get("title", "")
        rule_id = _parse_rule_id(title)
        if not rule_id:
            continue  # skip malformed entries

        clean_title = _clean_title(title)
        profiles = _normalize_profiles(entry.get("profiles", []))
        assessment_type = _parse_assessment_type(title)
        audit_text = entry.get("audit", "")

        rule = Rule(
            id=rule_id,
            title=clean_title,
            assessment_type=assessment_type,
            profiles=profiles,
            description=entry.get("description", ""),
            rationale=entry.get("rationale", ""),
            audit=audit_text,
            remediation=entry.get("remediation", ""),
            default_value=entry.get("default_value", ""),
        )
        rules.append(rule)

    return rules


def filter_by_profile(rules: List[Rule], level: int, system_type: str) -> List[Rule]:
    """
    Return rules applicable to the given (level, system_type) profile.
    Level 2 includes all Level 1 rules.
    """
    key = (level, system_type.lower())
    if key not in PROFILE_MAP:
        raise ValueError(f"Unknown profile: Level {level} - {system_type}")

    required_profiles: Set[str] = set(PROFILE_MAP[key])

    filtered = []
    for rule in rules:
        # A rule applies if ANY of its profiles are in the required set
        if any(p in required_profiles for p in rule.profiles):
            filtered.append(rule)

    return filtered


def apply_rule_filters(
    rules: List[Rule],
    include_ids: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
) -> List[Rule]:
    """Apply --rules and --skip-rules filters."""
    if include_ids:
        inc = set(include_ids)
        rules = [r for r in rules if r.id in inc]
    if exclude_ids:
        exc = set(exclude_ids)
        rules = [r for r in rules if r.id not in exc]
    return rules


def load_profile_rules(
    level: int,
    system_type: str,
    include_ids: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
    json_path: Path = RULES_JSON,
) -> List[Rule]:
    """Convenience: load → filter by profile → apply ID filters."""
    all_rules = load_all_rules(json_path)
    rules = filter_by_profile(all_rules, level, system_type)
    rules = apply_rule_filters(rules, include_ids, exclude_ids)
    # Sort by ID for consistent ordering
    rules.sort(key=lambda r: [int(x) for x in r.id.split(".")])
    return rules
