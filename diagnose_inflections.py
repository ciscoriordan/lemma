#!/usr/bin/env python3
"""Quick diagnostic: check what inflections a headword has in the built dictionary."""
import re
import html
import sys
import glob
import os

words = sys.argv[1:] or ['τρώω', 'πηγαίνω', 'βλέπω', 'έχω', 'λέω', 'δίνω', 'παίρνω', 'άνθρωπος', 'παιδί']

# Find all content.html files from latest build
base = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(base, 'lemma_greek_el_*', 'content.html')))
# Exclude pct builds
files = [f for f in files if 'pct' not in f]

if not files:
    print("No build files found")
    sys.exit(1)

# Load all content
print(f"Loading {len(files)} content files...")
all_content = ""
for f in files:
    with open(f, 'r', encoding='utf-8') as fh:
        all_content += fh.read()

for word in words:
    escaped = re.escape(html.escape(word))
    # Find the entry
    pattern = rf'<idx:orth value="{escaped}">(.*?)</idx:entry>'
    m = re.search(pattern, all_content, re.DOTALL)
    if not m:
        print(f"\n{word}: NOT FOUND as headword")
        # Check if it appears as an iform anywhere
        iform_pat = rf'<idx:iform value="{escaped}"'
        iform_matches = re.findall(iform_pat, all_content)
        if iform_matches:
            # Find which headword it's under
            # Search backwards from each iform match
            for im in re.finditer(iform_pat, all_content):
                # Find the preceding idx:orth
                chunk = all_content[max(0, im.start()-5000):im.start()]
                orth = re.findall(r'<idx:orth value="([^"]*)"', chunk)
                if orth:
                    hw = html.unescape(orth[-1])
                    print(f"  Found as inflection of: {hw}")
                    break
        continue

    entry_html = m.group(1)
    iforms = re.findall(r'<idx:iform value="([^"]*)"', entry_html)
    iforms_decoded = [html.unescape(f) for f in iforms]
    print(f"\n{word}: {len(iforms_decoded)} inflections")
    for f in iforms_decoded[:30]:
        print(f"  {f}")
    if len(iforms_decoded) > 30:
        print(f"  ... and {len(iforms_decoded) - 30} more")
