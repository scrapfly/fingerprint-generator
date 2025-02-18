from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Union, overload

import orjson

from fpgen.bayesian_network import BayesianNetwork, StrContainer
from fpgen.exceptions import (
    ConstraintKeyError,
    InvalidConstraints,
    InvalidScreenConstraints,
)
from fpgen.structs import CaseInsensitiveDict
from fpgen.unpacker import flatten, lookup_value_list, make_output_dict

from .pkgman import __is_module__, assert_downloaded

NETWORK_FILE = Path(__file__).parent / 'data' / "fingerprint-network.json"
assert_downloaded(NETWORK_FILE)


@dataclass
class Screen:
    """Constrains the screen dimensions of the generated fingerprint"""

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
                "Invalid screen constraints: min values cannot be greater than max values"
            )

    def is_set(self) -> bool:
        """
        Returns true if any constraints were set
        """
        return any(value is not None for value in self.__dict__.values())


class Generator:
    """Generates realistic browser fingerprints"""

    if not __is_module__():
        # Do not attempt to load the network if we are running as a module
        network = BayesianNetwork(NETWORK_FILE)

    def __init__(
        self,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        screen_size: Optional[Screen] = None,
        strict: bool = True,
        **constraints: Any,
    ):
        """
        Initializes the FingerprintGenerator with the given options.

        Parameters:
            screen (Screen, optional): Screen constraints for the generated fingerprint.
            strict (bool, optional): Whether to raise an exception if the constraints are too strict. Default is False.
            **constraints: Constrains for the network
        """
        if constraints_dict and constraints:
            raise ValueError("Cannot pass values as dict & as parameters")

        # Set default options
        self.screen_size: Optional[Screen] = screen_size
        self.strict: bool = strict
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
        screen: Optional[Screen] = None,
        strict: Optional[bool] = None,
        target: str,
        **constraints: Any,
    ) -> Any: ...

    @overload
    def generate(
        self,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        screen: Optional[Screen] = None,
        strict: Optional[bool] = None,
        target: Optional[StrContainer] = None,
        **constraints: Any,
    ) -> Dict[str, Any]: ...

    def generate(
        self,
        constraints_dict: Optional[Dict[str, Any]] = None,
        *,
        screen_size: Optional[Screen] = None,
        strict: Optional[bool] = None,
        target: Optional[Union[str, StrContainer]] = None,
        **constraints: Any,
    ) -> Dict[str, Any]:
        """
        Generates a fingerprint and a matching set of ordered headers using a combination of the default options
        specified in the constructor and their possible overrides provided here.

        Parameters:
            screen (Screen, optional): Screen constraints for the generated fingerprint.
            strict (bool, optional): Whether to raise an exception if the constraints are too strict.
            constraints: Constrains for the network
            target (Optional[Union[str, StrContainer]]): Only generate specific value(s)
        """
        if constraints_dict and constraints:
            raise ValueError("Cannot pass values as dict & as parameters")

        if constraints_dict:
            constraints = constraints_dict

        if constraints:
            filtered_values: Dict[str, List[str]] = {}
            self._build_constraints(constraints, filtered_values)
        else:
            filtered_values = self.filtered_values

        # Merge new options with old
        screen_size = _first(screen_size, self.screen_size)
        strict = _first(strict, self.strict)

        # Handle screen constraints
        if screen_size and isinstance(screen_size, Screen):
            self._filter_by_screen(
                strict=strict, screen=screen_size, filtered_values=filtered_values
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
                fingerprint = self.network.generate_certain_nodes(filtered_values, target_roots)
            else:
                fingerprint = self.network.generate_consistent_sample(filtered_values)

            # Found the fingerprint
            if fingerprint is not None:
                break
            # Raise an error if the filtered_values are too strict
            if strict:
                raise ValueError('Cannot generate fingerprint. Constraints are too restrictive.')
            # If no fingerprint was generated, relax the filtered values until we find one
            filtered_values.pop(next(iter(filtered_values.keys())))

        # If we arent searching for certain targets, we can return right away
        output = make_output_dict(fingerprint)
        if target:
            output = self._reassemble_targets(_tupilize(target), output)
            if isinstance(target, str):
                return output[target]
        return output

    def _reassemble_targets(self, targets: StrContainer, fingerprint: Dict[str, Any]):
        result = {}
        for target in targets:
            try:
                data = _at_path(fingerprint, target.split('.'), casefold=True)
            except ConstraintKeyError as key:
                raise InvalidConstraints(f'{key} is not a possible key in {target}')

            result[target] = data
        return result

    @staticmethod
    def _build_constraints(
        constraints: Dict[str, Any], filtered_values: Dict[str, List[str]]
    ) -> None:
        """
        Builds a map of filtered values based on given constraints
        """
        # flatten to match the format of the fingerprint network
        constraints = flatten(constraints, casefold=True)

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
                        except ConstraintKeyError:
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

    def _filter_by_screen(
        self, strict: Optional[bool], screen: Screen, filtered_values: Dict
    ) -> None:
        """
        Generates partial content security policy (CSP) based on the provided options and filtered values.
        """
        possible_screens = _lookup_possibilities('screen')
        if possible_screens is None:
            raise Exception("No possible screens found. Bad network?")

        filtered_values['screen'] = [
            lookup_value
            for screen_screen, lookup_value in possible_screens.items()
            if self._is_screen_within_constraints(screen_screen, screen)
        ]

        if not filtered_values['screen']:
            if strict:
                raise InvalidScreenConstraints("No possible screens found. Bad network?")
            del filtered_values['screen']

    @staticmethod
    def _is_screen_within_constraints(screen_string: str, screen: Screen) -> bool:
        """
        Checks if the given screen dimensions are within the specified constraints.
        """
        screen_data = orjson.loads(screen_string)
        if (
            not isinstance(screen_data, dict)
            or not isinstance(screen_data['width'], int)
            or not isinstance(screen_data['height'], int)
        ):
            return False  # bad data
        return (
            screen_data['width'] >= (screen.min_width or 0)
            and screen_data['width'] <= (screen.max_width or 1e5)
            and screen_data['height'] >= (screen.min_height or 0)
            and screen_data['height'] <= (screen.max_height or 1e5)
        )


def _at_path(data: Mapping, path: StrContainer, *, casefold=False) -> Any:
    """
    Checks the value at athe given path in a dictionary
    """
    for key in path:
        if casefold:
            data = CaseInsensitiveDict(data)
        if not isinstance(data, MutableMapping) or key not in data:
            raise ConstraintKeyError(key)
        data = data[key]
    return data


def get_values(node_name: str) -> Optional[List[Any]]:
    """
    Returns the possible values for the given node name.
    """
    possible_values = _lookup_possibilities(node_name, casefold=False)
    # Dedupe, load jsons, and return as list
    if possible_values is not None:
        return list(map(orjson.loads, set(possible_values.keys())))

    # User passed a nested key. Attempt to find a root node
    nested_keys: List[str] = []
    node_name, possible_values = _lookup_root_possibilities(
        node_name, nested_keys=nested_keys, casefold=False
    )
    # Fetch value at the nested path, and convert back to hashable type to dedupe
    data = set(
        orjson.dumps(_at_path(orjson.loads(val), nested_keys)) for val in possible_values.keys()
    )
    # Load values back to python objects
    return list(map(orjson.loads, data))


def _lookup_root_possibilities(
    key: str, nested_keys: Optional[List[str]] = None, casefold: bool = True
) -> Any:
    """
    Finds the root node of a given key
    """
    while key:
        keys = key.rsplit('.', 1)
        if len(keys) != 2:
            raise InvalidConstraints(f'{key} is not a valid constraint key')
        key, sliced_key = keys

        if nested_keys is not None:
            nested_keys.append(sliced_key)

        # if a nested key is avaliable, enter it
        possible_values = _lookup_possibilities(key, casefold)
        # iterate backwards until we find the node
        if possible_values is not None:
            break

    if possible_values is None:
        raise InvalidConstraints(f'{key} is not a valid constraint key')

    if nested_keys:
        nested_keys.reverse()

    return key, possible_values


def _lookup_possibilities(node_name: str, casefold: bool = True) -> Optional[Dict]:
    """
    Returns the possible values for the given node name.
    Returns as a dictionary {value: lookup_index}

    """
    if node_name not in Generator.network.nodes_by_name:
        return None

    lookup_values = Generator.network.nodes_by_name[node_name].possible_values
    actual_values = lookup_value_list(lookup_values)

    return {
        (actual.casefold() if casefold else actual): lookup
        for actual, lookup in zip(actual_values, lookup_values)
    }


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


def _find_roots(targets: Union[str, StrContainer]) -> Iterator[str]:
    """
    Given a list of targets, return all nodes that make up that target's data
    """
    for target in targets:
        target = target.casefold()
        while True:
            # Found a valid target
            if target in Generator.network.nodes_by_name:
                yield target
                break

            keys = target.rsplit('.', 1)
            if len(keys) > 1:
                # Move target back 1
                target = keys[0]
                continue

            # We are at the root key.
            # Find potential keys before quitting
            found = False
            for node in Generator.network.nodes_by_name:
                if not node.startswith(keys[0]):
                    continue
                # Check if its a . afterward
                key_len = len(keys[0])
                if len(node) > key_len and node[key_len] != '.':
                    continue
                found = True
                yield node

            if not found:
                raise InvalidConstraints(f'Unknown node: {target}')

            break
