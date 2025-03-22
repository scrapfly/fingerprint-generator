from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Union, overload

import orjson

from .bayesian_network import StrContainer
from .exceptions import RestrictiveConstraints
from .unpacker import lookup_value_list
from .utils import (
    NETWORK,
    _assert_dict_xor_kwargs,
    _find_roots,
    _tupilize,
    build_evidence,
)


@dataclass
class TraceResult:
    value: Any
    probability: float

    def __repr__(self) -> str:
        return f"<{self.value}: {self.probability * 100:.5f}%>"


# Recursive type for the return value
TraceResultDict = Dict[str, Union[List[TraceResult], "TraceResultDict"]]


@overload
def trace(
    target: str,
    conditions: Optional[Dict[str, Any]] = None,
    *,
    flatten: bool = False,
    **conditions_kwargs,
) -> List[TraceResult]: ...


@overload
def trace(
    target: StrContainer,
    conditions: Optional[Dict[str, Any]] = None,
    *,
    flatten: bool = False,
    **conditions_kwargs,
) -> TraceResultDict: ...


def trace(
    target: Union[str, StrContainer],
    conditions: Optional[Dict[str, Any]] = None,
    *,
    flatten: bool = False,
    __evidence__: Optional[Dict[str, Set[str]]] = None,
    **conditions_kwargs,
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
    _assert_dict_xor_kwargs(conditions, conditions_kwargs)

    # If evidence was already passed, consume it
    evidence: Dict[str, Set[str]] = __evidence__ or {}

    # Build conditions
    if conditions_kwargs:
        conditions = conditions_kwargs
    if conditions:
        build_evidence(conditions, evidence)

    # Get the targets
    target_tup = _tupilize(target)
    target_roots = tuple(_find_roots(target_tup))

    # List is empty, raise an error
    if not target_tup:
        raise ValueError("Please pass at least one valid target.")

    # If there is only one target, return the result
    if len(target_roots) == 1:
        return _pull_target(target_roots[0], evidence)

    # If flatten is true, return a dictionary of targets
    if flatten:
        return {root: _pull_target(root, evidence) for root in target_roots}

    # Otherwise, return a expanded dictionary of targets
    output: Dict[str, Any] = {}
    for root in target_roots:
        parts = root.split(".")
        d = output
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        output[parts[-1]] = _pull_target(root, evidence)
    return output


def _pull_target(target: str, evidence: Dict[str, Set[str]]) -> List[TraceResult]:
    """
    Gets the probability distribution for a target variable given conditions.
    """
    possibilities = NETWORK.trace(target=target, evidence=evidence)
    if not possibilities:
        raise RestrictiveConstraints(
            f"Restraints are too restrictive. No possible values for {target}."
        )
    data = lookup_value_list(possibilities.keys())
    data = map(orjson.loads, data)
    probs = possibilities.values()
    resp = [
        TraceResult(value=value, probability=probability) for value, probability in zip(data, probs)
    ]
    resp.sort(key=lambda x: x.probability, reverse=True)
    return resp
