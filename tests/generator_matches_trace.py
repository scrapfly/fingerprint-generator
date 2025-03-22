import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import fpgen

# Controls whether to use `target` or not (uses a different algorithm)
USE_TARGET = False
# Number of trials to run
TRIALS = 500

TESTS = [
    ('browser', {'os': ('Linux', 'MacOS'), 'browser': ('Edge', 'Safari')}),
    ('browser', {'os': ('Linux')}),
    ('browser', {'navigator': {'productsub': '20100101'}}),
    ('navigator.language', {'browser': 'firefox'}),
    ('os', {'browser': 'Firefox'}),
]

LIMIT = 10

for target, constraints in TESTS:
    pretty_constraints = ', '.join(f'{k}={v}' for k, v in constraints.items())
    print(f'Expected P({target}|{pretty_constraints}):')
    print(fpgen.trace(target=target, **constraints)[:LIMIT])
    print(f'Expected P({target}):')
    print(fpgen.trace(target=target)[:LIMIT])

    # Collected data
    browser_data = {}

    for _ in range(TRIALS):
        print(f'Trial {_+1}/{TRIALS}', end='\r')
        if USE_TARGET:
            a = fpgen.generate(flatten=True, target=target, **constraints)
        else:
            a = fpgen.generate(flatten=True, **constraints)[target]
        browser_data[a] = browser_data.get(a, 0) + 1

    print(f"\nGenerator test using P({target}|{pretty_constraints}):")
    for browser, count in sorted(browser_data.items(), key=lambda x: x[1], reverse=True)[:LIMIT]:
        print(f"{browser}: {count/TRIALS*100:.2f}%")
    print('\n---------\n')
