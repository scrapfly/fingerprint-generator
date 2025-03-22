"""
Test the speed of the generate, trace, and query functions.
"""

import sys
from pathlib import Path
from timeit import timeit

sys.path.append(str(Path(__file__).parent.parent))

from contextlib import contextmanager
from time import time

from fpgen import Generator, generate, query, trace


@contextmanager
def timer(description):
    print(description)
    start = time()
    yield
    print('Time to run', time() - start)


# Trace operations
with timer('trace (target=navigator.language)'):
    trace(target='navigator.language')

with timer("trace (target=browser, os=('Linux', 'MacOS'), browser=('Edge', 'Safari'))"):
    trace('browser', os=('Linux', 'MacOS'), browser=('Edge', 'Safari'))

# Generate operations
with timer('generating (full fingerprint)'):
    generate()

# with timer('generating (navigator.language=en-US)'):
#     generate({'navigator.language': 'en-US'})

with timer('generating (navigator.language=en-US, target=browser)'):
    generate({'navigator.language': ('en-US', 'en-GB', 'fr', 'de-DE')}, target='browser')

with timer('generating (browser=firefox, target=browser)'):
    generate(browser=('firefox'), target='browser')

with timer('generating (browser=firefox, target=navigator.language)'):
    generate(browser=('firefox'), target='navigator.language')

with timer('generating with a function constraint'):
    generate({'window': {'innerWidth': lambda x: x > 1000}}, target='navigator.language')

# Timeit tests

print('\n========== TIMEIT TESTS ==========\n')

print('Generator test')
print(timeit(lambda: generate(), number=100), '/ 100')

print('Generator test (with nested constraints)')
print(timeit(lambda: generate(screen={'width': 1920, 'height': 1080}), number=10), '/ 10')

gen = Generator(screen={'width': 1920, 'height': 1080})

print('Generator test with nested constraints (pre-filtered)')
print(timeit(lambda: gen.generate(), number=10), '/ 10')

print('Query test (large value set)')
print(timeit(lambda: query('allFonts'), number=10), '/ 10')

print('Trace test')
print(timeit(lambda: trace('browser'), number=100), '/ 100')

print('Trace test (large value set)')
print(timeit(lambda: trace('allFonts'), number=10), '/ 10')
