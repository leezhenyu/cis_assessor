#!/usr/bin/env bash
# =============================================================================
# CIS Oracle Linux 9 Assessor — Pure Bash Implementation
# Benchmark : CIS Oracle Linux 9 Benchmark v2.0.0
# Requires  : bash 4.2+, jq (for JSON parsing)
# Usage     : sudo bash cis_assessor.sh --level 1 --type server
# =============================================================================
set -euo pipefail

readonly TOOL_VERSION="2.0.0"
readonly BENCHMARK_NAME="CIS Oracle Linux 9 Benchmark"
readonly BENCHMARK_VERSION="v2.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly RULES_JSON="${SCRIPT_DIR}/data/parsed_rules.json"

# ── ANSI colours ──────────────────────────────────────────────────────────────
RED='\033[91m'; GREEN='\033[92m'; YELLOW='\033[93m'
CYAN='\033[96m'; GRAY='\033[90m'; BOLD='\033[1m'; RESET='\033[0m'

# ── Defaults ──────────────────────────────────────────────────────────────────
LEVEL=""
SYS_TYPE=""
OUTPUT_DIR="./output"
FORMATS="html,json,csv"
INCLUDE_IDS=""
EXCLUDE_IDS=""
SKIP_MANUAL=false
TIMEOUT=60
VERBOSE=false
DRY_RUN=false
NO_ROOT_WARN=false

# ── Counters ──────────────────────────────────────────────────────────────────
COUNT_TOTAL=0; COUNT_PASS=0; COUNT_FAIL=0
COUNT_MANUAL=0; COUNT_ERROR=0; COUNT_SKIP=0

# ── Runtime state ─────────────────────────────────────────────────────────────
ASSESSMENT_START=""
EVIDENCE_DIR=""
REPORT_DIR=""
declare -a RESULTS=()   # "rule_id|status|title|section|type|duration_ms|reason|ev_path"
declare -a RULE_ENTRIES=()

# =============================================================================
# UTILITY
# =============================================================================

usage() {
  cat <<EOF
CIS Oracle Linux 9 Assessor v${TOOL_VERSION}

Usage: sudo bash $(basename "$0") --level {1|2} --type {server|workstation} [OPTIONS]

Required:
  -l, --level {1|2}                 CIS benchmark level
  -t, --type  {server|workstation}  Target system type

Options:
  -o, --output-dir DIR    Output directory (default: ./output)
  -f, --format  FORMATS   Comma-separated: html,json,csv (default: all)
      --rules   IDs       Only assess these rule IDs (comma-separated)
      --skip-rules IDs    Skip these rule IDs (comma-separated)
      --skip-manual       Skip manual rules entirely
      --timeout SECS      Per-rule timeout in seconds (default: 60)
  -v, --verbose           Show each rule as it runs
      --dry-run           List rules without running them
      --no-root-warn      Suppress non-root warning
      --version           Show tool version and exit
  -h, --help              Show this help

Examples:
  sudo bash cis_assessor.sh -l 1 -t server
  sudo bash cis_assessor.sh -l 2 -t server --format json,csv -o /var/reports
  sudo bash cis_assessor.sh -l 1 -t server --rules "1.1.1.1,1.4.1" --verbose
  sudo bash cis_assessor.sh -l 2 -t server --dry-run
EOF
  exit 0
}

die()        { echo "ERROR: $*" >&2; exit 1; }
now_iso()    { date '+%Y-%m-%dT%H:%M:%S%z'; }
capitalize() { echo "$1" | awk '{print toupper(substr($0,1,1)) substr($0,2)}'; }
# Portable milliseconds timestamp
now_ms() { date +%s%3N 2>/dev/null | grep -E '^[0-9]+$' || date +%s | awk '{print $1*1000}'; }

check_deps() {
  command -v jq &>/dev/null || die "jq is required. Install with: dnf install -y jq"
}

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

parse_args() {
  [[ $# -eq 0 ]] && usage
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -l|--level)        LEVEL="$2";       shift 2 ;;
      -t|--type)         SYS_TYPE="$2";    shift 2 ;;
      -o|--output-dir)   OUTPUT_DIR="$2";  shift 2 ;;
      -f|--format)       FORMATS="$2";     shift 2 ;;
         --rules)        INCLUDE_IDS="$2"; shift 2 ;;
         --skip-rules)   EXCLUDE_IDS="$2"; shift 2 ;;
         --skip-manual)  SKIP_MANUAL=true; shift   ;;
         --timeout)      TIMEOUT="$2";     shift 2 ;;
      -v|--verbose)      VERBOSE=true;     shift   ;;
         --dry-run)      DRY_RUN=true;     shift   ;;
         --no-root-warn) NO_ROOT_WARN=true;shift   ;;
         --version)      echo "CIS Assessor v${TOOL_VERSION}"; exit 0 ;;
      -h|--help)         usage ;;
      *) die "Unknown option: $1" ;;
    esac
  done
  [[ -z "$LEVEL" ]]                                                        && die "--level is required (1 or 2)"
  [[ -z "$SYS_TYPE" ]]                                                     && die "--type is required (server or workstation)"
  [[ "$LEVEL" != "1" && "$LEVEL" != "2" ]]                                 && die "--level must be 1 or 2"
  [[ "$SYS_TYPE" != "server" && "$SYS_TYPE" != "workstation" ]]           && die "--type must be 'server' or 'workstation'"
  [[ -f "$RULES_JSON" ]]                                                   || die "Rules file not found: $RULES_JSON"
}

