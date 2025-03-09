"""
Fpgen is a fast & comprehensive browser fingerprint generator.
"""


def __check_module__() -> None:
    '''
    Detect if fpgen is being ran as a module.
    '''
    import inspect
    import os
    import sys

    # Detect if we're running as poetry script
    if sys.argv and os.path.basename(sys.argv[0]) == 'fpgen':
        os.environ['FPGEN_NO_INIT'] = '1'
        return

    stack: list = inspect.stack(2)
    if len(stack) >= 2:
        prev, launch = stack[-2:]
        try:
            if (launch.function, prev.function) == ('_run_module_as_main', '_get_module_details'):
                # Enable "partial execution mode" to prevent automatic downloads, starting network, etc.
                os.environ['FPGEN_NO_INIT'] = '1'
        except AttributeError:
            pass


__check_module__()
del __check_module__  # Remove from namespace

# ruff: noqa: E402

from .generator import Generator, WindowBounds, generate

# Expose the bayesian network interface for tests
from .utils import NETWORK as __network__
from .utils import query

__all__ = ['Generator', 'WindowBounds', 'generate', 'query', '__network__']
