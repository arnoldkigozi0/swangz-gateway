"""Bound toolbar text contrast over black/white photographs using shipped tokens."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[3]
css = (root / 'gateway/static/tokens.css').read_text()
light = css.index(':root[data-theme="light"] {')

def color(value):
    if value.startswith('#'):
        return [int(value[i:i+2], 16) for i in (1, 3, 5)] + [1]
    return list(map(float, re.findall(r'[\d.]+', value)))

def over(a, b):
    return [a[i] * a[3] + b[i] * (1 - a[3]) for i in range(3)]

def luminance(rgb):
    return sum((v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4) * weight
               for v, weight in zip([c / 255 for c in rgb[:3]], [.2126, .7152, .0722]))

rows = []
for theme, part in [('dark', css[:light]), ('light', css[light:])]:
    def token(name):
        return color(re.search(re.escape(name) + r':\s*([^;]+);', part)[1].strip())
    for photo in ([0, 0, 0], [255, 255, 255]):
        scene = over(token('--scene-scrim'), photo)
        for label, foreground, background in [
            ('pill text', token('--tx-1'), over(token('--glass-bg-strong'), scene)),
            ('area context', token('--tx-2'), scene),
        ]:
            lo, hi = sorted([luminance(foreground), luminance(background)])
            ratio = (hi + .05) / (lo + .05)
            assert ratio >= 4.5, (theme, label, ratio)
            rows.append(dict(theme=theme, photo=photo[0], text=label, ratio=round(ratio, 2)))
Path(__file__).with_name('contrast-bounds.json').write_text(json.dumps(rows, indent=2) + '\n')
print('PASS', len(rows), 'text contrast bounds; minimum', min(row['ratio'] for row in rows))
