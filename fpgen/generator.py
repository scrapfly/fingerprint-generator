from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union, overload

import orjson

from .bayesian_network import StrContainer
from .exceptions import InvalidWindowBounds, RestrictiveConstraints
from .trace import TraceResult, TraceResultDict, trace
from .utils import (
    NETWORK,
    _assert_dict_xor_kwargs,
    _assert_network_exists,
    _build_constraints,
    _find_roots,
    _lookup_possibilities,
    _make_output_dict,
    _maybe_flatten,
    _reassemble_targets,
    _tupilize,
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
            _build_constraints(constraints, self.filtered_values)

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
        filtered_values = self.filtered_values.copy()
        if constraints:
            _build_constraints(constraints, filtered_values)

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

    @overload
    def trace(
        self,
        target: str,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        exact: bool = False,
        flatten: bool = False,
        **constraints,
    ) -> List[TraceResult]: ...

    @overload
    def trace(
        self,
        target: StrContainer,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        exact: bool = False,
        flatten: bool = False,
        **constraints,
    ) -> TraceResultDict: ...

    def trace(
        self,
        target: Union[str, StrContainer],
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        exact: bool = False,
        flatten: bool = False,
        **constraints,
    ) -> Union[List[TraceResult], TraceResultDict]:
        """
        Compute the probability distribution(s) of a target variable given constraints.

        Parameters:
            target (str): The target variable name.
            constraints_dict (Dict[str, Any], optional): A dictionary mapping variable names to their observed value.
            exact (bool, optional): If True, perform full exact inference.
                    Otherwise, perform approximate beam search inference (much faster).
            flatten (bool, optional): If True, return a flattened dictionary.
            **constraints: Additional constraints to apply to the target variable.
        Returns:
            A dictionary mapping probabilities to the target's possible values.
        """
        if constraints_dict:
            constraints = constraints_dict

        # Inherit the constraints from the class instance
        filtered_values = self.filtered_values.copy()
        if constraints:
            # Add the new constraints to the filtered values
            _build_constraints(constraints, filtered_values)
        # Get the common possibilities
        if shared_possibilities := NETWORK.get_shared_possibilities(filtered_values):
            filtered_values = shared_possibilities

        return trace(
            target=target,
            exact=exact,
            flatten=flatten,
            __filtered_evidence=filtered_values,
        )

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
