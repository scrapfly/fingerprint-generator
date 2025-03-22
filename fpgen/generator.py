from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Union, overload

from .bayesian_network import StrContainer
from .exceptions import RestrictiveConstraints
from .trace import TraceResult, TraceResultDict, trace
from .utils import (
    NETWORK,
    _assert_dict_xor_kwargs,
    _assert_network_exists,
    _find_roots,
    _make_output_dict,
    _maybe_flatten,
    _reassemble_targets,
    _tupilize,
    build_evidence,
)


class Generator:
    """
    Generates realistic browser fingerprints
    """

    def __init__(
        self,
        conditions: Optional[Dict[str, Any]] = None,
        *,
        strict: bool = True,
        flatten: bool = False,
        **conditions_kwargs: Any,
    ):
        """
        Initializes the Generator with the given options.
        Values passed to the Generator object will be inherited when calling Generator.generate()

        Parameters:
            conditions (dict, optional): Conditions for the generated fingerprint.
            strict (bool, optional): Whether to raise an exception if the conditions are too strict.
            flatten (bool, optional): Whether to flatten the output dictionary
            target (Optional[Union[str, StrContainer]]): Only generate specific value(s)
            **conditions_kwargs: Conditions for the generated fingerprint (passed as kwargs)
        """
        _assert_dict_xor_kwargs(conditions, conditions_kwargs)
        # Set default options
        self.strict: bool = strict
        self.flatten: bool = flatten
        self.evidence: Dict[str, Set[str]] = {}

        if conditions_kwargs:
            conditions = conditions_kwargs
        if conditions:
            build_evidence(conditions, self.evidence)

    @overload
    def generate(
        self,
        conditions: Optional[Dict[str, Any]] = None,
        *,
        strict: Optional[bool] = None,
        flatten: Optional[bool] = None,
        target: str,
        **conditions_kwargs: Any,
    ) -> Any: ...

    @overload
    def generate(
        self,
        conditions: Optional[Dict[str, Any]] = None,
        *,
        strict: Optional[bool] = None,
        flatten: Optional[bool] = None,
        target: Optional[StrContainer] = None,
        **conditions_kwargs: Any,
    ) -> Dict[str, Any]: ...

    def generate(
        self,
        conditions: Optional[Dict[str, Any]] = None,
        *,
        strict: Optional[bool] = None,
        flatten: Optional[bool] = None,
        target: Optional[Union[str, StrContainer]] = None,
        **conditions_kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Generates a fingerprint.

        Parameters:
            conditions (dict, optional): Conditions for the generated fingerprints.
                These conditions will be inherited by generated fingerprints.
            strict (bool, optional): Whether to raise an exception if the conditions are too strict.
            flatten (bool, optional): Whether to flatten the output dictionary
            target (Optional[Union[str, StrContainer]]): Only generate specific value(s)
            **conditions_kwargs: Conditions for the generated fingerprints (passed as kwargs)

        Returns:
            A generated fingerprint.
        """
        _assert_dict_xor_kwargs(conditions, conditions_kwargs)
        _assert_network_exists()

        if conditions_kwargs:
            conditions = conditions_kwargs

        # Merge new options with old
        strict = _first(strict, self.strict)
        flatten = _first(flatten, self.flatten)

        # Inherit the evidence from the class instance
        evidence = self.evidence.copy()
        if conditions:
            build_evidence(conditions, evidence, strict=strict)

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
                fingerprint = NETWORK.generate_certain_nodes(evidence, target_roots)
            else:
                fingerprint = NETWORK.generate_consistent_sample(evidence)

            # Found the fingerprint
            if fingerprint is not None:
                break
            # Raise an error if the evidence are too strict
            if strict:
                raise RestrictiveConstraints(
                    'Cannot generate fingerprint. Constraints are too restrictive.'
                )
            # If no fingerprint was generated, relax the filtered values until we find one
            evidence.pop(next(iter(evidence.keys())))

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
        conditions: Optional[Dict[str, Any]] = None,
        *,
        flatten: bool = False,
        **conditions_kwargs: Any,
    ) -> List[TraceResult]: ...

    @overload
    def trace(
        self,
        target: StrContainer,
        conditions: Optional[Dict[str, Any]] = None,
        *,
        flatten: bool = False,
        **conditions_kwargs: Any,
    ) -> TraceResultDict: ...

    def trace(
        self,
        target: Union[str, StrContainer],
        conditions: Optional[Dict[str, Any]] = None,
        *,
        flatten: bool = False,
        **conditions_kwargs: Any,
    ) -> Union[List[TraceResult], TraceResultDict]:
        """
        Compute the probability distribution(s) of a target variable given conditions.

        Parameters:
            target (str): The target variable name.
            conditions (Dict[str, Any], optional): A dictionary mapping variable names
            flatten (bool, optional): If True, return a flattened dictionary.
            **conditions_kwargs: Additional conditions to apply

        Returns:
            A dictionary mapping probabilities to the target's possible values.
        """
        return trace(
            target=target,
            flatten=flatten,
            conditions=conditions,
            **conditions_kwargs,
            # Inherit the conditions from the class instance
            __evidence__=self.evidence.copy(),
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
    """
    Generates a fingerprint.

    Parameters:
        conditions (dict, optional): Conditions for the generated fingerprints.
            These conditions will be inherited by generated fingerprints.
        strict (bool, optional): Whether to raise an exception if the conditions are too strict.
        flatten (bool, optional): Whether to flatten the output dictionary
        target (Optional[Union[str, StrContainer]]): Only generate specific value(s)
        **conditions_kwargs: Conditions for the generated fingerprints (passed as kwargs)

    Returns:
        A generated fingerprint.
    """
    global GLOBAL_GENERATOR
    if GLOBAL_GENERATOR is None:
        GLOBAL_GENERATOR = Generator()
    return GLOBAL_GENERATOR.generate(*args, **kwargs)


__all__ = ('Generator', 'WindowBounds', 'generate')
