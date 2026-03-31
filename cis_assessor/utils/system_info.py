"""
CIS Assessor — System Information Collector
"""

import os
import re
import socket
import subprocess
from typing import List

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from models import SystemInfo


def _run(cmd: str, default: str = "unknown") -> str:
    """Run a shell command and return stripped stdout, or default on failure."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() or default
    except Exception:
        return default


def _get_ip_addresses() -> List[str]:
    """Return a list of non-loopback IP addresses."""
    ips = []
    try:
        out = _run("hostname -I", "")
        if out and out != "unknown":
            ips = [ip.strip() for ip in out.split() if ip.strip() and ip.strip() != "127.0.0.1"]
    except Exception:
        pass

    if not ips:
        try:
            out = _run("ip -4 addr show | grep -oP '(?<=inet )\\d+\\.\\d+\\.\\d+\\.\\d+' | grep -v '^127\\.'", "")
            if out and out != "unknown":
                ips = [l.strip() for l in out.splitlines() if l.strip()]
        except Exception:
            pass

    if not ips:
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip != "127.0.0.1":
                ips = [ip]
        except Exception:
            pass

    return ips or ["127.0.0.1"]


def _get_os_info() -> dict:
    """Parse /etc/os-release for OS details."""
    info = {"name": "unknown", "version": "unknown", "id": "unknown"}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                line = line.strip()
                if line.startswith("PRETTY_NAME="):
                    info["name"] = line.split("=", 1)[1].strip('"')
                elif line.startswith("VERSION_ID="):
                    info["version"] = line.split("=", 1)[1].strip('"')
                elif line.startswith("ID="):
                    info["id"] = line.split("=", 1)[1].strip('"')
    except FileNotFoundError:
        info["name"] = _run("uname -s", "unknown")
    return info


def _get_selinux_status() -> str:
    """Return current SELinux mode or 'not available'."""
    out = _run("getenforce 2>/dev/null", "")
    if out and out not in ("unknown", ""):
        return out
    out2 = _run("sestatus 2>/dev/null | head -1", "")
    if out2:
        return out2
    return "not available"


def collect_system_info() -> SystemInfo:
    """Collect all relevant host information for the report."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = _run("hostname", "unknown")

    os_info = _get_os_info()

    return SystemInfo(
        hostname=hostname,
        ip_addresses=_get_ip_addresses(),
        os_name=os_info["name"],
        os_version=os_info["version"],
        os_id=os_info["id"],
        kernel_version=_run("uname -r", "unknown"),
        architecture=_run("uname -m", "unknown"),
        selinux_status=_get_selinux_status(),
        run_as_user=_run("whoami", str(os.getuid())),
        uptime=_run("uptime -p 2>/dev/null || uptime", "unknown"),
    )


def check_root() -> bool:
    """Return True if running as root (uid 0)."""
    return os.getuid() == 0
