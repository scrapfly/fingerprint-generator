from collections.abc import MutableMapping
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Union

import orjson

from .bayesian_network import BayesianNetwork, StrContainer
from .exceptions import InvalidNode, NetworkError, NodePathError
from .pkgman import NETWORK_FILE, __is_module__
from .structs import CaseInsensitiveDict
from .unpacker import lookup_value_list

# Load the network. (unless we're running as a module)
NETWORK: BayesianNetwork
if __is_module__():
    NETWORK = None  # type: ignore
else:
    NETWORK = BayesianNetwork(NETWORK_FILE)


def _assert_network_exists():
    """
    Quick helper to confirm NETWORK is defined
    """
    if NETWORK is None:
        raise NetworkError("FPGEN_NO_INIT is enabled. Cannot access the network.")


def query(target: str) -> Union[Dict[str, Any], List[Any]]:
    """
    Query a list of possibilities given a target.
    """
    _assert_network_exists()

    # Check node list first
    values = _lookup_possibilities(target, casefold=False)
    if values:
        output: Union[Tuple, map]
        output = tuple(map(orjson.loads, values))
        if all(isinstance(d, dict) for d in output):
            return _merge_dicts(output)
        return _dedupe(output)

    # Target is within a node. Need to look up the tree
    nested_keys: List[str] = []
    data = _lookup_root_possibilities(
        target, nested_keys=nested_keys, none_if_missing=True, casefold=False
    )
    if data is not None:
        # Read possibile values as jsons
        output = map(orjson.loads, data[1])
        # Pull the item at the target path
        output = map(lambda d: _at_path(d, nested_keys), output)
        output = tuple(output)

        # If they are all dicts, merge them
        if all(isinstance(d, dict) for d in output):
            return _merge_dicts(output)

        # Return a deduped list
        return _dedupe(output)

    # Search down the tree
    data = _search_downward(target)
    return _unflatten(
        {
            # Remove the current node path
            key.removeprefix(f'{target}.'): [
                # Parse each possible value via orjson
                orjson.loads(d)
                for d in (_lookup_possibilities(key, casefold=False) or [])
            ]
            for key in data
        }
    )


"""
Helper functions for searching for nodes up/down the network
"""


def _at_path(data: Mapping, path: StrContainer, *, casefold=False) -> Any:
    """
    Gets the value in nested dictionary given its path
    """
    for key in path:
        if casefold:
            data = CaseInsensitiveDict(data)
        if not isinstance(data, MutableMapping) or key not in data:
            raise NodePathError(key)
        data = data[key]
    return data


def _lookup_root_possibilities(
    key: str,
    nested_keys: Optional[List[str]] = None,
    casefold: bool = True,
    none_if_missing: bool = False,
) -> Any:
    """
    Finds the first avaliable root node of a given key, and queries its possibilities
    """
    if not key:
        raise InvalidNode('Key cannot be empty.')
    while key:
        keys = key.rsplit('.', 1)
        # Ran out of keys to parse
        if len(keys) != 2:
            if none_if_missing:
                return None
            raise InvalidNode(f'{key} is not a valid node')
        key, sliced_key = keys

        if nested_keys is not None:
            nested_keys.append(sliced_key)

        # if a nested key is avaliable, enter it
        possible_values = _lookup_possibilities(key, casefold)
        # iterate backwards until we find the node
        if possible_values is not None:
            break

    if possible_values is None:
        if none_if_missing:
            return None
        raise InvalidNode(f'{key} is not a valid node')

    if nested_keys:
        nested_keys.reverse()

    return key, possible_values


def _lookup_possibilities(node_name: str, casefold: bool = True) -> Optional[Dict]:
    """
    Returns the possible values for the given node name.
    Returns as a dictionary {value: lookup_index}
    """
    if node_name not in NETWORK.nodes_by_name:
        return None

    lookup_values = NETWORK.nodes_by_name[node_name].possible_values
    actual_values = lookup_value_list(lookup_values)

    return {
        (actual.casefold() if casefold else actual): lookup
        for actual, lookup in zip(actual_values, lookup_values)
    }


def _search_downward(domain: str):
    """
    Searches for all nodes that begin with a specific key
    """
    found = False
    for i, node in enumerate(NETWORK.nodes_by_name.keys()):
        if not node.startswith(domain):
            continue
        # Check if its a . afterward
        key_len = len(domain)
        if len(node) > key_len and node[key_len] != '.':
            continue
        if not found:
            found = True
        # Get the original case
        yield NETWORK.node_names[i]

    if not found:
        raise InvalidNode(f'Unknown node: "{domain}"')


def _find_roots(targets: Union[str, StrContainer]) -> Iterator[str]:
    """
    Given a list of targets, return all nodes that make up that target's data
    """
    for target in targets:
        target = target.casefold()
        while True:
            # Found a valid target
            if target in NETWORK.nodes_by_name:
                yield target
                break

            keys = target.rsplit('.', 1)
            if len(keys) > 1:
                # Move target back 1
                target = keys[0]
                continue

            # We are at the root key.
            # Find potential keys before quitting
            yield from _search_downward(keys[0])
            break


def _reassemble_targets(targets: StrContainer, fingerprint: Dict[str, Any]):
    result = {}
    for target in targets:
        try:
            data = _at_path(fingerprint, target.split('.'), casefold=True)
        except NodePathError as key:
            raise InvalidNode(f"'{target}' is not a valid key path (missing {key}).")
        result[target] = data
    return result


"""
Miscellaneous python list/dict helpers
"""


def _dedupe(lst):
    """
    Group items by their type, deduping each group
    """
    groups = {}
    for item in lst:
        t = type(item)
        if t not in groups:
            groups[t] = []
        # Only add item if it's not already in its type group
        if item not in groups[t]:
            groups[t].append(item)

    result = []
    # Process groups in order sorted by type name
    for t in sorted(groups.keys(), key=lambda typ: typ.__name__):
        items = groups[t]
        # For list and dict types, dedupe but don't sort
        if t in (list, dict):
            result.extend(items)
        else:
            result.extend(sorted(items))
    return result


def _unflatten(dictionary):
    """
    Unflatten dicts and dedupe any nested lists
    """
    result_dict = dict()
    for key, value in dictionary.items():
        parts = key.split(".")
        d = result_dict
        for part in parts[:-1]:
            if part not in d:
                d[part] = dict()
            d = d[part]
        # Dedupe lists
        if isinstance(value, list):
            value = _dedupe(value)
        d[parts[-1]] = value
    return result_dict


def _merge_dicts(dict_list):
    """
    Merge items in a list of dicts -> dict of list
    """
    if not dict_list:
        return {}
    merged = {}
    # iterate over the keys from the first dictionary
    for key in dict_list[0]:
        # if the value is a dictionary, merge recursively
        if isinstance(dict_list[0][key], dict):
            merged[key] = _merge_dicts([d[key] for d in dict_list])
        else:
            # deduplicate the list of values
            merged[key] = _dedupe([d[key] for d in dict_list])
    return merged


# Only expose `query` publicly
__all__ = ('query',)