# =============================================================================
# PROFILE
# =============================================================================

profile_display() {
  local type_cap; type_cap="$(capitalize "$SYS_TYPE")"
  if [[ "$LEVEL" == "2" ]]; then
    echo "Level 2 - ${type_cap} (includes Level 1)"
  else
    echo "Level 1 - ${type_cap}"
  fi
}

# Load matching rule indices into global RULE_ENTRIES array
# Each element: "<json_idx>\t<rule_id>\t<Automated|Manual>"
load_rules() {
  local type_cap; type_cap="$(capitalize "$SYS_TYPE")"
  local level_pattern
  [[ "$LEVEL" == "2" ]] && level_pattern="Level [12] - ${type_cap}" \
                        || level_pattern="Level 1 - ${type_cap}"

  RULE_ENTRIES=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && RULE_ENTRIES+=("$line")
  done < <(
    jq -r --arg pat "$level_pattern" '
      to_entries[] |
      select(
        .value.profiles | map(test($pat; "i")) | any
      ) |
      [
        (.key | tostring),
        (.value.title | capture("^(?<id>[0-9]+(?:\\.[0-9]+)*)") | .id),
        (if (.value.title | test("\\(Manual\\)"; "i")) then "Manual" else "Automated" end)
      ] | @tsv
    ' "$RULES_JSON"
  )
}

# =============================================================================
# AUDIT EXECUTION
# =============================================================================

extract_and_run_audit() {
  local rule_idx="$1" timeout_secs="$2"
  local tmp_script; tmp_script="$(mktemp /tmp/cis_audit_XXXXXX.sh)"
  local audit_text; audit_text="$(jq -r ".[$rule_idx].audit // empty" "$RULES_JSON")"

  if [[ -z "$audit_text" ]]; then
    rm -f "$tmp_script"
    echo "__NO_AUDIT__"
    return
  fi

  # Case 1: embedded bash script
  if echo "$audit_text" | grep -q '#!/usr/bin/env bash'; then
    echo "$audit_text" | sed -n '/^#!\/usr\/bin\/env bash/,$p' > "$tmp_script"
  else
    # Case 2: detect if "empty output = pass" pattern
    local expects_empty=false
    echo "$audit_text" | grep -qiE 'nothing should be returned|should return nothing|no output' \
      && expects_empty=true

    # Extract candidate commands: lines that look like shell commands (not narrative)
    local -a cmds=()
    while IFS= read -r line; do
      # Skip lines that start with narrative words
      echo "$line" | grep -qiE '^\s*(run|verify|check|ensure|note|if|the|this|an|a |for|when|•)' && continue
      # Match lines that look like a command (start with a letter, /, $)
      if echo "$line" | grep -qE '^[[:space:]]*[a-zA-Z/\$][a-zA-Z0-9/_.\-]'; then
        local cmd; cmd="$(echo "$line" | sed 's/^[[:space:]]*//')"
        [[ -z "$cmd" || "${#cmd}" -lt 3 ]] && continue
        cmds+=("$cmd")
      fi
    done <<< "$audit_text"

    if [[ ${#cmds[@]} -eq 0 ]]; then
      rm -f "$tmp_script"
      echo "__NO_AUDIT__"
      return
    fi

    {
      echo "#!/usr/bin/env bash"
      echo "{"
      if $expects_empty; then
        echo "  _fail=0"
        for cmd in "${cmds[@]}"; do
          echo "  _out=\$( $cmd 2>&1 || true )"
          echo "  [[ -n \"\$_out\" ]] && { _fail=1; echo \"  [FOUND] \$_out\"; }"
        done
        echo "  if [[ \$_fail -eq 0 ]]; then"
        echo "    printf '\\n- Audit Result:\\n  ** PASS **\\n'"
        echo "  else"
        echo "    printf '\\n- Audit Result:\\n  ** FAIL **\\n'"
        echo "  fi"
      else
        for cmd in "${cmds[@]}"; do
          printf "  echo '--- %s ---'\n" "$cmd"
          echo "  $cmd 2>&1 || true"
          echo "  echo ''"
        done
      fi
      echo "}"
    } > "$tmp_script"
  fi

  chmod 700 "$tmp_script"
  local output exit_code=0
  if command -v timeout &>/dev/null; then
    output="$(timeout "$timeout_secs" bash "$tmp_script" 2>&1)" || exit_code=$?
  else
    output="$(bash "$tmp_script" 2>&1)" || exit_code=$?
  fi
  rm -f "$tmp_script"

  echo "__EXIT_CODE__${exit_code}__"
  echo "$output"
}

# =============================================================================
# PASS/FAIL EVALUATION
# =============================================================================

evaluate_result() {
  local audit_text="$1" output="$2" exit_code="$3"

  # 1. Embedded script verdict
  if echo "$output" | grep -q '\*\* PASS \*\*'; then
    echo "PASS|script_verdict|Audit script reported PASS"
    return
  fi
  if echo "$output" | grep -q '\*\* FAIL \*\*'; then
    local reason; reason="$(echo "$output" | grep -A2 'FAIL' | tail -1 | head -c 120 || true)"
    echo "FAIL|script_verdict|Audit script reported FAIL: ${reason:-see evidence}"
    return
  fi

  # 2. Empty output expected
  if echo "$audit_text" | grep -qiE 'nothing should be returned|should return nothing|no output'; then
    if [[ -z "$(echo "$output" | tr -d '[:space:]')" ]]; then
      echo "PASS|empty_output|Command produced no output as expected"
    else
      echo "FAIL|empty_output|Expected empty output but found: $(echo "$output" | head -1 | head -c 80)"
    fi
    return
  fi

  # 3. Package check
  if echo "$audit_text" | grep -qi 'not installed'; then
    if echo "$output" | grep -qi 'not installed'; then
      echo "PASS|package_check|Package correctly not installed"
      return
    elif [[ -n "$(echo "$output" | tr -d '[:space:]')" ]]; then
      echo "FAIL|package_check|Package appears installed: $(echo "$output" | head -1 | head -c 80)"
      return
    fi
  fi

  # 4. Exit code fallback
  if [[ "$exit_code" == "0" ]]; then
    echo "PASS|exit_code|Audit script exited with code 0"
  else
    echo "FAIL|exit_code|Audit script exited with code $exit_code"
  fi
}

# =============================================================================
# EVIDENCE STORE
# =============================================================================

save_evidence() {
  local rule_id="$1" rule_title="$2" assessment_type="$3"
  local profiles="$4" status="$5" strategy="$6" reason="$7"
  local output="$8" exit_code="$9" duration_ms="${10}"
  local audit_text="${11:-}"

  local icon
  case "$status" in
    PASS)   icon="✅" ;; FAIL)   icon="❌" ;;
    MANUAL) icon="📋" ;; ERROR)  icon="⚠️ " ;; SKIP) icon="⏭ " ;; *) icon="?" ;;
  esac

  local ev_file="${EVIDENCE_DIR}/${rule_id}.txt"
  {
    printf '%0.s=' {1..80}; echo
    echo "CIS Oracle Linux 9 Benchmark ${BENCHMARK_VERSION}"
    echo "Rule ID   : ${rule_id}"
    echo "Title     : ${rule_title}"
    echo "Type      : ${assessment_type}"
    echo "Profiles  : ${profiles}"
    echo "Date/Time : $(now_iso)"
    echo "Status    : ${icon} ${status}"
    echo "Duration  : ${duration_ms}ms"
    printf '%0.s=' {1..80}; echo
    echo ""
    echo "--- EVALUATION ---"
    echo "Strategy  : ${strategy}"
    echo "Reasoning : ${reason}"
    echo ""
    if [[ -n "$audit_text" ]]; then
      echo "--- AUDIT PROCEDURE ---"
      echo "$audit_text" | head -30
      echo "(... full audit in parsed_rules.json ...)"
      echo ""
    fi
    echo "--- STDOUT ---"
    [[ -n "$output" ]] && echo "$output" || echo "(no output)"
    echo ""
    echo "--- EXIT CODE ---"
    echo "$exit_code"
    echo ""
    printf '%0.s=' {1..80}; echo
  } > "$ev_file"

  echo "$ev_file"
}

