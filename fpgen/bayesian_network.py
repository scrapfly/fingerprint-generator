import heapq
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple, Union

from .exceptions import RestrictiveConstraints
from .pkgman import extract_json
from .structs import CaseInsensitiveDict
from .unpacker import lookup_value_list

StrContainer = Union[str, List[str], Tuple[str, ...], Set[str]]

# Width for beam search
# This cuts off values that are way too low or contaminated
BEAM_WIDTH = 1000


class BayesianNode:
    """
    A single node in a Bayesian network with methods to sample conditional probabilities
    """

    __slots__ = (
        'node_definition',
        'name',
        'parent_names',
        'possible_values',
        'probabilities',
        'index',
    )

    def __init__(self, node_definition: Dict[str, Any], index: int):
        # Node defintion info
        self.node_definition = node_definition
        self.name = node_definition['name']
        self.parent_names = node_definition['parentNames']
        self.possible_values = node_definition['possibleValues']
        # CPT data structure
        self.probabilities = node_definition['conditionalProbabilities']
        # Index in the sampling order
        self.index = index

    def get_probabilities_given_known_values(
        self, parent_values: Mapping[str, Any]
    ) -> Dict[Any, float]:
        """
        Extracts the probabilities for this node's values, given known parent values
        """
        probabilities = self.probabilities
        for parent_name in self.parent_names:
            parent_value = parent_values[parent_name]
            probabilities = probabilities.get(parent_value, {})
        return probabilities


