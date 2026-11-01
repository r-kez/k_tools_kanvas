"""Check that every relative link and #anchor in README.md and docs/*.md resolves."""

import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = [root / 'README.md', *sorted((root / 'docs').glob('*.md'))]


def slug(heading):
    heading = re.sub(r'[`*_]', '', heading.strip().lower())
    heading = re.sub(r'[^\w\s-]', '', heading)
    return re.sub(r'\s', '-', heading)


anchors = {}
for path in files:
    text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
    found = [slug(m.group(2)) for m in re.finditer(r'^(#{1,6})\s+(.+)$', text, re.M)]
    anchors[path.name] = set(found)

problems = []
for path in files:
    text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
    text = re.sub(r'`[^`\n]*`', '', text)
    for match in re.finditer(r'\[[^\]]*\]\(([^)\s]+)\)', text):
        target = match.group(1)
        if target.startswith(('http://', 'https://', 'mailto:')):
            continue
        name, _, fragment = target.partition('#')
        destination = (path.parent / name).resolve() if name else path
        if not destination.exists():
            problems.append(f'{path.name}: missing file {target}')
            continue
        if fragment and destination.suffix == '.md':
            if fragment not in anchors.get(destination.name, set()):
                problems.append(f'{path.name}: missing anchor {target}')
print(f'checked {len(files)} files')
for problem in problems:
    print('PROBLEM', problem)
sys.exit(1 if problems else 0)