# =============================================================================
# REPORT GENERATORS
# =============================================================================

generate_json() {
  local json_file="${REPORT_DIR}/report.json"
  local hostname ip os_name kernel run_user
  hostname="$(hostname -f 2>/dev/null || hostname)"
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  os_name="$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}" || echo "unknown")"
  kernel="$(uname -r)"
  run_user="$(whoami)"

  local score=0 scoreable=$(( COUNT_PASS + COUNT_FAIL ))
  [[ $scoreable -gt 0 ]] && score=$(echo "scale=1; $COUNT_PASS * 100 / $scoreable" | bc)

  {
    echo "{"
    echo "  \"metadata\": {"
    echo "    \"tool\": \"CIS Oracle Linux 9 Assessor (bash)\","
    echo "    \"tool_version\": \"${TOOL_VERSION}\","
    echo "    \"benchmark\": \"${BENCHMARK_NAME}\","
    echo "    \"benchmark_version\": \"${BENCHMARK_VERSION}\","
    echo "    \"profile\": \"$(profile_display)\","
    echo "    \"assessment_date\": \"${ASSESSMENT_START}\","
    echo "    \"assessment_end\": \"$(now_iso)\""
    echo "  },"
    echo "  \"host\": {"
    echo "    \"hostname\": \"${hostname}\","
    echo "    \"ip_addresses\": [\"${ip}\"],"
    echo "    \"os_name\": \"${os_name}\","
    echo "    \"kernel_version\": \"${kernel}\","
    echo "    \"run_as_user\": \"${run_user}\""
    echo "  },"
    echo "  \"summary\": {"
    echo "    \"total\": ${COUNT_TOTAL},"
    echo "    \"passed\": ${COUNT_PASS},"
    echo "    \"failed\": ${COUNT_FAIL},"
    echo "    \"manual\": ${COUNT_MANUAL},"
    echo "    \"errors\": ${COUNT_ERROR},"
    echo "    \"skipped\": ${COUNT_SKIP},"
    echo "    \"score_percent\": ${score}"
    echo "  },"
    echo "  \"results\": ["
    local first=true
    for entry in "${RESULTS[@]}"; do
      IFS='|' read -r rid status rtitle rsec rtype dur reason ev_path <<< "$entry"
      $first && first=false || echo "    ,"
      echo "    {"
      echo "      \"rule_id\": \"${rid}\","
      echo "      \"rule_title\": $(jq -Rn --arg s "$rtitle" '$s'),"
      echo "      \"rule_section\": \"${rsec}\","
      echo "      \"assessment_type\": \"${rtype}\","
      echo "      \"status\": \"${status}\","
      echo "      \"evaluation_reason\": $(jq -Rn --arg s "$reason" '$s'),"
      echo "      \"duration_ms\": ${dur},"
      echo "      \"evidence_path\": \"${ev_path}\""
      echo -n "    }"
    done
    echo ""
    echo "  ]"
    echo "}"
  } > "$json_file"
  echo "$json_file"
}

