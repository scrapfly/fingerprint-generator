from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union, overload

import orjson

from .bayesian_network import StrContainer
from .exceptions import (
    InvalidConstraints,
    InvalidWindowBounds,
    NodePathError,
    RestrictiveConstraints,
)
from .utils import (
    NETWORK,
    _assert_network_exists,
    _at_path,
    _find_roots,
    _flatten_constraints,
    _lookup_possibilities,
    _lookup_root_possibilities,
    _make_output_dict,
    _maybe_flatten,
    _reassemble_targets,
)


@dataclass
class WindowBounds:
    """
    Constrains the window size of the generated fingerprint.
    At least one parameter must be passed.

    Parameters:
        min_width (int, optional): Lower bound width
        max_width (int, optional): Upper bound width
        min_height (int, optional): Lower bound height
        max_height (int, optional): Upper bound height
    """

    min_width: Optional[int] = None
    max_width: Optional[int] = None
    min_height: Optional[int] = None
    max_height: Optional[int] = None

    def __post_init__(self):
        if (
            None not in (self.min_width, self.max_width)
            and self.min_width > self.max_width
            or None not in (self.min_height, self.max_height)
            and self.min_height > self.max_height
        ):
            raise ValueError(
                "Invalid window constraints: min values cannot be greater than max values"
            )

    def is_set(self) -> bool:
        """
        Returns true if any constraints were set
        """
        return any(value is not None for value in self.__dict__.values())


