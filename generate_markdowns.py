import json
import re

with open('parsed_rules.json', 'r') as f:
    rules = json.load(f)

files = {
    'level_1_server': open('level_1_server.md', 'w'),
    'level_2_server': open('level_2_server.md', 'w'),
    'level_1_workstation': open('level_1_workstation.md', 'w'),
    'level_2_workstation': open('level_2_workstation.md', 'w'),
}

for k, v in files.items():
    title = k.replace('_', ' ').title()
    v.write(f"# CIS Oracle Linux 9 Benchmark - {title}\n\n")

def format_rule(rule):
    title_line = rule.get('title', '')
    parts = title_line.split(' ', 1)
    number = parts[0] if len(parts) > 1 else ""
    title_text = parts[1] if len(parts) > 1 else title_line
    
    md = f"## {number} {title_text}\n\n"
    if rule.get('description'):
        md += f"### Description\n{rule['description']}\n\n"
    if rule.get('rationale'):
        md += f"### Rationale\n{rule['rationale']}\n\n"
    if rule.get('audit'):
        md += f"### Audit\n{rule['audit']}\n\n"
    if rule.get('remediation'):
        md += f"### Remediation\n{rule['remediation']}\n\n"
    if rule.get('default_value'):
        md += f"### Default Value\n{rule['default_value']}\n\n"
    md += "---\n\n"
    return md

for rule in rules:
    profs = "".join(rule.get('profiles', [])).lower()
    
    is_l1_server = 'level 1 - server' in profs
    is_l2_server = 'level 2 - server' in profs
    is_l1_workstation = 'level 1 - workstation' in profs
    is_l2_workstation = 'level 2 - workstation' in profs
    
    md_content = format_rule(rule)
    
    if is_l1_server:
        files['level_1_server'].write(md_content)
        files['level_2_server'].write(md_content)
    elif is_l2_server:
        files['level_2_server'].write(md_content)
        
    if is_l1_workstation:
        files['level_1_workstation'].write(md_content)
        files['level_2_workstation'].write(md_content)
    elif is_l2_workstation:
        files['level_2_workstation'].write(md_content)

for f in files.values():
    f.close()