generate_csv() {
  local csv_file="${REPORT_DIR}/summary.csv"
  local hostname; hostname="$(hostname -f 2>/dev/null || hostname)"
  local profile; profile="$(profile_display)"
  {
    echo "rule_id,rule_section,rule_title,assessment_type,status,evaluation_reason,duration_ms,evidence_path,hostname,assessment_date,profile"
    for entry in "${RESULTS[@]}"; do
      IFS='|' read -r rid status rtitle rsec rtype dur reason ev_path <<< "$entry"
      rtitle="${rtitle//\"/\"\"}"; reason="${reason//\"/\"\"}"
      echo "\"${rid}\",\"${rsec}\",\"${rtitle}\",\"${rtype}\",\"${status}\",\"${reason}\",${dur},\"${ev_path}\",\"${hostname}\",\"${ASSESSMENT_START}\",\"${profile}\""
    done
  } > "$csv_file"
  echo "$csv_file"
}

generate_html() {
  local html_file="${REPORT_DIR}/report.html"
  local hostname ip os_name kernel run_user uptime_str selinux
  hostname="$(hostname -f 2>/dev/null || hostname)"
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  os_name="$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}" || echo "unknown")"
  kernel="$(uname -r)"
  run_user="$(whoami)"
  uptime_str="$(uptime -p 2>/dev/null || uptime)"
  selinux="$(getenforce 2>/dev/null || echo 'not available')"

  local score=0 scoreable=$(( COUNT_PASS + COUNT_FAIL ))
  [[ $scoreable -gt 0 ]] && score=$(echo "scale=1; $COUNT_PASS * 100 / $scoreable" | bc)
  local pct_int=${score%%.*}

  local profile_str; profile_str="$(profile_display)"

  local score_label="Non-Compliant"
  (( pct_int >= 60 )) && score_label="Partial"
  (( pct_int >= 85 )) && score_label="Compliant"

  # Build results rows
  local rows=""
  for entry in "${RESULTS[@]}"; do
    IFS='|' read -r rid status rtitle rsec rtype dur reason ev_path <<< "$entry"
    local badge_class icon
    case "$status" in
      PASS)   badge_class="bp"; icon="✅ PASS"    ;;
      FAIL)   badge_class="bf"; icon="❌ FAIL"    ;;
      MANUAL) badge_class="bm"; icon="📋 MANUAL"  ;;
      ERROR)  badge_class="be"; icon="⚠️ ERROR"   ;;
      SKIP)   badge_class="bs"; icon="⏭ SKIP"    ;;
      *)      badge_class="bs"; icon="$status"    ;;
    esac
    local type_badge="ba"; local type_label="Auto"
    [[ "$rtype" == "Manual" ]] && { type_badge="bm2"; type_label="Manual"; }

    local detail_id="d_${rid//./_}"
    local ev_content=""
    [[ -f "$ev_path" ]] && ev_content="$(head -60 "$ev_path" | sed 's/</\&lt;/g; s/>/\&gt;/g')"
    local reason_esc; reason_esc="$(echo "$reason" | sed 's/</\&lt;/g; s/>/\&gt;/g')"

    rows+="<tr class='rr' data-status='${status}' onclick='td(\"${detail_id}\")'>"
    rows+="<td class='ci'>${rid}</td><td>${rtitle}</td>"
    rows+="<td class='cs'>${rsec}</td>"
    rows+="<td><span class='b ${badge_class}'>${icon}</span></td>"
    rows+="<td><span class='b ${type_badge}'>${type_label}</span></td>"
    rows+="<td>${dur}ms</td></tr>"
    rows+="<tr class='rd' id='${detail_id}'><td colspan='6'><div class='dg'>"
    rows+="<div class='db'><h4>Evaluation</h4><p class='rs'><b>Status:</b> ${status}<br><b>Reason:</b> ${reason_esc}</p></div>"
    rows+="<div class='db'><h4>Evidence</h4><pre>${ev_content}</pre></div>"
    rows+="</div></td></tr>"
  done

  cat > "$html_file" << HTMLEOF
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CIS Assessment — ${hostname}</title>
<style>
:root{--bg:#0f1117;--sf:#1a1d27;--sf2:#232736;--bd:#2e3347;--tx:#e2e8f0;--mu:#8892a4;--ac:#4f8ef7;--ps:#22c55e;--fl:#ef4444;--mn:#f59e0b;--er:#a855f7;--sk:#64748b;--r:10px;--mo:'JetBrains Mono',monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.6}
.hdr{background:linear-gradient(135deg,#1a1d27,#0f1117);border-bottom:2px solid var(--ac);padding:20px 32px;position:sticky;top:0;z-index:100}
.hdr h1{font-size:19px;font-weight:700;margin-bottom:5px}.hdr h1 span{color:var(--ac)}
.hm{display:flex;gap:18px;flex-wrap:wrap;color:var(--mu);font-size:12px}.hm strong{color:var(--tx)}
.wrap{max-width:1400px;margin:0 auto;padding:24px 32px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.g4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);padding:18px}
.ct{font-size:11px;font-weight:600;letter-spacing:1.4px;text-transform:uppercase;color:var(--mu);margin-bottom:12px}
.sc{background:linear-gradient(135deg,var(--sf),#1e2235);border:1px solid var(--ac);border-radius:var(--r);padding:22px;display:flex;align-items:center;gap:22px;margin-bottom:16px}
.do{width:100px;height:100px;flex-shrink:0;border-radius:50%;background:conic-gradient(var(--ps) 0% ${score}%,var(--sf2) ${score}% 100%);display:flex;align-items:center;justify-content:center;position:relative}
.do::after{content:'';position:absolute;width:68px;height:68px;background:var(--sf);border-radius:50%}
.sn{position:relative;z-index:1;text-align:center;font-size:20px;font-weight:800;line-height:1.1}
.sn small{display:block;font-size:9px;color:var(--mu);font-weight:400}
.sl{font-size:26px;font-weight:800;color:var(--ps)}.sd{color:var(--mu);font-size:12px;margin-top:4px}
.stc{background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);padding:14px;text-align:center}
.stc .n{font-size:30px;font-weight:800;margin-bottom:3px}.stc .l{font-size:11px;color:var(--mu);text-transform:uppercase;letter-spacing:1px}
.sp .n{color:var(--ps)}.sf2 .n{color:var(--fl)}.sm .n{color:var(--mn)}.se .n{color:var(--er)}
.it{width:100%;border-collapse:collapse}
.it td{padding:6px 0;border-bottom:1px solid var(--bd);font-size:13px}
.it td:first-child{color:var(--mu);font-size:11px;text-transform:uppercase;letter-spacing:.7px;width:120px}
.it tr:last-child td{border-bottom:none}
.sh{font-size:15px;font-weight:700;margin:24px 0 12px;display:flex;align-items:center;gap:8px}
.sh::after{content:'';flex:1;height:1px;background:var(--bd)}
.fb{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}
.fb input{background:var(--sf2);border:1px solid var(--bd);color:var(--tx);border-radius:6px;padding:6px 11px;font-size:13px;outline:none;flex:1;min-width:160px}
.fb input:focus{border-color:var(--ac)}
.btn{background:var(--sf2);color:var(--mu);border:1px solid var(--bd);border-radius:6px;padding:4px 11px;cursor:pointer;font-size:12px;transition:.15s}
.btn:hover,.btn.a{background:var(--ac);color:#fff;border-color:var(--ac)}
table.rt{width:100%;border-collapse:collapse;font-size:13px}
table.rt th{text-align:left;padding:8px 11px;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--mu);font-weight:600;border-bottom:2px solid var(--bd)}
table.rt td{padding:8px 11px;border-bottom:1px solid var(--bd);vertical-align:top}
tr.rr:hover{background:var(--sf);cursor:pointer}
.ci{width:70px;font-family:var(--mo);font-weight:600;color:var(--ac);font-size:12px}
.cs{width:75px;font-family:var(--mo);font-size:12px;color:var(--mu)}
.b{display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700}
.bp{background:rgba(34,197,94,.15);color:var(--ps);border:1px solid rgba(34,197,94,.3)}
.bf{background:rgba(239,68,68,.15);color:var(--fl);border:1px solid rgba(239,68,68,.3)}
.bm{background:rgba(245,158,11,.15);color:var(--mn);border:1px solid rgba(245,158,11,.3)}
.be{background:rgba(168,85,247,.15);color:var(--er);border:1px solid rgba(168,85,247,.3)}
.bs{background:rgba(100,116,139,.15);color:var(--sk)}
.ba{background:rgba(79,142,247,.1);color:var(--ac)}
.bm2{background:rgba(245,158,11,.1);color:var(--mn)}
tr.rd{display:none;background:var(--sf2);border-bottom:1px solid var(--bd)}
tr.rd.open{display:table-row}
tr.rd td{padding:12px 16px}
.dg{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.db{background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:11px}
.db h4{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--mu);margin-bottom:6px}
.db pre{font-family:var(--mo);font-size:11px;color:var(--tx);white-space:pre-wrap;word-break:break-all;max-height:240px;overflow-y:auto}
.rs{font-size:12px}
.ftr{margin-top:40px;padding:18px 32px;border-top:1px solid var(--bd);color:var(--mu);font-size:12px;display:flex;justify-content:space-between}
</style>
</head>
<body>
<div class="hdr">
  <h1>🔒 <span>CIS</span> Oracle Linux 9 Benchmark — Assessment Report</h1>
  <div class="hm">
    <span><strong>Profile:</strong> ${profile_str}</span>
    <span><strong>Benchmark:</strong> ${BENCHMARK_NAME} ${BENCHMARK_VERSION}</span>
    <span><strong>Date:</strong> ${ASSESSMENT_START}</span>
    <span><strong>Host:</strong> ${hostname}</span>
    <span><strong>Engine:</strong> bash v${TOOL_VERSION}</span>
  </div>
</div>
<div class="wrap">
  <div class="sh">📊 Executive Summary</div>
  <div class="sc">
    <div class="do"><div class="sn">${score}<small>%</small></div></div>
    <div>
      <div class="sl">${score_label}</div>
      <div class="sd">${COUNT_PASS} passed of $((COUNT_PASS + COUNT_FAIL)) automated checks · ${COUNT_MANUAL} manual · ${COUNT_ERROR} errors excluded</div>
      <div class="sd" style="margin-top:5px">👤 ${run_user} &nbsp;|&nbsp; 🖥 ${os_name}</div>
    </div>
  </div>
  <div class="g4" style="margin-bottom:18px">
    <div class="stc sp"><div class="n">${COUNT_PASS}</div><div class="l">✅ Pass</div></div>
    <div class="stc sf2"><div class="n">${COUNT_FAIL}</div><div class="l">❌ Fail</div></div>
    <div class="stc sm"><div class="n">${COUNT_MANUAL}</div><div class="l">📋 Manual</div></div>
    <div class="stc se"><div class="n">${COUNT_ERROR}</div><div class="l">⚠️ Error</div></div>
  </div>
  <div class="g2" style="margin-bottom:24px">
    <div class="card">
      <div class="ct">🖥 Host Information</div>
      <table class="it">
        <tr><td>Hostname</td><td>${hostname}</td></tr>
        <tr><td>IP Address</td><td>${ip}</td></tr>
        <tr><td>OS</td><td>${os_name}</td></tr>
        <tr><td>Kernel</td><td>${kernel}</td></tr>
        <tr><td>SELinux</td><td>${selinux}</td></tr>
        <tr><td>Run As</td><td>${run_user}</td></tr>
        <tr><td>Uptime</td><td>${uptime_str}</td></tr>
        <tr><td>Profile</td><td>${profile_str}</td></tr>
        <tr><td>Assessed</td><td>${ASSESSMENT_START}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="ct">📂 Summary</div>
      <table class="it">
        <tr><td>Total Rules</td><td>${COUNT_TOTAL}</td></tr>
        <tr><td>✅ Passed</td><td style="color:var(--ps)">${COUNT_PASS}</td></tr>
        <tr><td>❌ Failed</td><td style="color:var(--fl)">${COUNT_FAIL}</td></tr>
        <tr><td>📋 Manual</td><td style="color:var(--mn)">${COUNT_MANUAL}</td></tr>
        <tr><td>⚠️ Errors</td><td style="color:var(--er)">${COUNT_ERROR}</td></tr>
        <tr><td>Score</td><td style="font-weight:700;font-size:15px">${score}%</td></tr>
        <tr><td>Benchmark</td><td>${BENCHMARK_NAME} ${BENCHMARK_VERSION}</td></tr>
        <tr><td>Engine</td><td>bash v${TOOL_VERSION}</td></tr>
      </table>
    </div>
  </div>
  <div class="sh">📋 Detailed Results</div>
  <div class="fb">
    <input type="text" id="srch" placeholder="🔍  Search rules..." oninput="ft()">
    <button class="btn a" onclick="fs('ALL',this)">All (${COUNT_TOTAL})</button>
    <button class="btn" onclick="fs('PASS',this)">Pass (${COUNT_PASS})</button>
    <button class="btn" onclick="fs('FAIL',this)">Fail (${COUNT_FAIL})</button>
    <button class="btn" onclick="fs('MANUAL',this)">Manual (${COUNT_MANUAL})</button>
    <button class="btn" onclick="fs('ERROR',this)">Error (${COUNT_ERROR})</button>
  </div>
  <table class="rt">
    <thead><tr>
      <th class="ci">Rule ID</th><th>Title</th><th class="cs">Section</th>
      <th>Status</th><th>Type</th><th>Duration</th>
    </tr></thead>
    <tbody>
${rows}
    </tbody>
  </table>
</div>
<div class="ftr">
  <div>Generated by <strong>CIS Oracle Linux 9 Assessor (bash) v${TOOL_VERSION}</strong></div>
  <div>⚠️ For informational purposes. Results require expert review.</div>
</div>
<script>
let as='ALL';
function td(id){document.getElementById(id)?.classList.toggle('open')}
function ft(){
  const q=document.getElementById('srch').value.toLowerCase();
  document.querySelectorAll('tr.rr').forEach(r=>{
    const m=(as==='ALL'||r.dataset.status===as)&&(!q||r.textContent.toLowerCase().includes(q));
    r.style.display=m?'':'none';
    const d=document.getElementById('d_'+r.querySelector('.ci').textContent.trim().replace(/\./g,'_'));
    if(d)d.style.display=m?'':'none';
  });
}
function fs(s,b){as=s;document.querySelectorAll('.btn').forEach(x=>x.classList.remove('a'));b.classList.add('a');ft();}
</script>
</body></html>
HTMLEOF

  echo "$html_file"
}

# =============================================================================
# ASSESSMENT LOOP
# =============================================================================

run_assessment() {
  local total=${#RULE_ENTRIES[@]}

  for entry in "${RULE_ENTRIES[@]}"; do
    IFS=$'\t' read -r rule_idx rule_id assessment_type <<< "$entry"

    # Include/Exclude filters
    if [[ -n "$INCLUDE_IDS" ]]; then
      echo "$INCLUDE_IDS" | tr ',' '\n' | grep -qxF "$rule_id" || continue
    fi
    if [[ -n "$EXCLUDE_IDS" ]]; then
      echo "$EXCLUDE_IDS" | tr ',' '\n' | grep -qxF "$rule_id" && continue
    fi

    (( COUNT_TOTAL++ )) || true
    local start_ms; start_ms="$(now_ms)"

    local rule_title section profiles_str audit_text
    rule_title="$(jq -r ".[$rule_idx].title // empty" "$RULES_JSON" | \
      sed 's/^[0-9.][0-9.]* *//; s/ *(Automated)//; s/ *(Manual)//')"
    section="$(echo "$rule_id" | sed 's/\.[^.]*$//')"
    profiles_str="$(jq -r ".[$rule_idx].profiles[]? // empty" "$RULES_JSON" | \
      tr '\n' ',' | sed 's/,$//')"
    audit_text="$(jq -r ".[$rule_idx].audit // empty" "$RULES_JSON")"

    # Dry-run
    if $DRY_RUN; then
      local ts="(Auto) "
      [[ "$assessment_type" == "Manual" ]] && ts="(Manual)"
      printf "  %-12s %s  %s\n" "$rule_id" "$ts" "$rule_title"
      continue
    fi

    # Progress
    local pct=$(( COUNT_TOTAL * 100 / total ))
    if $VERBOSE; then
      printf "  [%3d/%-3d] %-12s %s\n" "$COUNT_TOTAL" "$total" "$rule_id" "${rule_title:0:55}"
    else
      local bar; bar="$(printf '#%.0s' $(seq 1 $(( pct * 28 / 100 )) 2>/dev/null) 2>/dev/null || true)"
      printf "\r  [%-28s] %3d%%  \033[92m%dP\033[0m \033[91m%dF\033[0m \033[93m%dM\033[0m  %-10s " \
        "$bar" "$pct" "$COUNT_PASS" "$COUNT_FAIL" "$(( COUNT_MANUAL + COUNT_SKIP ))" "$rule_id"
    fi

    local status="" strategy="" reason="" output="" exit_code=0 ev_path=""

    if [[ "$assessment_type" == "Manual" ]]; then
      if $SKIP_MANUAL; then
        status="SKIP"; strategy="skipped"; reason="Skipped by --skip-manual"
        (( COUNT_SKIP++ )) || true
      else
        status="MANUAL"; strategy="manual"; reason="Manual review required — see benchmark"
        (( COUNT_MANUAL++ )) || true
      fi
    else
      local raw_output
      raw_output="$(extract_and_run_audit "$rule_idx" "$TIMEOUT")"

      if [[ "$raw_output" == "__NO_AUDIT__" ]]; then
        status="ERROR"; strategy="no_audit"; reason="No runnable audit commands found"
        exit_code=-1
        (( COUNT_ERROR++ )) || true
      else
        exit_code="$(echo "$raw_output" | awk '/^__EXIT_CODE__/{match($0, /[0-9]+/); print substr($0,RSTART,RLENGTH); exit}')"
        [[ -z "$exit_code" ]] && exit_code=0
        output="$(echo "$raw_output" | grep -v '__EXIT_CODE__')"

        local eval_result; eval_result="$(evaluate_result "$audit_text" "$output" "$exit_code")"
        IFS='|' read -r status strategy reason <<< "$eval_result"

        case "$status" in
          PASS)  (( COUNT_PASS++  )) || true ;;
          FAIL)  (( COUNT_FAIL++  )) || true ;;
          ERROR) (( COUNT_ERROR++ )) || true ;;
        esac
      fi
    fi

    local end_ms; end_ms="$(now_ms)"
    local duration_ms=$(( end_ms - start_ms ))

    ev_path="$(save_evidence \
      "$rule_id" "$rule_title" "$assessment_type" \
      "$profiles_str" "$status" "$strategy" "$reason" \
      "$output" "$exit_code" "$duration_ms" "$audit_text")"

    RESULTS+=("${rule_id}|${status}|${rule_title}|${section}|${assessment_type}|${duration_ms}|${reason}|${ev_path}")

    if $VERBOSE; then
      case "$status" in
        PASS)   echo "  -> PASS" ;;
        FAIL)   echo "  -> FAIL  => ${reason:0:80}" ;;
        MANUAL) echo "  -> MANUAL" ;;
        ERROR)  echo "  -> ERROR => ${reason:0:80}" ;;
        SKIP)   echo "  -> SKIP"  ;;
      esac
    fi
  done

  $DRY_RUN || echo  # newline after progress bar
}

