import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import fpgen

"""
Confirms that a caller-supplied `rng` makes generation reproducible
without touching the `random` module's global generator.
"""

CONDITIONS = {'os': 'Windows', 'browser': 'Firefox'}

# Same seed, same fingerprint (full sample and targeted sample).
assert fpgen.generate(rng=random.Random(42), **CONDITIONS) == fpgen.generate(
    rng=random.Random(42), **CONDITIONS
)
assert fpgen.generate(
    rng=random.Random(42), target=('screen', 'navigator.hardwareconcurrency'), **CONDITIONS
) == fpgen.generate(
    rng=random.Random(42), target=('screen', 'navigator.hardwareconcurrency'), **CONDITIONS
)

# Different seeds draw different fingerprints.
assert len({repr(fpgen.generate(rng=random.Random(seed), **CONDITIONS)) for seed in range(5)}) > 1

# The global generator is neither consumed nor reseeded.
random.seed(7)
expected = random.random()
random.seed(7)
fpgen.generate(rng=random.Random(42), **CONDITIONS)
assert random.random() == expected

# A Generator's rng is inherited by generate() and can be overridden per call.
gen = fpgen.Generator(rng=random.Random(42), **CONDITIONS)
assert gen.generate() == fpgen.generate(rng=random.Random(42), **CONDITIONS)
assert gen.generate(rng=random.Random(1)) == fpgen.generate(rng=random.Random(1), **CONDITIONS)

# Without rng, the global generator is used as before.
random.seed(3)
first = fpgen.generate(**CONDITIONS)
random.seed(3)
assert fpgen.generate(**CONDITIONS) == first

print('OK')
