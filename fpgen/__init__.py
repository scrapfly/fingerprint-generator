"""
Fpgen is a fast & comprehensive browser fingerprint generator.
"""


def __check_module__() -> None:
    '''
    Detect if fpgen is being ran as a module.
    '''
    import inspect
    import os

    stack: list = inspect.stack(2)
    if len(stack) >= 2:
        prev, launch = stack[-2:]
        try:
            if (launch.function, prev.function) == ('_run_module_as_main', '_get_module_details'):
                os.environ['FPGEN_NO_AUTO_DOWNLOAD'] = '1'
        except AttributeError:
            pass


__check_module__()


from .generator import Generator, Screen

__all__ = ['Generator', 'Screen']