class Generator:
    """Generates realistic browser fingerprints"""

    def __init__(
        self,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        window_bounds: Optional[WindowBounds] = None,
        strict: bool = True,
        flatten: bool = False,
        **constraints: Any,
    ):
        """
        Initializes the Generator with the given options.

        Parameters:
            constraints_dict (dict, optional): Constraints for the network, passed as a dictionary.
            window (WindowBounds, optional): Constrain the output window size.
            strict (bool, optional): Whether to raise an exception if the constraints are too strict. Default is False.
            flatten (bool, optional): Whether to flatten output dictionaries.
            **constraints: Constraints for the network.
        """
        _assert_dict_xor_kwargs(constraints_dict, constraints)

        # Set default options
        self.window_bounds: Optional[WindowBounds] = window_bounds
        self.strict: bool = strict
        self.flatten: bool = flatten
        self.filtered_values: Dict[str, List[str]] = {}

        if constraints_dict:
            constraints = constraints_dict

        if constraints:
            self._build_constraints(constraints, self.filtered_values)

    @overload
    def generate(
        self,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        window_bounds: Optional[WindowBounds] = None,
        strict: Optional[bool] = None,
        flatten: Optional[bool] = None,
        target: str,
        **constraints: Any,
    ) -> Any: ...

    @overload
    def generate(
        self,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        window_bounds: Optional[WindowBounds] = None,
        strict: Optional[bool] = None,
        flatten: Optional[bool] = None,
        target: Optional[StrContainer] = None,
        **constraints: Any,
    ) -> Dict[str, Any]: ...

    def generate(
        self,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        window_bounds: Optional[WindowBounds] = None,
        strict: Optional[bool] = None,
        flatten: Optional[bool] = None,
        target: Optional[Union[str, StrContainer]] = None,
        **constraints: Any,
    ) -> Dict[str, Any]:
        """
        Generates a fingerprint.

        Parameters:
            constraints_dict (dict, optional): Constraints for the network, passed as a dictionary.
            window_bounds (WindowBounds, optional): Constrain the output window size.
            strict (bool, optional): Whether to raise an exception if the constraints are too strict.
            flatten (bool, optional): Whether to flatten the output dictionary
            target (Optional[Union[str, StrContainer]]): Only generate specific value(s)
            **constraints: Constraints for the network.
        """
        _assert_dict_xor_kwargs(constraints_dict, constraints)
        _assert_network_exists()

        if constraints_dict:
            constraints = constraints_dict

        # Inherit the constraints from the class instance
        filtered_values = self.filtered_values
        if constraints:
            self._build_constraints(constraints, filtered_values)

        # Merge new options with old
        window_bounds = _first(window_bounds, self.window_bounds)
        strict = _first(strict, self.strict)
        flatten = _first(flatten, self.flatten)

        # Handle window constraints
        if isinstance(window_bounds, WindowBounds):
            self._filter_by_window(
                strict=strict, window=window_bounds, filtered_values=filtered_values
            )

        # Convert targets to set
        if target:
            target_tup = _tupilize(target)
            target_roots = set(_find_roots(target_tup))
        else:
            target_roots = None

        # Generate fingerprint
        while True:
            # If we only are searching for certain targets, call generate_certain_nodes
            if target_roots:
                fingerprint = NETWORK.generate_certain_nodes(filtered_values, target_roots)
            else:
                fingerprint = NETWORK.generate_consistent_sample(filtered_values)

            # Found the fingerprint
            if fingerprint is not None:
                break
            # Raise an error if the filtered_values are too strict
            if strict:
                raise RestrictiveConstraints(
                    'Cannot generate fingerprint. Constraints are too restrictive.'
                )
            # If no fingerprint was generated, relax the filtered values until we find one
            filtered_values.pop(next(iter(filtered_values.keys())))

        # If we arent searching for certain targets, we can return right away
        if target:
            output = _make_output_dict(fingerprint, flatten=False)  # Don't flatten yet
            output = _reassemble_targets(_tupilize(target), output)
            if isinstance(target, str):
                output = output[target]
            return _maybe_flatten(flatten, output)

        return _make_output_dict(fingerprint, flatten=flatten)

    @staticmethod
    def _build_constraints(
        constraints: Dict[str, Any], filtered_values: Dict[str, List[str]]
    ) -> None:
        """
        Builds a map of filtered values based on given constraints
        """
        # flatten to match the format of the fingerprint network
        constraints = _flatten_constraints(constraints, casefold=True)

        for key, value in constraints.items():
            possible_values = _lookup_possibilities(key)

            # handle nested keys
            nested_keys: List[str] = []
            if possible_values is None:
                key, possible_values = _lookup_root_possibilities(key, nested_keys)

            filtered_values[key] = []

            for value_con in _tupilize(value):
                val = orjson.loads(value_con.casefold())

                # handle nested keys by filtering out possible values that dont
                # match the value at the target
                if nested_keys:
                    nested_keys = list(map(lambda s: s.casefold(), nested_keys))
                    for poss_value, lookup_index in possible_values.items():
                        # parse the dictionary
                        outputted_possible = orjson.loads(poss_value)

                        # check if the value is a possible value at the nested path
                        try:
                            target_value = _at_path(outputted_possible, nested_keys)
                        except NodePathError:
                            continue  # Path didn't exist, bad data
                        if target_value == val:
                            filtered_values[key].append(lookup_index)
                    # if nothing was found, raise an error
                    if not filtered_values[key]:
                        raise InvalidConstraints(
                            f'{value_con} is not a possible value for "{key}" '
                            f'at "{".".join(nested_keys)}"'
                        )
                    continue

                # non nested values can be handled by directly checking possible_values
                lookup_index = possible_values.get(value_con.casefold())
                # value is not possible
                if lookup_index is None:
                    raise InvalidConstraints(f'{value_con} is not a possible value for "{key}"')
                filtered_values[key].append(lookup_index)

    def _filter_by_window(
        self, strict: Optional[bool], window: WindowBounds, filtered_values: Dict
    ) -> None:
        """
        Filters the network based on the window constraints.
        """
        possible_windows = _lookup_possibilities('window')
        if possible_windows is None:
            raise Exception("No possible windows found. Bad network?")

        # Get a list of window node possibilities that are valid
        filtered_values['window'] = [
            lookup_value
            for window_string, lookup_value in possible_windows.items()
            if self._is_window_within_constraints(window_string, window)
        ]

        if not filtered_values['window']:
            if strict:
                raise InvalidWindowBounds("Window bound constraints are too restrictive.")
            del filtered_values['window']

    @staticmethod
    def _is_window_within_constraints(window_string: str, window: WindowBounds) -> bool:
        """
        Checks if the given window size are within the specified constraints.
        """
        window_data = orjson.loads(window_string)
        width, height = window_data['outerwidth'], window_data['outerheight']
        # Compare the sizes
        return (
            width >= (window.min_width or 0)
            and width <= (window.max_width or 1e5)
            and height >= (window.min_height or 0)
            and height <= (window.max_height or 1e5)
        )


def _first(*values):
    """
    Simple function that returns the first non-None value passed
    """
    return next((v for v in values if v is not None), None)


def _tupilize(value) -> Union[List[str], Tuple[str, ...]]:
    """
    If a value is not a tuple or list, wrap it in a tuple
    """
    return value if isinstance(value, (tuple, list)) else (value,)


def _assert_dict_xor_kwargs(
    passed_dict: Optional[Dict[str, Any]], passed_kwargs: Optional[Dict[str, Any]]
) -> None:
    """
    Confirms a dict is either passed as an argument, xor kwargs are passed.
    """
    if passed_dict:
        if passed_kwargs:
            raise ValueError(
                f"Cannot pass values as dict & as parameters: {passed_dict} and {passed_kwargs}"
            )
        if not isinstance(passed_dict, dict):
            raise ValueError(
                "Invalid argument. Constraints must be passed as kwargs or as a dictionary."
            )


"""
A global `generate` function for those calling
fpgen.generate() directly without creating a Generator object
"""

GLOBAL_GENERATOR: Optional[Generator] = None


def generate(*args, **kwargs) -> Dict[str, Any]:
    global GLOBAL_GENERATOR
    if GLOBAL_GENERATOR is None:
        GLOBAL_GENERATOR = Generator()
    return GLOBAL_GENERATOR.generate(*args, **kwargs)


__all__ = ('Generator', 'WindowBounds', 'generate')
