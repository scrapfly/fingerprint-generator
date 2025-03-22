"""
Tests various user inputs to confirm that they are handled correctly.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import re

from fpgen import Generator, __network__, query


def test(name, out, x=None):
    if x and not re.search(x, str(out)):
        print(
            ('> FAILED: ' + name).ljust(60, ' '),
            out,
        )
        return
    print(('PASSED! ' + name).ljust(60, ' '), str(out)[:100])


# Test options
FLATTEN_OPT = False
SORT_OPT = False

print(' ==== GENERATOR TESTS ==== ')

gen = Generator(flatten=FLATTEN_OPT)

test(
    'Generate full fp',
    gen.generate(),
    '^{.*',
)
test(
    'Generate full fp (non strict, fallback os)',
    gen.generate(
        os='ChromeOS',
        browser='Firefox',
        strict=False,
        target=('os', 'browser'),
    ),
    ".*'browser': 'Firefox'.*",
)
test(
    'Target (at node) given constraint',
    gen.generate(
        {'navigator': {'productsub': '20100101'}},
        target=('headers.user-agent'),
    ),
    'Firefox',
)
test(
    'Target (within node) given constraint',
    gen.generate(
        {'navigator': {'productsub': '20100101'}},
        target=['screen.width', 'screen.height'],
    ),
    r'\d+',
)
test(
    'Target (above node) given constraint',
    gen.generate(
        {'navigator': {'productsub': '20100101'}},
        target='navigator',
    ),
    '^{.*$',
)
test(
    'Passing multi constraints (no target)',
    gen.generate(
        browser=('Firefox', 'Chrome'),
        client={'browser': {'major': ('134', '133')}},
    ),
    r'\b13[34]\b',
)
test(
    'Passing multi constraints (target)',
    gen.generate(
        browser=('Firefox', 'Chrome'),
        client={'browser': {'major': ('134', '133')}},
        target='client',
    ),
    r'\b13[34]\b',
)
gpu = {
    'vendor': 'Google Inc. (Apple)',
    'renderer': 'ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)',
}
test(
    'Constraint tgt (at node, `window`)',
    gen.generate(gpu=gpu, target='window'),
)
test(
    'Constraint tgt (above nodes, `navigator`)',
    gen.generate(gpu=gpu, target='navigator'),
)
test(
    'Constraint tgt (within node, `screen.width`)',
    gen.generate(gpu=gpu, target='screen.width'),
)

print('\n ==== QUERY TESTS ==== ')

test(
    'Possibilities (at node 1, `navigator.productsub`)',
    query('navigator.productsub', flatten=FLATTEN_OPT, sort=SORT_OPT),
)
test(
    'Possibilities (at node 2, `screen`)',
    query('screen', flatten=FLATTEN_OPT, sort=SORT_OPT),
)
test(
    'Possibilities (above nodes, `navigator`)',
    query('navigator', flatten=FLATTEN_OPT, sort=SORT_OPT),
)
test(
    'Possibilities (within node, `screen.width`)',
    query('screen.width', flatten=FLATTEN_OPT, sort=SORT_OPT),
)


print(' ==== QUERY ALL NODES ==== ')

for node in __network__.nodes_by_name:
    # Get the possibilities
    print(f'Listing possibilities for {node}')
    a = query(node, flatten=FLATTEN_OPT, sort=SORT_OPT)
    print(str(a)[:100])
