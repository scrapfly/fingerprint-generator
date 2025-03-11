import logging
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Union,
    cast,
    overload,
)

import orjson

from .bayesian_network import BayesianNode, StrContainer
from .exceptions import CannotTraceLargeConfigSpace
from .unpacker import lookup_value_list
from .utils import (
    NETWORK,
    _assert_dict_xor_kwargs,
    _build_constraints,
    _find_roots,
    _tupilize,
)

# Maximum allowed joint configuration space size for exact inference
EXTREME_CASE_THRESHOLD = 1_000_000
# Beam width for approximate beam search inference
DEFAULT_BEAM_WIDTH = 1000


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
    constraints_dict: Optional[Dict[str, Any]] = None,
    *,
    exact: bool = False,
    flatten: bool = False,
    **constraints,
) -> List[TraceResult]: ...


@overload
def trace(
    target: StrContainer,
    constraints_dict: Optional[Dict[str, Any]] = None,
    *,
    exact: bool = False,
    flatten: bool = False,
    **constraints,
) -> TraceResultDict: ...


def trace(
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
    # Check if constraints are passed from another internal structure
    if '__filtered_evidence' in constraints:
        filtered_evidence = constraints.pop('__filtered_evidence')
    else:
        _assert_dict_xor_kwargs(constraints_dict, constraints)
        # Convert constraints into filters
        filtered_evidence: Mapping[str, StrContainer] = {}
        constraints = constraints_dict or constraints
        if constraints:
            # Build the constraints
            _build_constraints(constraints, cast(Dict[str, List[str]], filtered_evidence))
            # Get the shared possibilities
            if shared_possibilities := NETWORK.get_shared_possibilities(filtered_evidence):
                filtered_evidence = shared_possibilities

    target_tup = _tupilize(target)
    target_roots = tuple(_find_roots(target_tup))

    # If there's only one root, return the target directly
    if len(target_roots) == 1:
        return _pull_target(target_roots[0], filtered_evidence, exact)

    if flatten:
        # Just return the dict directly
        return {root: _pull_target(root, filtered_evidence, exact) for root in target_roots}

    output: Dict[str, Any] = {}
    for root in target_roots:
        # Split the root by dots to create nested structure
        parts = root.split(".")
        d = output
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = _pull_target(root, filtered_evidence, exact)
    return output


def _pull_target(
    target: str, filtered_evidence: Mapping[str, StrContainer], exact: bool
) -> List[TraceResult]:
    """
    Pull the target value from the fast_dag_inference output
    """
    possibilities = _fast_dag_inference(target, filtered_evidence, exact)
    data = lookup_value_list(possibilities.keys())
    data = map(orjson.loads, data)
    probs = possibilities.values()
    resp = [
        TraceResult(value=value, probability=probability) for value, probability in zip(data, probs)
    ]
    resp.sort(key=lambda x: x.probability, reverse=True)
    return resp


def _fast_dag_inference(
    target: str, whitelisted: Mapping[str, StrContainer], exact: bool = False
) -> Dict[str, float]:
    """
    Perform inference over a DAG Bayesian network.

    If exact is True, full exact inference is performed with the full joint distribution.
    Otherwise, an approximate beam search inference is used.

    Parameters:
        target (str): The target node name.
        whitelisted (Mapping[str, StrContainer]): Dictionary of allowed values for constrained nodes.
        exact (bool, optional): Whether to use the exact inference method.

    Returns:
        A dictionary mapping target values to probabilities.
    """
    if exact:
        # Use full exact inference
        return _exact_inference(target, whitelisted)
    else:
        # Use approximate beam search inference
        return _beam_search_inference(target, whitelisted, beam_width=DEFAULT_BEAM_WIDTH)


def _exact_inference(target: str, whitelisted: Mapping[str, StrContainer]) -> Dict[str, float]:
    """
    Perform exact inference by enumerating the full joint distribution
    over all nodes relevant to the target, and then marginalizing
    Parameters:
        target (str): The target node name.
        whitelisted (Mapping[str, StrContainer]): Dictionary of allowed values for constrained nodes.

    Returns:
        A dictionary mapping target values to (normalized) probabilities
    """
    # Get the set of nodes (the target and all its ancestors)
    relevant_nodes = _get_ancestors_and_target(target)
    # Order them according to the network’s topological order
    nodes_ordered = [
        node for node in NETWORK.nodes_in_sampling_order if node.name in relevant_nodes
    ]
    # Check if the configuration space size is too large
    config_space_size = 1
    for node in nodes_ordered:
        allowed = whitelisted.get(node.name, node.possible_values)
        config_space_size *= len(allowed)
    if config_space_size > EXTREME_CASE_THRESHOLD:
        raise CannotTraceLargeConfigSpace(
            "This node cannot be traced with exact inference because the CPT space is too large: "
            f"{config_space_size:,} exceeds threshold of {EXTREME_CASE_THRESHOLD:,}. "
            "Please use exact=False instead."
        )

    target_counts: Dict[str, float] = {}
    total_prob = 0.0

    # Enumerate every full assignment, and accumulate probabilities for the target variable
    for assignment, prob in _enumerate_joint_assignments(nodes_ordered, whitelisted):
        total_prob += prob
        target_val = assignment[target]
        target_counts[target_val] = target_counts.get(target_val, 0.0) + prob

    if total_prob > 0:
        return {val: p / total_prob for val, p in target_counts.items()}
    else:
        # If for some reason the total probability is zero, return uniform distribution
        allowed = whitelisted.get(target, NETWORK.nodes_by_name[target].possible_values)
        uniform = 1.0 / len(allowed)
        return {val: uniform for val in allowed}


def _enumerate_joint_assignments(
    nodes: List[BayesianNode],
    whitelisted: Mapping[str, StrContainer],
    index: int = 0,
    current_assignment: Optional[Dict[str, str]] = None,
    current_prob: float = 1.0,
) -> Iterable[Tuple[Dict[str, str], float]]:
    """
    Recursively enumerate all joint assignments (with their joint probabilities)
    for a list of nodes in topological order.

    Parameters:
        nodes (List[BayesianNode]): List of BayesianNodes
        whitelisted (Mapping[str, StrContainer]): Dictionary of allowed values for constrained nodes.
        index (int): The current index in the nodes list.
        current_assignment (Optional[Dict[str, str]]): Partial assignment built so far.
        current_prob (float): Joint probability of the partial assignment.

    Yields:
        Tuples of (assignment, joint_probability) for complete assignments.
    """
    if current_assignment is None:
        current_assignment = {}

    if index == len(nodes):
        yield current_assignment.copy(), current_prob
        return

    node = nodes[index]
    # Allowed values for this node (from evidence if provided)
    allowed = whitelisted.get(node.name, node.possible_values)
    # Get the CPT for this node given the current assignment.
    cpt = node.get_probabilities_given_known_values(current_assignment)
    if not cpt:
        # If no CPT exists for these parent values, assume a uniform distribution
        prob_uniform = 1.0 / len(allowed) if allowed else 0.0
        cpt = {val: prob_uniform for val in allowed}

    for value in allowed:
        p = cpt.get(value, 0.0)
        new_prob = current_prob * p
        if new_prob <= 0:
            continue
        current_assignment[node.name] = value
        yield from _enumerate_joint_assignments(
            nodes, whitelisted, index + 1, current_assignment, new_prob
        )
    # Remove the assignment for the current node before backtracking.
    if node.name in current_assignment:
        del current_assignment[node.name]


def _beam_search_inference(
    target: str, whitelisted: Mapping[str, StrContainer], beam_width: int = DEFAULT_BEAM_WIDTH
) -> Dict[str, float]:
    """
    Perform approximate inference using beam search to limit the number of
    joint configurations processed. The beam search proceeds in topological order
    over the target and its ancestors, keeping only the most probable partial assignments

    Parameters:
        target (str): The target node name.
        whitelisted (Mapping[str, StrContainer]): Dictionary of allowed values for constrained nodes.
        beam_width (int): Maximum number of partial assignments to keep at each step.

    Returns:
        A (normalized) approximate distribution over the target.
    """
    # Get all relevant nodes (target and ancestors) in topological order
    relevant_nodes = _get_ancestors_and_target(target)
    nodes_ordered = [
        node for node in NETWORK.nodes_in_sampling_order if node.name in relevant_nodes
    ]

    # Beam is a list of tuples (partial_assignment, probability)
    beam: List[Tuple[Dict[str, str], float]] = [({}, 1.0)]

    for node in nodes_ordered:
        new_beam: List[Tuple[Dict[str, str], float]] = []
        # Allowed values for this node come from evidence (if any) or the node's possibilities.
        allowed = whitelisted.get(node.name, node.possible_values)
        for assignment, prob in beam:
            cond_probs = node.get_probabilities_given_known_values(assignment)
            for value in allowed:
                if value not in cond_probs:
                    continue
                new_prob = prob * cond_probs[value]
                if new_prob <= 0:
                    continue
                new_assignment = assignment.copy()
                new_assignment[node.name] = value
                new_beam.append((new_assignment, new_prob))
        # Prune to the top beam_width partial assignments.
        new_beam.sort(key=lambda x: x[1], reverse=True)
        beam = new_beam[:beam_width]
        if not beam:
            logging.warning(f"Beam search failed at node {node.name}")
            return {}
    # Aggregate probabilities for the target variable from the complete assignments.
    target_counts: Dict[str, float] = {}
    for assignment, prob in beam:
        if target in assignment:
            val = assignment[target]
            target_counts[val] = target_counts.get(val, 0.0) + prob

    total = sum(target_counts.values())
    if total > 0:
        return {val: p / total for val, p in target_counts.items()}
    else:
        allowed = whitelisted.get(target, NETWORK.nodes_by_name[target].possible_values)
        uniform = 1.0 / len(allowed)
        return {val: uniform for val in allowed}


def _get_ancestors_and_target(target: str) -> Set[str]:
    """
    Get the target node and all its ancestor nodes (nodes that influence the target).

    Parameters:
        target (str): The target node name.

    Returns:
        A set of node names representing the target and its ancestors.
    """
    ancestors = {target}
    nodes_to_process = [target]

    while nodes_to_process:
        current = nodes_to_process.pop(0)
        node = NETWORK.nodes_by_name[current]
        for parent in node.parent_names:
            if parent not in ancestors:
                ancestors.add(parent)
                nodes_to_process.append(parent)

    return ancestors


__all__ = ("trace", "TraceResult")
