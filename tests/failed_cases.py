"""
Test for exceptions that should be raised.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from fpgen import Generator, generate, trace
from fpgen.exceptions import InvalidConstraints, InvalidNode, RestrictiveConstraints

# Generator with incorrect values
try:
    generate(screen={'width': 1920, 'height': 5000})
except InvalidConstraints as e:
    print('[PASSED] VERIFIER:', e)
else:
    print('[FAILED]')

# Incorrect nested node
try:
    generate(screen={'width': 1920, 'heighta': 1080})
except InvalidConstraints as e:
    print('[PASSED] VERIFIER:', e)
else:
    print('[FAILED]')

try:
    generate(screena={'width': 1920, 'height': 1080})
except InvalidNode as e:
    print('[PASSED] VERIFIER:', e)
else:
    print('[FAILED]')


# Test generator constructor
try:
    Generator(screen={'width': 1920, 'height': lambda x: x > 5000})
except InvalidConstraints as e:
    print('[PASSED] VERIFIER:', e)
else:
    print('[FAILED]')

# Test that Chrome is 100% probability on ChromeOS
result = trace(target='browser', os='ChromeOS')
try:
    assert len(result) == 1 and result[0].value == 'Chrome' and result[0].probability == 1.0
except AssertionError:
    print('[FAILED] TRACE: Expected Chrome 100% probability on ChromeOS, got:', result)
else:
    print('[PASSED] TRACE: Chrome is 100% probability on ChromeOS')

# Test that Firefox/Safari are impossible on ChromeOS
try:
    result = trace(target='browser', os='ChromeOS', browser=('Firefox', 'Safari'))
except RestrictiveConstraints as e:
    print('[PASSED] TRACE: Firefox/Safari correctly impossible on ChromeOS')
else:
    print('[FAILED] TRACE: Expected exception for impossible Firefox/Safari on ChromeOS')

# Test Firefox/Safari probabilities without OS constraint
result = trace(target='browser', browser=('Firefox', 'Safari'))
try:
    assert len(result) == 2
    assert all(r.value in ('Firefox', 'Safari') for r in result)
    assert abs(sum(r.probability for r in result) - 1.0) < 0.0001
except AssertionError:
    print('[FAILED] TRACE: Expected valid Firefox/Safari probabilities, got:', result)
else:
    print('[PASSED] TRACE: Valid Firefox/Safari probabilities')

# Test Chrome is 100% on ChromeOS even with Firefox/Safari allowed
result = trace(target='browser', os='ChromeOS', browser=('Firefox', 'Safari', 'Chrome'))
try:
    assert len(result) == 1 and result[0].value == 'Chrome' and result[0].probability == 1.0
except AssertionError:
    print(
        '[FAILED] TRACE: Expected Chrome 100% on ChromeOS with Firefox/Safari allowed, got:', result
    )
else:
    print('[PASSED] TRACE: Chrome is 100% on ChromeOS with Firefox/Safari allowed')

try:
    trace(target='browser', os='ChromeOS', browser='Firefox')
except RestrictiveConstraints as e:
    print('[PASSED] TRACE: Firefox cannot exist on ChromeOS')
else:
    print('[FAILED] TRACE: Should have raised an exception.')


# Basic passing case
try:
    data = generate(os='ChromeOS')
except Exception as e:
    print('[FAILED] GENERATE: Basic target case failed:', e)
else:
    print('[PASSED] GENERATE: Passed basic case (control)')

try:
    data = generate(os='ChromeOS', target='browser')
except Exception as e:
    print('[FAILED] GENERATE: Basic target case failed:', e)
else:
    print('[PASSED] GENERATE: Passed basic case (control)')

# Test impossible constraint handling
try:
    data = generate(browser='firefox', os='ChromeOS')
except RestrictiveConstraints as e:
    print('[PASSED] GENERATE: Throws on impossible constraint', e)
else:
    print('[FAILED] GENERATE: Firefox should not exist on ChromeOS')

try:
    data = generate(browser='firefox', os='ChromeOS', target='browser')
except RestrictiveConstraints as e:
    print('[PASSED] GENERATE: Throws on impossible constraint', e)
else:
    print('[FAILED] GENERATE: Firefox should not exist on ChromeOS (target)')

try:
    data = generate(browser=('firefox', 'safari', 'chrome'), os='ChromeOS', target='browser')
    assert data == 'Chrome'
except AssertionError:
    print('[FAILED] GENERATE: Doesn\'t pick the correct constraint')
else:
    print('[PASSED] GENERATE: Picks the correct constraint')
