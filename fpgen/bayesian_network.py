import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple, Union

import orjson
import zstandard

from .structs import CaseInsensitiveDict

StrContainer = Union[List[str], Tuple[str, ...], Set[str]]

# Constants
MISSING_VALUE_STRING = 'null'


class BayesianNode:
    """
    A single node in a Bayesian network with methods to sample conditional probabilities
    """

    def __init__(self, node_definition: Dict[str, Any], index: int):
        # Node defintion info
        self.node_definition = node_definition
        self.name = node_definition['name']
        self.parent_names = node_definition.get('parentNames', [])
        self.possible_values = node_definition.get('possibleValues', [])
        # CPT data structure
        self.probabilities = node_definition.get('conditionalProbabilities', {})
        # Index in the sampling order
        self.index = index

    def get_probabilities_given_known_values(
        self, parent_values: Dict[str, Any]
    ) -> Dict[Any, float]:
        """
        Extracts the probabilities for this node's values, given known parent values
        """
        probabilities = self.probabilities
        for parent_name in self.parent_names:
            parent_value = parent_values.get(parent_name, MISSING_VALUE_STRING)
            probabilities = probabilities.get(parent_value, {})
        return probabilities

    def sample_random_value_from_possibilities(
        self, possible_values: List[str], probabilities: Dict[str, float]
    ) -> Any:
        """
        Randomly sample from the given possible_values using the dict of probabilities
        """
        anchor = random.random()
        cumulative_probability = 0.0
        for val in possible_values:
            cumulative_probability += probabilities[val]
            if cumulative_probability > anchor:
                return val
        return possible_values[-1]  # Fallback

    def sample(self, parent_values: Dict[str, Any]) -> Any:
        """
        Sample a value for this node, given parent_values
        """
        cpt = self.get_probabilities_given_known_values(parent_values)
        if not cpt:
            # If missing, uniform distribution
            if not self.possible_values:
                return MISSING_VALUE_STRING
            prob = 1.0 / len(self.possible_values)
            cpt = {v: prob for v in self.possible_values}
        return self.sample_random_value_from_possibilities(self.possible_values, cpt)

    def sample_according_to_restrictions(
        self,
        parent_values: Dict[str, Any],
        value_possibilities: Iterable[str],
        banned_values: List[str],
    ) -> Optional[str]:
        """
        Sample a value consistent with the given subset of possible values
        excluding any in banned_values
        """
        cpt = self.get_probabilities_given_known_values(parent_values)
        valid_values = [v for v in value_possibilities if v not in banned_values and v in cpt]
        if not valid_values:
            return None
        return self.sample_random_value_from_possibilities(valid_values, cpt)


