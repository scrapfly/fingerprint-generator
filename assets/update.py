"""
Refreshes example-output.json
"""

import json
from pathlib import Path

import fpgen

DIR = Path('.').absolute()


with open(DIR / 'assets' / 'example-output.json', 'w') as f:
    data = fpgen.generate()
    json.dump(data, f, indent=2)
    data = fpgen.generate()
    json.dump(data, f, indent=2)
