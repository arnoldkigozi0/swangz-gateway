"""Check all shipped application, extension and harness scripts without shell interpolation."""
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
files=sorted(set(root.glob('gateway/static/*.js'))|set(root.glob('extension/*.js'))|set(root.glob('tests/browser/*.cjs')))
for path in files:
    subprocess.run(['node','--check',str(path)],check=True)
print(f'Checked {len(files)} JavaScript files')
