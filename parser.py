import re
import json

with open('extracted.txt', 'r') as f:
    lines = f.readlines()

rules = []
current_rule = {}
state = None

def clean_lines(text_lines):
    # remove page numbers like "Page 20"
    cleaned = []
    for l in text_lines:
        ls = l.strip()
        if re.match(r'^Page\s+\d+$', ls):
            continue
        # also ignore single space lines or empty lines
        if not ls:
            continue
        cleaned.append(ls)
    return " \n".join(cleaned)

i = 0
while i < len(lines):
    line = lines[i].strip()
    
    if line.startswith("Profile Applicability:"):
        # The title is the lines preceding this
        # Usually starts with Number
        title_lines = []
        j = i - 1
        while j >= 0:
            prev_line = lines[j].strip()
            if prev_line == '' or re.match(r'^Page\s+\d+$', prev_line):
                pass
            else:
                title_lines.insert(0, prev_line)
                if re.match(r'^\d+\.\d+(\.\d+)*\s', prev_line):
                    break
            j -= 1
        
        title = " ".join(title_lines)
        
        current_rule = {
            'title': title,
            'profiles': [],
            'description': [],
            'rationale': [],
            'audit': [],
            'remediation': [],
            'default_value': []
        }
        rules.append(current_rule)
        state = 'profiles'
        i += 1
        continue
        
    if state == 'profiles':
        if line.startswith("Description:"):
            state = 'description'
        elif line.startswith("• Level") or line.startswith("•  Level") or "Level" in line:
            # wait, profiles have a specific list
            current_rule['profiles'].append(line)
        i += 1
        continue
        
    if state == 'description':
        if line.startswith("Rationale:"):
            state = 'rationale'
        else:
            current_rule['description'].append(line)
        i += 1
        continue
        
    if state == 'rationale':
        if line.startswith("Audit:"):
            state = 'audit'
        else:
            current_rule['rationale'].append(line)
        i += 1
        continue

    if state == 'audit':
        if line.startswith("Remediation:"):
            state = 'remediation'
        else:
            current_rule['audit'].append(line)
        i += 1
        continue
        
    if state == 'remediation':
        if line.startswith("Default Value:"):
            state = 'default_value'
        elif line.startswith("References:") or line.startswith("CIS Controls:") or line.startswith("Profile Applicability:") or (i<len(lines)-1 and lines[i+1].strip().startswith("Profile Applicability:")):
            # end of remediation if we hit another section or next rule
            pass # we let it continue, but if we see next rule's signature it's handled
        # Wait, if we hit the next rule, `line.startswith("Profile Applicability:")` will be caught at the top
        # But wait, what if we see References?
        if line.startswith("References:") or line.startswith("CIS Controls:"):
            state = 'other'
        else:
            current_rule['remediation'].append(line)
        i += 1
        continue
        
    if state == 'default_value':
        if line.startswith("References:") or line.startswith("CIS Controls:"):
            state = 'other'
        else:
            current_rule['default_value'].append(line)
        i += 1
        continue
        
    if state == 'other':
        i += 1
        continue

    i += 1

# Process the parsed rules
for r in rules:
    r['description'] = clean_lines(r['description'])
    r['rationale'] = clean_lines(r['rationale'])
    r['audit'] = clean_lines(r['audit'])
    r['remediation'] = clean_lines(r['remediation'])
    r['default_value'] = clean_lines(r['default_value'])

# write to json
with open('parsed_rules.json', 'w') as f:
    json.dump(rules, f, indent=2)

print(f"Total parsed rules: {len(rules)}")