# =============================================================================
# SUMMARY PRINT
# =============================================================================

print_summary() {
  local score=0 scoreable=$(( COUNT_PASS + COUNT_FAIL ))
  [[ $scoreable -gt 0 ]] && score=$(echo "scale=1; $COUNT_PASS * 100 / $scoreable" | bc)

  echo ""
  echo "=============================================================="
  echo "📊 Assessment Complete  [$(date '+%Y-%m-%d %H:%M:%S %Z')]"
  echo "=============================================================="
  echo "   Total rules : ${COUNT_TOTAL}"
  echo "   ✅ Pass    : ${COUNT_PASS}"
  echo "   ❌ Fail    : ${COUNT_FAIL}"
  echo "   📋 Manual  : ${COUNT_MANUAL}"
  echo "   ⚠️  Error   : ${COUNT_ERROR}"
  [[ $COUNT_SKIP -gt 0 ]] && echo "   ⏭  Skipped : ${COUNT_SKIP}"
  echo ""
  echo "   Score      : ${score}% (${COUNT_PASS}/${scoreable} automated)"
  echo ""

  if [[ $COUNT_FAIL -gt 0 ]]; then
    echo "❌ Failed Rules (${COUNT_FAIL}):"
    for entry in "${RESULTS[@]}"; do
      IFS='|' read -r rid status rtitle rsec rtype dur reason ev_path <<< "$entry"
      [[ "$status" != "FAIL" ]] && continue
      printf "   %-12s %s\n" "$rid" "${rtitle:0:55}"
      printf "               -> %s\n" "${reason:0:80}"
    done
    echo ""
  fi

  if [[ $COUNT_ERROR -gt 0 ]]; then
    echo "⚠️  Errors (${COUNT_ERROR}):"
    for entry in "${RESULTS[@]}"; do
      IFS='|' read -r rid status rtitle rsec rtype dur reason ev_path <<< "$entry"
      [[ "$status" != "ERROR" ]] && continue
      printf "   %-12s %s\n" "$rid" "${rtitle:0:55}"
      printf "               -> %s\n" "${reason:0:80}"
    done
    echo ""
  fi
}

