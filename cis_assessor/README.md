# CIS Oracle Linux 9 Assessor

A CLI tool to automatically assess Oracle Linux 9 systems against the **CIS Oracle Linux 9 Benchmark v2.0.0**, inspired by CIS-CAT Pro.

## Features

- ✅ **297 rules** across 4 profiles (Level 1/2 × Server/Workstation)
- 🤖 **275 Automated** checks, 22 Manual checks
- 📂 **Evidence capture**: per-rule raw output saved to disk
- 📊 **Reports**: HTML (interactive dark UI), JSON, CSV
- ⚡ **Fast**: runs 235 L1-Server rules in ~3-5 minutes
- 🔒 **Read-only**: never modifies the system

## Requirements

- Python 3.9+
- `jinja2` (for HTML reports): `pip install jinja2`
- Must be run as **root** for accurate results (`sudo`)

## Usage

```bash
# Install dependency
pip install jinja2

# Level 1 Server assessment (recommended starting point)
sudo python3 cis_assessor.py --level 1 --type server

# Level 2 Server (includes all Level 1 rules)
sudo python3 cis_assessor.py --level 2 --type server

# Level 1 Workstation
sudo python3 cis_assessor.py --level 1 --type workstation

# HTML report only, custom output dir
sudo python3 cis_assessor.py --level 1 --type server --format html --output-dir /var/reports/cis

# Assess specific rules
sudo python3 cis_assessor.py --level 1 --type server --rules "1.1.1.1,1.1.1.2,1.4.1"

# Skip manual rules, verbose output
sudo python3 cis_assessor.py --level 1 --type server --skip-manual --verbose

# Dry-run: see what would be assessed without running
sudo python3 cis_assessor.py --level 2 --type server --dry-run
```

## Options

| Option | Description |
|--------|-------------|
| `--level {1,2}` | CIS benchmark level (required) |
| `--type {server,workstation}` | Target system type (required) |
| `--output-dir DIR` | Output directory (default: `./output`) |
| `--format {html,json,csv}` | Comma-separated report formats (default: all) |
| `--rules IDs` | Only assess these rule IDs (e.g. `1.1.1.1,1.4.1`) |
| `--skip-rules IDs` | Skip these rule IDs |
| `--skip-manual` | Skip manual rules (default: mark as MANUAL) |
| `--timeout SECS` | Per-rule timeout (default: 60s) |
| `--verbose` | Show each rule result as it runs |
| `--dry-run` | List rules without running them |

## Remote Execution without Dependencies

If you want to assess a remote minimalist server that doesn't have `pip` or `jinja2` installed, you can generate just the JSON/CSV data on the remote host, download it, and render the HTML report locally:

```bash
# On the remote server: run without HTML format
sudo python3 cis_assessor.py --level 2 --type server --format json,csv --output-dir ./remote_output

# On your local machine (where jinja2 is installed): 
# Download the report folder and run your custom local python script to render the HTML.
```
*(There is a `run_remote.py` script provided in the parent directory that automates this entire process using `paramiko`).*

## Output Structure

```
output/
└── <hostname>_<timestamp>/
    ├── report.html          # Interactive HTML report
    ├── report.json          # Machine-readable full report
    ├── summary.csv          # Flat CSV for spreadsheets/GRC
    ├── assessment.log       # Full assessment log
    └── evidence/
        ├── 1.1.1.1.txt      # Per-rule evidence file
        ├── 1.1.1.2.txt
        ├── ...
        └── evidence_manifest.json
```

## Scoring

The **score** is calculated as:
```
score = passed / (passed + failed) * 100
```

Manual and Error results are **excluded** from the score denominator (same as CIS-CAT Pro).

## Status Values

| Status | Meaning |
|--------|---------|
| ✅ PASS | Rule is compliant |
| ❌ FAIL | Rule is not compliant — see evidence for details |
| 📋 MANUAL | Manual review required — not automatable |
| ⚠️ ERROR | Audit script failed to run (permission, timeout, etc.) |
| ⏭ SKIP | Skipped by `--skip-manual` flag |

## Project Structure

```
cis_assessor/
├── cis_assessor.py              # CLI entry point
├── config.py                    # Constants and configuration
├── models.py                    # Data classes
├── loader/rule_loader.py        # Load and filter rules
├── engine/
│   ├── assessment_engine.py     # Orchestrator
│   ├── audit_runner.py          # Script executor
│   └── result_evaluator.py     # PASS/FAIL evaluator
├── evidence/evidence_store.py   # Save evidence files
├── report/
│   ├── report_generator.py      # HTML, JSON, CSV generation
│   └── templates/report_template.html
├── utils/
│   ├── system_info.py           # Host info collection
│   └── logger.py
└── data/parsed_rules.json       # 297 CIS benchmark rules
```
