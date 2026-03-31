<p align="center">
  <img src="https://img.shields.io/badge/CIS-Oracle%20Linux%209-red?style=for-the-badge&logo=oracle&logoColor=white" alt="CIS Oracle Linux 9">
  <img src="https://img.shields.io/badge/Benchmark-v2.0.0-blue?style=for-the-badge" alt="Benchmark v2.0.0">
  <img src="https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License MIT">
</p>

# 🔒 CIS Oracle Linux 9 Assessor

A lightweight, **zero-dependency** CLI tool that automatically assesses Oracle Linux 9 systems against the **CIS Oracle Linux 9 Benchmark v2.0.0** — inspired by [CIS-CAT Pro](https://www.cisecurity.org/cybersecurity-tools/cis-cat-pro).

> **Read-only & Safe** — The assessor only *reads* system configuration. It never modifies your system.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📋 **297 Rules** | Covers all CIS benchmark recommendations across 7 sections |
| 🏷 **4 Profiles** | Level 1 / Level 2 × Server / Workstation |
| 🤖 **275 Automated** | Auto-assessed via embedded CIS audit scripts |
| 📝 **22 Manual** | Flagged for human review, excluded from scoring |
| 📂 **Evidence Capture** | Per-rule raw output saved as audit-grade evidence files |
| 📊 **3 Report Formats** | Interactive HTML, machine-readable JSON, flat CSV |
| 🎯 **Flexible Targeting** | Assess all rules, specific rules, or skip rules by ID |
| 🖥 **Remote Execution** | Run on minimal servers without `pip` — render reports locally |
| ⏱ **Timeout Protection** | Per-rule timeout with graceful error handling |
| 🔐 **CI/CD Ready** | Returns exit code `1` on failures for pipeline integration |

---

## 📦 Project Structure

```
cis_assessor/
├── cis_assessor.py                  # CLI entry point
├── config.py                        # Constants & configuration
├── models.py                        # Data classes (Rule, AuditResult, Report)
├── requirements.txt                 # jinja2 (HTML reports only)
│
├── loader/
│   └── rule_loader.py               # Load & filter rules from JSON
│
├── engine/
│   ├── assessment_engine.py          # Orchestrator — iterate & assess rules
│   ├── audit_runner.py               # Extract & execute bash audit scripts
│   └── result_evaluator.py           # Multi-strategy PASS/FAIL evaluator
│
├── evidence/
│   └── evidence_store.py             # Save per-rule evidence to disk
│
├── report/
│   ├── report_generator.py           # HTML, JSON, CSV report generators
│   └── templates/
│       └── report_template.html      # Dark-themed interactive HTML template
│
├── utils/
│   ├── system_info.py                # Collect hostname, IP, OS, kernel
│   └── logger.py                     # Structured console + file logging
│
└── data/
    └── parsed_rules.json             # 297 CIS benchmark rules (extracted from PDF)
```

### Supporting Files (repo root)

| File | Purpose |
|------|---------|
| `benchmark/` | Original CIS benchmark PDF |
| `parser.py` | Extracts rules from PDF → `parsed_rules.json` |
| `generate_markdowns.py` | Generates per-profile Markdown reference files |
| `run_remote.py` | Automated remote assessment via SSH (paramiko) |
| `level_1_server.md` | CIS rules for Level 1 Server profile |
| `level_2_server.md` | CIS rules for Level 2 Server profile (includes L1) |
| `level_1_workstation.md` | CIS rules for Level 1 Workstation profile |
| `level_2_workstation.md` | CIS rules for Level 2 Workstation profile (includes L1) |

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/leezhenyu/cis_assessor.git
cd cis_assessor/cis_assessor

# Only dependency (for HTML reports)
pip install jinja2
```

### 2. Run Assessment

```bash
# Level 1 Server (recommended starting point)
sudo python3 cis_assessor.py --level 1 --type server

# Level 2 Server (includes all Level 1 rules + additional hardening)
sudo python3 cis_assessor.py --level 2 --type server

# Workstation profiles
sudo python3 cis_assessor.py --level 1 --type workstation
sudo python3 cis_assessor.py --level 2 --type workstation
```

### 3. View Reports

Reports are saved to `./output/<hostname>_<timestamp>/`:

```
output/
└── oracle-prod-01_2026-04-01_00-28-14/
    ├── report.html              # 🌐 Open in browser — interactive dark UI
    ├── report.json              # 🔧 Machine-readable for SIEM/GRC
    ├── summary.csv              # 📊 Flat table for spreadsheets
    ├── assessment.log           # 📝 Full execution log
    └── evidence/
        ├── 1.1.1.1.txt          # Per-rule evidence with full audit trail
        ├── 1.1.1.2.txt
        ├── ...
        └── evidence_manifest.json
```

---

## 🖥 CLI Output Example

```
╔══════════════════════════════════════════════════════════════╗
║         CIS Oracle Linux 9 Benchmark Assessor                ║
║         v2.0.0  ·  Tool v1.0.0                              ║
╚══════════════════════════════════════════════════════════════╝

📋 Loading rules for: Level 2 - Server (includes Level 1)
   297 rules loaded  (275 automated, 22 manual)

🖥  Collecting system information...
   Hostname   : guacamole
   IP Address : 192.168.1.30
   OS         : Oracle Linux Server 9.7
   Kernel     : 6.12.0-107.59.3.2.el9uek.x86_64
   Run As     : root

══════════════════════════════════════════════════════════════
📊 Assessment Complete
══════════════════════════════════════════════════════════════
   Total rules : 297
   ✅ Pass    : 174
   ❌ Fail    : 87
   📋 Manual  : 22
   ⚠️  Error   : 14

   Score      : 66.7% (174/261 automated)
   Duration   : 325.4s

❌ Failed Rules (87):
   1.1.2.1.1    Ensure /tmp is a separate partition
               → Audit script explicitly reported FAIL
   1.3.1.5      Ensure the SELinux mode is enforcing
               → Audit script explicitly reported FAIL
   ...

📄 Generating reports (html, json, csv)...
   HTML  → output/guacamole_2026-04-01/report.html
   JSON  → output/guacamole_2026-04-01/report.json
   CSV   → output/guacamole_2026-04-01/summary.csv

✅ Assessment complete. Reports saved to:
   output/guacamole_2026-04-01
```

---

## ⚙️ CLI Options

```
Usage: cis_assessor.py --level {1,2} --type {server,workstation} [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--level {1,2}` | CIS benchmark level **(required)** | — |
| `--type {server,workstation}` | Target system type **(required)** | — |
| `--output-dir DIR` | Output directory for reports | `./output` |
| `--format FORMATS` | Comma-separated: `html`, `json`, `csv` | `html,json,csv` |
| `--rules IDs` | Only assess these rule IDs (e.g. `1.1.1.1,1.4.1`) | all |
| `--skip-rules IDs` | Skip these rule IDs | none |
| `--skip-manual` | Skip manual rules entirely | include as MANUAL |
| `--timeout SECS` | Per-rule audit timeout | `60` |
| `--verbose` | Show each rule result as it runs | compact progress |
| `--dry-run` | List rules without executing | — |
| `--no-root-warn` | Suppress the non-root warning | — |
| `--version` | Show tool version | — |

### Examples

```bash
# HTML report only, custom output dir
sudo python3 cis_assessor.py -l 1 -t server --format html -o /var/reports/cis

# Assess specific rules only
sudo python3 cis_assessor.py -l 1 -t server --rules "1.1.1.1,1.1.1.2,1.4.1"

# Skip manual rules, verbose output
sudo python3 cis_assessor.py -l 1 -t server --skip-manual --verbose

# Preview which rules would be checked (no execution)
sudo python3 cis_assessor.py -l 2 -t server --dry-run

# JSON + CSV only (for servers without jinja2)
sudo python3 cis_assessor.py -l 1 -t server --format json,csv
```

---

## 🌐 Remote Execution

For minimal servers without `pip` or `jinja2`, you can run the assessment remotely and render reports locally:

### Manual Method

```bash
# 1. Copy assessor to remote server
scp -r cis_assessor/ user@192.168.1.30:~/cis_assessor/

# 2. Run on remote (JSON/CSV only — no jinja2 needed)
ssh user@192.168.1.30 "cd ~/cis_assessor && sudo python3 cis_assessor.py -l 2 -t server --format json,csv"

# 3. Download results
scp -r user@192.168.1.30:~/cis_assessor/output/ ./downloaded_report/

# 4. Render HTML locally (requires jinja2)
python3 gen_html.py
```

### Automated Method

A `run_remote.py` script is provided that automates the entire process using `paramiko`:

```bash
pip install paramiko scp
python3 run_remote.py
```

---

## 📊 Scoring

The compliance **score** is calculated as:

```
Score = Passed / (Passed + Failed) × 100%
```

| Status | Counted in Score? | Description |
|--------|:-:|-------------|
| ✅ **PASS** | ✔ | Rule is compliant |
| ❌ **FAIL** | ✔ | Rule is not compliant |
| 📋 **MANUAL** | ✘ | Requires human review |
| ⚠️ **ERROR** | ✘ | Audit script failed to execute |
| ⏭ **SKIP** | ✘ | Skipped by `--skip-manual` flag |

> This matches the scoring methodology used by **CIS-CAT Pro**.

---

## 🔍 How It Works

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Rule Loader │───▶│  Assessment │───▶│   Result    │───▶│   Report    │
│              │    │   Engine    │    │  Evaluator  │    │  Generator  │
│ parsed_rules │    │             │    │             │    │             │
│    .json     │    │ audit_runner│    │ PASS / FAIL │    │ HTML / JSON │
│              │    │ (subprocess)│    │ / MANUAL    │    │   / CSV     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                          │                                      │
                          ▼                                      ▼
                   ┌─────────────┐                        ┌─────────────┐
                   │  Evidence   │                        │   Output    │
                   │   Store     │                        │  Directory  │
                   │ (per-rule)  │                        │             │
                   └─────────────┘                        └─────────────┘
```

### Pass/Fail Evaluation Strategies (priority order)

1. **Script Verdict** — CIS scripts that output `** PASS **` or `** FAIL **` (most reliable)
2. **Empty Output** — Rules expecting no output on compliant systems
3. **Package Check** — Rules verifying package installation status
4. **Exit Code** — Fallback to script exit code (`0` = pass)

---

## 📋 CIS Benchmark Sections

| Section | Topic | Rules |
|:-------:|-------|:-----:|
| **1** | Initial Setup (filesystems, updates, SELinux, crypto) | 77 |
| **2** | Services (time sync, special purpose, service clients) | 39 |
| **3** | Network Configuration (kernel params, uncommon protocols) | 18 |
| **4** | Host-Based Firewall (firewalld / nftables / iptables) | 8 |
| **5** | Access Control (SSH, PAM, password, sudo, privileges) | 71 |
| **6** | Logging & Auditing (journald, auditd, log permissions) | 62 |
| **7** | System Maintenance (file permissions, user/group settings) | 22 |

---

## 📄 Evidence File Format

Each rule produces an evidence file (`evidence/<rule_id>.txt`) containing:

```
================================================================================
CIS Oracle Linux 9 Benchmark v2.0.0
Rule ID   : 1.1.1.1
Title     : Ensure cramfs kernel module is not available
Type      : Automated
Profiles  : Level 1 - Server, Level 1 - Workstation
Date/Time : 2026-04-01T00:28:15+08:00
Status    : ✅ PASS
Duration  : 245ms
================================================================================

--- DESCRIPTION ---
The cramfs filesystem type is a compressed read-only Linux filesystem...

--- EVALUATION ---
Strategy  : script_verdict
Reasoning : Audit script explicitly reported PASS

--- AUDIT PROCEDURE ---
(full audit script from the CIS benchmark)

--- STDOUT ---
- Audit Result:
  ** PASS **

--- EXIT CODE ---
0
================================================================================
```

---

## ⚠️ Requirements & Security

- **Python 3.9+** (uses `dataclasses`, `pathlib`, `subprocess`)
- **`jinja2`** (only needed for HTML reports — JSON/CSV work without it)
- **Root access** (`sudo`) — most CIS checks require privileged access to inspect system configurations
- The tool **never modifies** the system — all audits are read-only
- Evidence files may contain **sensitive system information** — protect your output directory accordingly

---

## 🗺 Roadmap

- [ ] Add `--remediate` flag to optionally fix failed rules
- [ ] Support CIS benchmarks for other distros (RHEL 9, Ubuntu 24.04)
- [ ] Web dashboard for multi-host trend tracking
- [ ] Delta reports (compare two assessment runs)
- [ ] Ansible/Terraform integration modules

---

## 📜 License

This tool is provided for internal security assessment purposes. The CIS Benchmark content is © Center for Internet Security, Inc. and is used in accordance with their [Terms of Use](https://www.cisecurity.org/terms-and-conditions-table-of-contents).
