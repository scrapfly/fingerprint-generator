"""
Track where the generator hangs.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from pyinstrument import Profiler

from fpgen import generate

profiler = Profiler(interval=0.001)
profiler.start()

# Intensive constraint
generate(
    browser=('Firefox', 'Chrome'),
    client={'browser': {'major': ('134', '133')}},
)
profiler.stop()

print(profiler.output_text(show_all=True))
