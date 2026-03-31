"""
CIS Assessor — Audit Runner
Extracts and executes audit scripts/commands from rule audit text.
"""

import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import ExecutionResult

# Regex to extract a full bash script block starting with #!/usr/bin/env bash
_SCRIPT_SHEBANG_RE = re.compile(r'(#!/usr/bin/env bash.*)', re.DOTALL)

# Regex to extract audit commands: lines like "# findmnt -kn /tmp | grep -v nodev"
# These are benchmark-style "run this command" instructions
_CMD_LINE_RE = re.compile(r'^#\s+([a-zA-Z/][^\n]+)$', re.MULTILINE)


def extract_audit_script(audit_text: str) -> Optional[str]:
    """
    Extract the full bash script from audit text.
    Returns the script string, or None if no script found.
    """
    m = _SCRIPT_SHEBANG_RE.search(audit_text)
    if not m:
        return None
    script = m.group(1).strip()
    # Ensure the script is non-trivial (more than just the shebang)
    lines = [l for l in script.splitlines() if l.strip() and not l.strip().startswith('#')]
    if len(lines) < 2:
        return None
    return script


def extract_audit_commands(audit_text: str) -> List[str]:
    """
    Extract individual shell commands from audit instructions.
    Picks up lines like: # grep -Pi 'LEGACY' /etc/crypto-policies/config
    """
    commands = []
    for m in _CMD_LINE_RE.finditer(audit_text):
        cmd = m.group(1).strip()
        # Skip obvious non-commands
        if any(skip in cmd.lower() for skip in [
            'example output', 'example:', 'output should', 'note:', 'verify that',
            'run the following', 'check that', 'nothing should'
        ]):
            continue
        # Skip lines that look like filenames or paths without commands
        if cmd.startswith('/') and ' ' not in cmd:
            continue
        commands.append(cmd)
    return commands


def build_command_audit_script(rule_id: str, commands: List[str], audit_text: str) -> str:
    """
    For rules without a full bash script, wrap individual commands in a
    standardised script that produces PASS/FAIL output.
    """
    # Detect if we expect empty output (nothing should be returned)
    expects_empty = bool(re.search(
        r'nothing should be returned|should return nothing|no output',
        audit_text, re.IGNORECASE
    ))

    cmd_lines = "\n".join(f"  {cmd}" for cmd in commands)

    if expects_empty:
        # Build a script that checks each command returns nothing
        individual_checks = []
        for i, cmd in enumerate(commands):
            individual_checks.append(f"""\
  l_out{i}="$({cmd} 2>&1)"
  if [ -n "$l_out{i}" ]; then
    l_fail=1
    echo "  [FOUND] $l_out{i}"
  fi""")

        checks_str = "\n".join(individual_checks)
        return f"""#!/usr/bin/env bash
# Auto-generated audit script for CIS rule {rule_id}
{{
  l_fail=0
{checks_str}
  if [ "$l_fail" -eq 0 ]; then
    echo ""
    echo "- Audit Result:"
    echo "  ** PASS **"
    echo "  - All checks returned empty output (expected)"
  else
    echo ""
    echo "- Audit Result:"
    echo "  ** FAIL **"
    echo "  - Reason(s) for audit failure above"
  fi
}}
"""
    else:
        # For informational commands, just run and collect output
        individual_cmds = "\n".join(f'  echo "--- {cmd} ---"\n  {cmd} 2>&1\n  echo ""' for cmd in commands)
        return f"""#!/usr/bin/env bash
# Auto-generated audit script for CIS rule {rule_id}
{{
{individual_cmds}
}}
"""


def execute_script(script: str, timeout: int = 60) -> ExecutionResult:
    """
    Write script to a temp file and execute it with bash.
    Returns ExecutionResult with stdout, stderr, exit_code.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', prefix='cis_audit_',
            delete=False, encoding='utf-8'
        ) as tmp:
            tmp.write(script)
            tmp_path = tmp.name

        os.chmod(tmp_path, 0o700)

        proc = subprocess.run(
            ["/bin/bash", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return ExecutionResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            timed_out=False,
        )

    except subprocess.TimeoutExpired as e:
        return ExecutionResult(
            stdout=e.stdout or "",
            stderr=e.stderr or "",
            exit_code=-1,
            timed_out=True,
            execution_error=f"Timed out after {timeout}s",
        )
    except PermissionError as e:
        return ExecutionResult(
            stdout="",
            stderr=str(e),
            exit_code=-1,
            execution_error=f"Permission denied: {e}",
        )
    except Exception as e:
        return ExecutionResult(
            stdout="",
            stderr=str(e),
            exit_code=-1,
            execution_error=str(e),
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def run_audit(rule_id: str, audit_text: str, timeout: int = 60) -> Tuple[ExecutionResult, str]:
    """
    Main entry point for running an audit.
    Returns (ExecutionResult, audit_script_used).
    """
    # Try full embedded bash script first
    script = extract_audit_script(audit_text)
    if script:
        return execute_script(script, timeout), script

    # Fall back to extracting individual commands
    commands = extract_audit_commands(audit_text)
    if commands:
        generated_script = build_command_audit_script(rule_id, commands, audit_text)
        return execute_script(generated_script, timeout), generated_script

    # Nothing runnable found
    return ExecutionResult(
        stdout="",
        stderr="No executable audit commands could be extracted.",
        exit_code=-1,
        execution_error="No runnable audit commands found",
    ), ""