class BayesianNetwork:
    """
    Bayesian network implementation for probabilistic sampling
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
        # Precompute ancestors
        self.ancestors_by_name: Dict[str, Set[str]] = {}
        for node in self.nodes_in_sampling_order:
            self.get_all_ancestors(node.name)

    def generate_consistent_sample(
        self, evidence: Mapping[str, Set[str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a full sample from the Bayesian network.
        """
        result: Dict[str, str] = {}
        # Create a working copy of evidence that we can update in place.
        current_evidence = {k: set(v) for k, v in evidence.items()}

        for node in self.nodes_in_sampling_order:
            node_name = node.name

            # For nodes with explicit evidence, remove the node itself from the evidence for beam search.
            if node_name in current_evidence:
                allowed_values = current_evidence[node_name]
                search_evidence = {k: v for k, v in current_evidence.items() if k != node_name}
                distribution = self.trace(node_name, search_evidence)

                # Filter the distribution to allowed values and renormalize.
                filtered_dist = {k: v for k, v in distribution.items() if k in allowed_values}
                if not filtered_dist or sum(filtered_dist.values()) <= 0:
                    uniform_prob = 1.0 / len(allowed_values)
                    filtered_dist = {val: uniform_prob for val in allowed_values}
                else:
                    total = sum(filtered_dist.values())
                    filtered_dist = {k: v / total for k, v in filtered_dist.items()}
                sampled_value = self.sample_value_from_distribution(filtered_dist)
            else:
                # For unconstrained nodes, use all current evidence.
                distribution = self.trace(node_name, current_evidence)
                sampled_value = self.sample_value_from_distribution(distribution)

            result[node_name] = sampled_value
            # Update current evidence with the newly sampled node value.
            current_evidence[node_name] = {sampled_value}

        return result

    def generate_certain_nodes(
        self,
        evidence: Mapping[str, Set[str]],
        targets: Optional[StrContainer] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate values for target nodes given conditions.
        """
        # If no target specified, generate full sample
        if targets is None:
            return self.generate_consistent_sample(evidence)

        # Generate result for each target
        result = {}

        for target_node in targets:
            # Calculate distribution for this target
            distribution = self.trace(target_node, evidence)

            # # Handle multi-value conditions for the target
            if target_node in evidence:
                allowed_values = evidence[target_node]

                # Filter and renormalize
                filtered_dist = {k: v for k, v in distribution.items() if k in allowed_values}

                # If no probability mass, use uniform distribution over allowed values
                if not filtered_dist or sum(filtered_dist.values()) <= 0:
                    raise RestrictiveConstraints(
                        f"Cannot generate fingerprint: No valid values for {target_node} with current conditions."
                    )

                # Renormalize
                total = sum(filtered_dist.values())
                filtered_dist = {k: v / total for k, v in filtered_dist.items()}

                distribution = filtered_dist

            # Sample from the distribution
            if distribution:
                result[target_node] = self.sample_value_from_distribution(distribution)
            else:
                raise RestrictiveConstraints(
                    f"Cannot generate fingerprint: Empty distribution for {target_node}."
                )

        return result

    def validate_evidence(self, evidence: Mapping[str, Set[str]]) -> None:
        """
        Validate that evidence is compatible with each other based on the
        Bayesian network structure. Raises an exception if they're incompatible.
        """
        # Skip validation for single constraint
        if len(evidence) <= 1:
            return

        # For each constrained node, check if it's compatible with other fixed conditions
        for node_name, allowed_values in evidence.items():
            # Get other fixed conditions (nodes with single values)
            fixed_constraints: Dict[str, Union[str, Set[str]]] = {}
            for k, v in evidence.items():
                if k != node_name and len(v) == 1:
                    fixed_constraints[k] = next(iter(v))

            # If we have fixed conditions, check compatibility
            if fixed_constraints:
                # Use beam search with fixed conditions to check compatibility
                dist = self.trace(node_name, fixed_constraints)

                # If beam search returns a distribution
                if dist and all(dist.get(val, 0) <= 0 for val in allowed_values):
                    # === BUILD THE EXCEPTION MESSAGE ===
                    # Show first 5 values failing node values.
                    values_str = ", ".join(lookup_value_list(tuple(allowed_values)[:5]))
                    if len(allowed_values) > 5:
                        values_str += ", ..."
                    # Get the constraints
                    constraints_values = lookup_value_list(fixed_constraints.values())
                    constraints_str = ", ".join(
                        f"{k}={v}" for k, v in zip(fixed_constraints.keys(), constraints_values)
                    )
                    raise RestrictiveConstraints(
                        f"Cannot generate fingerprint: {node_name}=({values_str}) "
                        f"is impossible with constraint: {constraints_str}"
                    )

    def get_all_ancestors(self, node_name: str) -> Set[str]:
        """
        Get all ancestors of a node (nodes that can influence its value)
        """
        if node_name in self.ancestors_by_name:
            return self.ancestors_by_name[node_name]

        node = self.nodes_by_name[node_name]
        ancestors: Set[str] = set()
        if not node:
            return ancestors

        # Add direct parents
        for parent in node.parent_names:
            ancestors.add(parent)
            # Add parent's ancestors recursively
            ancestors.update(self.get_all_ancestors(parent))

        self.ancestors_by_name[node_name] = ancestors
        return ancestors

    def trace(self, target: str, evidence: Mapping[str, Union[str, Set[str]]]) -> Dict[str, float]:
        """
        Calculate conditional probability distribution for target given evidence
        using beam search.
        """
        # Get the actual target name and build relevant nodes set.
        target = self.nodes_by_name[target].name
        relevant_nodes = self.get_all_ancestors(target).copy()
        relevant_nodes.add(target)

        # Add evidence nodes and their ancestors.
        for ev_node in evidence:
            if ev_node in self.nodes_by_name:
                relevant_nodes.add(ev_node)
                relevant_nodes.update(self.get_all_ancestors(ev_node))

        # Sort nodes by sampling order
        ordered_nodes = [
            node for node in self.nodes_in_sampling_order if node.name in relevant_nodes
        ]

        # Initialize beam
        beam: List[Tuple[Dict[str, Any], float]] = [({}, 1.0)]
        # Local cache for conditional probability lookups
        cpt_cache: Dict[Tuple[str, Tuple[Any, ...]], Dict[Any, float]] = {}

        for node in ordered_nodes:
            new_beam = []
            node_name = node.name

            # Determine allowed values from evidence if present
            allowed_values = evidence[node_name] if node_name in evidence else None

            # Process each assignment in the current beam
            for assignment, prob in beam:
                # Parent order is defined by node.parent_names
                try:
                    parent_values_tuple = tuple(assignment[parent] for parent in node.parent_names)
                except KeyError:
                    # Should not occur if assignments are built in order
                    parent_values_tuple = ()

                cache_key = (node_name, parent_values_tuple)
                if cache_key in cpt_cache:
                    cpt = cpt_cache[cache_key]
                else:
                    parent_values = {parent: assignment[parent] for parent in node.parent_names}
                    cpt = node.get_probabilities_given_known_values(parent_values)
                    # Use uniform distribution if missing
                    if not cpt and node.possible_values:
                        uniform_prob = 1.0 / len(node.possible_values)
                        cpt = {val: uniform_prob for val in node.possible_values}

                # Expand the beam with new assignments
                for value, p in cpt.items():
                    if (allowed_values is None or value in allowed_values) and p > 0:
                        # Create a new assignment with the new node value
                        new_assignment = assignment.copy()
                        new_assignment[node_name] = value
                        new_beam.append((new_assignment, prob * p))

            # Prune the beam if no valid configurations are left
            if new_beam:
                if len(new_beam) > BEAM_WIDTH:
                    # Get the top BEAM_WIDTH assignments
                    beam = heapq.nlargest(BEAM_WIDTH, new_beam, key=lambda x: x[1])
                else:
                    beam = new_beam
            else:
                return {}

        # Extract the target distribution
        target_dist: Dict[str, float] = {}
        total_prob = 0.0
        for assignment, prob in beam:
            if target in assignment:
                value = assignment[target]
                target_dist[value] = target_dist.get(value, 0) + prob
                total_prob += prob

        if total_prob > 0:
            return {val: p / total_prob for val, p in target_dist.items()}
        return {}

    def sample_value_from_distribution(self, distribution: Mapping[str, float]) -> str:
        """
        Sample a value from a probability distribution
        """
        anchor = random.random()  # nosec
        cumulative_probability = 0.0
        for value, probability in distribution.items():
            cumulative_probability += probability
            if anchor < cumulative_probability:
                return value
        # Fall back to first value
        return next(iter(distribution.keys()))

    def get_distribution_for_node(
        self,
        node: BayesianNode,
        sample: Mapping[str, Any],
        evidence: Optional[Dict[str, Set[str]]] = None,
    ) -> Dict[str, float]:
        """
        Get the probability distribution for a node given the current sample
        """
        # For multi-value conditions, use beam search
        if evidence and node.name in evidence and len(evidence[node.name]) > 1:
            # Current evidence is what we've sampled so far
            current_evidence = {k: v for k, v in sample.items()}

            # Calculate distribution using beam search
            distribution = self.trace(node.name, current_evidence)
            # Filter by allowed values and renormalize
            if node.name in evidence:
                allowed_values = evidence[node.name]
                filtered_dist = {k: v for k, v in distribution.items() if k in allowed_values}

                # If no probability mass, the conditions are impossible
                if not filtered_dist or sum(filtered_dist.values()) <= 0:
                    raise RestrictiveConstraints(
                        f"Cannot generate fingerprint: no valid values for {node.name} with current conditions"
                    )

                # Renormalize
                total = sum(filtered_dist.values())
                filtered_dist = {k: v / total for k, v in filtered_dist.items()}
                return filtered_dist

            return distribution

        # For regular nodes, use direct sampling
        parent_values = {parent: sample[parent] for parent in node.parent_names}

        cpt = node.get_probabilities_given_known_values(parent_values)
        if not cpt and node.possible_values:
            # If missing probabilities, use uniform distribution
            uniform_prob = 1.0 / len(node.possible_values)
            cpt = {v: uniform_prob for v in node.possible_values}

        if not cpt:
            raise RestrictiveConstraints(
                f"Cannot generate fingerprint: no probability table for {node.name}"
            )

        return cpt

    def get_shared_possibilities(
        self,
        value_possibilities: Mapping[str, Set[str]],
        seen_nodes: Optional[Set[Tuple[str, int]]] = None,
        orig_parents: Optional[Tuple[str, ...]] = None,
    ) -> Optional[Dict[str, Set[str]]]:
        """
        Get shared possibilities across nodes based on conditions.
        Returns None if conditions are contradictory.

        This is deprecated as of v1.3.0 but still exposed for testing.
        """
        # Return empty dict immediately
        if not value_possibilities:
            return {}

        if seen_nodes is None:
            seen_nodes = set()

        # Propagate upward to find possible parent values
        all_parents = {node: set(values) for node, values in value_possibilities.items()}
        for node, values in value_possibilities.items():
            # Track nodes we've processed
            if (node, len(values)) in seen_nodes:
                continue
            seen_nodes.add((node, len(values)))
            self._intersect_parents(node, values, all_parents)

        if orig_parents is None:
            orig_parents = tuple(all_parents.keys())

        # If any parent has no valid values, conditions are contradictory
        if any(len(parents) == 0 for parents in all_parents.values()):
            return None

        return all_parents

    def _intersect_parents(
        self, node: str, values: Set[str], all_parents: Dict[str, Set[str]]
    ) -> None:
        """
        Intersect possible parent values based on child node conditions
        """
        node_obj = self.nodes_by_name.get(node)
        if not node_obj:
            return

        parent_names = node_obj.parent_names
        num_parents = len(parent_names)

        # No parents exist, nothing to do
        if not num_parents:
            return

        # Build a set of each parent's possible values
        parent_values: List[Set[str]] = [set() for _ in range(num_parents)]
        for value in values:
            collect_parents(
                node_obj.probabilities,
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

        # Recurse to earlier parents if needed
        if parent_names and parent_names[0] != self.nodes_in_sampling_order[0].name:
            self._intersect_parents(
                node=parent_names[0], values=parent_values[0], all_parents=all_parents
            )


def collect_parents(
    probabilities: Mapping[str, Any],
    target: str,
    parent_values: List[Set[str]],
    so_far: Optional[List[str]] = None,
    depth: int = 0,
) -> None:
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