# =============================================================================
# MAIN
# =============================================================================

main() {
  parse_args "$@"
  check_deps

  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║      CIS Oracle Linux 9 Benchmark Assessor (bash)            ║"
  echo "║      ${BENCHMARK_VERSION}  ·  Tool v${TOOL_VERSION}                              ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""

  if [[ $EUID -ne 0 ]] && ! $NO_ROOT_WARN; then
    echo "WARNING: Not running as root. Many CIS checks require root access."
    echo ""
  fi

  local profile_str; profile_str="$(profile_display)"
  echo "📋 Loading rules for: ${profile_str}"
  load_rules

  local total_rules=${#RULE_ENTRIES[@]}
  [[ $total_rules -eq 0 ]] && die "No rules loaded — check that jq is installed and rules JSON is valid"

  local auto_count=0 manual_count=0
  for e in "${RULE_ENTRIES[@]}"; do
    [[ "$e" =~ $'\t'Manual$ ]] && (( manual_count++ )) || (( auto_count++ ))
  done
  echo "   ${total_rules} rules loaded  (${auto_count} automated, ${manual_count} manual)"
  echo ""

  if $DRY_RUN; then
    echo "🔍 Dry-run — rules that WOULD be assessed:"
    echo ""
    run_assessment
    echo ""
    echo "Total: ${total_rules} rules"
    return 0
  fi

  # System info
  echo "🖥  Collecting system information..."
  local hostname ip os_name kernel run_user
  hostname="$(hostname -f 2>/dev/null || hostname)"
  ip="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'unknown')"
  os_name="$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}" || echo 'unknown')"
  kernel="$(uname -r)"
  run_user="$(whoami)"
  echo "   Hostname   : ${hostname}"
  echo "   IP Address : ${ip}"
  echo "   OS         : ${os_name}"
  echo "   Kernel     : ${kernel}"
  echo "   Run As     : ${run_user}"
  echo ""

  # Prepare dirs
  ASSESSMENT_START="$(now_iso)"
  local safe_ts="${ASSESSMENT_START//:/-}"; safe_ts="${safe_ts//T/_}"
  REPORT_DIR="${OUTPUT_DIR}/${hostname}_${safe_ts:0:19}"
  EVIDENCE_DIR="${REPORT_DIR}/evidence"
  mkdir -p "$EVIDENCE_DIR"
  echo "📂 Output directory: ${REPORT_DIR}"
  echo ""

  echo "=============================================================="
  echo "🚀 Starting Assessment  [$(date '+%Y-%m-%d %H:%M:%S %Z')]"
  echo "=============================================================="
  echo ""

  run_assessment
  print_summary

  # Generate reports
  echo "📄 Generating reports (${FORMATS})..."
  IFS=',' read -ra fmts <<< "$FORMATS"
  for fmt in "${fmts[@]}"; do
    fmt="$(echo "$fmt" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
    local path=""
    case "$fmt" in
      json) path="$(generate_json)" ;;
      csv)  path="$(generate_csv)"  ;;
      html) path="$(generate_html)" ;;
      *)    echo "   Unknown format: ${fmt}"; continue ;;
    esac
    printf "   %-6s -> %s\n" "$(echo "$fmt" | awk '{print toupper($0)}')" "$path"
  done

  echo ""
  echo "✅ Assessment complete. Reports saved to:"
  echo "   ${REPORT_DIR}"
  echo ""

  [[ $COUNT_FAIL -gt 0 ]] && return 1 || return 0
}

main "$@"