class BayesianNetwork:
    """
    Bayesian network implementation from Apify's fingerprint-suite,
    then ported to Python in Browserforge, then adapted here
    """

    def __init__(self, network_file: Path) -> None:
        network_definition = extract_json(network_file)
        self.nodes_in_sampling_order = [
            BayesianNode(node_def, index)
            for index, node_def in enumerate(network_definition['nodes'])
        ]
        nodes_by_name = {node.name: node for node in self.nodes_in_sampling_order}
        self.nodes_by_name = CaseInsensitiveDict(nodes_by_name)
        # Keep a list of the original names
        self.node_names = tuple(nodes_by_name.keys())

    def generate_certain_nodes(
        self,
        value_possibilities: Mapping[str, StrContainer],
        target_nodes: Set[str],
    ) -> Optional[Dict[str, Any]]:
        # Recursively find all possible parents
        parents = self.get_shared_possibilities(value_possibilities)
        # Handle impossible constraints
        if parents is None:
            return None

        # Build paths to the target_nodes
        depth_set: Set[int] = set()
        for target in target_nodes:
            # Add the current node to the depth list
            node = self.nodes_by_name[target]
            depth_set.add(node.index)

            # Collect parents until we're at the root
            parent_names = node.parent_names
            while parent_names and self.nodes_in_sampling_order[0] != parent_names[0]:
                # Update depth list and find the first parent's parents
                self._merge_into_depth_set(depth_set, parent_names)
                parent_names = self.nodes_by_name[parent_names[0]].parent_names
            # Update depth list
            self._merge_into_depth_set(depth_set, parent_names)

        sampled_nodes = self._recurse_consistent_sample({}, parents, index_list=sorted(depth_set))
        if not sampled_nodes:
            return sampled_nodes
        # Filter by target nodes
        return {node: v for node, v in sampled_nodes.items() if node.casefold() in target_nodes}

    def generate_consistent_sample(
        self,
        value_possibilities: Mapping[str, StrContainer],
    ) -> Optional[Dict[str, Any]]:
        # Recursively find all possible parents
        parents = self.get_shared_possibilities(value_possibilities)
        # Handle impossible constraints
        if parents is None:
            return None
        # Sample
        return self._recurse_consistent_sample({}, parents)

    def _merge_into_depth_set(self, depth_set: Set[int], node_names: List[str]):
        """
        Merges a list of node names into a depth set (set of sampling order indices)
        """
        depth_set.update(self.nodes_by_name[name].index for name in node_names)

    def get_shared_possibilities(
        self,
        value_possibilities: Mapping[str, StrContainer],
        orig_parents: Optional[Tuple[str, ...]] = None,
        seen_nodes: Optional[Set[Tuple[str, int]]] = None,
    ) -> Optional[Mapping[str, StrContainer]]:
        """
        Helper to search for all possible parents' values of the given constraints
        This works by tracing nodes up the tree and adding each parents possible values
        to the constraints

        If multiple constraints are passed, their parents' possible values are intersected
        to find common possible values
        """
        # Return empty dict immediately
        if not value_possibilities:
            return value_possibilities

        if seen_nodes is None:
            seen_nodes = set()

        # propogate upward until we have a list of clear branches to reach the target
        all_parents = {node: set(values) for node, values in value_possibilities.items()}
        for node, values in value_possibilities.items():
            # Track nodes that we've found the parents for
            if (node, len(values)) in seen_nodes:
                continue
            seen_nodes.add((node, len(values)))
            self._intersect_parents(node, values, all_parents)

        if orig_parents is None:
            orig_parents = tuple(all_parents.keys())

        # No common values found for a parent, give up
        if any(len(parents) == 0 for parents in all_parents.values()):
            return None

        return all_parents

    def _intersect_parents(
        self, node: str, values: StrContainer, all_parents: Dict[str, Set[str]]
    ) -> None:
        parent_names = self.nodes_by_name[node].parent_names
        num_parents = len(parent_names)
        # No parents exist, no reason to be here
        if not num_parents:
            return

        # Build a set of each parent's possible values
        parent_values: List[Set[str]] = [set() for _ in range(num_parents)]
        for value in values:
            collect_parents(
                self.nodes_by_name[node].probabilities,
                value,
                parent_values=parent_values,
            )

        # Update all_parents with the intersection of this node's parents
        for n, parents in enumerate(parent_values):
            parent_name = parent_names[n]
            if parent_name not in all_parents:
                all_parents[parent_name] = parents
            else:
                all_parents[parent_name] = all_parents[parent_name].intersection(parents)

        # If the first parent isnt the root node, recurse until we're there
        if parent_names[0] != self.nodes_in_sampling_order[0]:
            self._intersect_parents(
                node=parent_names[0], values=parent_values[0], all_parents=all_parents
            )

    def _recurse_consistent_sample(
        self,
        sample_so_far: Dict[str, Any],
        value_possibilities: Mapping[str, Iterable[str]],
        depth: int = 0,
        index_list: Optional[List[int]] = None,
    ) -> Optional[Dict[str, Any]]:
        # Get the current node & check if we are at the max depth
        if index_list is not None:
            if depth == len(index_list):
                return sample_so_far
            node = self.nodes_in_sampling_order[index_list[depth]]
        else:
            if depth == len(self.nodes_in_sampling_order):
                return sample_so_far
            node = self.nodes_in_sampling_order[depth]

        # Backtracking sampler
        banned: List[str] = []
        while True:
            candidate_val = node.sample_according_to_restrictions(
                sample_so_far,
                value_possibilities.get(node.name, node.possible_values),
                banned,
            )
            if candidate_val is None:
                break
            sample_so_far[node.name] = candidate_val
            nxt = self._recurse_consistent_sample(
                sample_so_far, value_possibilities, depth + 1, index_list
            )
            if nxt is not None:
                return nxt
            banned.append(candidate_val)
            del sample_so_far[node.name]
        return None


def collect_parents(
    probabilities: Dict[str, Any],
    target: str,
    parent_values: List[Set[str]],
    so_far: Optional[List[str]] = None,
    depth: int = 0,
):
    """
    Collects all the possible parent values of a node
    """
    if so_far is None:
        so_far = []
    for parent, values in probabilities.items():
        if isinstance(values, dict):
            collect_parents(
                probabilities=values,
                target=target,
                parent_values=parent_values,
                so_far=so_far + [parent],
                depth=depth + 1,
            )
        elif parent == target:
            for n, parent in enumerate(so_far):
                parent_values[n].add(parent)


def extract_json(path: Path) -> dict:
    """
    Reads JSON from a file (or from a zst if needed).
    """
    # Check for uncompressed json
    if path.exists():
        with open(path, 'rb') as f:
            return orjson.loads(f.read())

    # Check for zst json
    elif (zst_path := path.with_suffix('.json.zst')).exists():
        with open(zst_path, 'rb') as f:
            decomp = zstandard.ZstdDecompressor()
            return orjson.loads(decomp.decompress(f.read()))

    raise FileNotFoundError(f'Missing required data file for: {path}')
