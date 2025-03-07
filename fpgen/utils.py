from collections.abc import MutableMapping
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Union,
)

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


def _assert_network_exists() -> None:
    """
    Quick helper to confirm NETWORK is defined
    """
    if NETWORK is None:
        raise NetworkError("FPGEN_NO_INIT is enabled. Cannot access the network.")


def query(
    target: str, *, flatten: bool = False, sort: bool = False
) -> Union[Dict[str, Any], List[Any]]:
    """
    Query a list of possibilities given a target.

    Parameters:
        target (str): Target node to query possible values for
        flatten (bool, optional): Whether to flatten the output array
        sort (bool, optional): Whether to sort the output arrays
    """
    _assert_network_exists()

    # Check node list first
    values = _lookup_possibilities(target, casefold=False)
    if values:
        output: Union[Tuple, map]
        output = tuple(map(orjson.loads, values))
        # Merge dicts if data is all dicts, else just return a deduped list
        if all(isinstance(d, dict) for d in output):
            # Flatten the output dict before returning if needed
            return _maybe_flatten(flatten, _merge_dicts(output, sort=sort))
        else:
            # Dedupe the list
            return _dedupe(output, sort=sort)

    # Target is within a node. Need to look up the tree
    nested_keys: List[str] = []
    root_data = _lookup_root_possibilities(
        target, nested_keys=nested_keys, none_if_missing=True, casefold=False
    )
    if root_data is not None:
        # Read possibile values as jsons
        output = map(orjson.loads, root_data[1])
        # Pull the item at the target path
        output = map(lambda d: _at_path(d, nested_keys), output)
        output = tuple(output)

        # If they are all dicts, merge them
        if all(isinstance(d, dict) for d in output):
            # Flatten the output dict if needed
            return _maybe_flatten(flatten, _merge_dicts(output, sort=sort))

        # Return a deduped list
        return _dedupe(output, sort=sort)

    # Search down the tree
    data = _search_downward(target)
    resp: Dict[str, List[Any]] = {
        # Remove the current node path
        key.removeprefix(f'{target}.'): [
            # Parse each possible value via orjson
            orjson.loads(d)
            for d in (_lookup_possibilities(key, casefold=False) or tuple())
        ]
        for key in data
    }
    if flatten:
        # May need to flatten further
        return _flatten({node: _dedupe(values, sort=sort) for node, values in resp.items()})
    return _unflatten(resp, sort=sort)


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
) -> Optional[Tuple[str, Dict[str, Any]]]:
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


def _lookup_possibilities(node_name: str, casefold: bool = True) -> Optional[Dict[str, Any]]:
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


def _search_downward(domain: str) -> Iterable[str]:
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


def _dedupe(lst: Iterable[Any], sort: bool) -> List[Any]:
    """
    Group items by their type, deduping each group
    """
    groups: Dict[type, Any] = {}
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
        # Do not sort if `sort` is False, or if type is unhashable
        if not sort or t in (list, dict):
            result.extend(items)
        else:
            result.extend(sorted(items))
    return result


def _unflatten(dictionary, sort: bool) -> Dict[str, Any]:
    """
    Unflatten dicts and dedupe any nested lists
    """
    result_dict: Dict[str, Any] = dict()
    for key, value in dictionary.items():
        parts = key.split(".")
        d = result_dict
        for part in parts[:-1]:
            if part not in d:
                d[part] = dict()
            d = d[part]
        # Dedupe lists
        if isinstance(value, list):
            value = _dedupe(value, sort=sort)
        d[parts[-1]] = value
    return result_dict


def _flatten(dictionary: Dict[str, Any], parent_key=False) -> Dict[str, Any]:
    """
    Turn a nested dictionary into a flattened dictionary
    https://stackoverflow.com/questions/6027558/flatten-nested-dictionaries-compressing-keys
    """
    items: List[Tuple[str, Any]] = []
    for key, value in dictionary.items():
        new_key = str(parent_key) + '.' + key if parent_key else key
        if isinstance(value, dict):
            items.extend(_flatten(value, new_key).items())
        else:
            items.append((new_key, value))
    return dict(items)


def _maybe_flatten(flatten: Optional[bool], data):
    if not isinstance(data, dict):
        return data
    if flatten:
        return _flatten(data)
    return data


def _merge_dicts(dict_list: Iterable[Dict[str, Any]], sort: bool) -> Dict[str, Any]:
    """
    Merge items in a list of dicts into a dict of merged values.
    For a given key, if all values are dicts, merge them recursively.
    If all values are lists, flatten them into a single list and dedupe.
    Otherwise, dedupe the list of values.
    """
    if not dict_list:
        return {}

    merged: Dict[str, Any] = {}
    # Get the union of keys from all dictionaries.
    all_keys: Set[str] = set()
    for d in dict_list:
        all_keys.update(d.keys())

    for key in all_keys:
        # Get the list of values for the current key, skipping dicts that don't have it
        values = [d[key] for d in dict_list if key in d]

        if all(isinstance(v, dict) for v in values):
            # Merge dictionaries recursively
            merged[key] = _merge_dicts(values, sort=sort)
        elif all(isinstance(v, list) for v in values):
            # Merge lists
            merged_list = []
            for lst in values:
                merged_list.extend(lst)
            merged[key] = _dedupe(merged_list, sort=sort)
        else:
            # For mixed/scalar values, dedupe
            merged[key] = _dedupe(values, sort=sort)

    return merged


"""
Parse user input
"""


def _flatten_constraints(
    dictionary: Mapping[str, Any], parent_key: str = '', casefold: bool = False
) -> Dict[str, Any]:
    """
    Flattens the passed list of constraints
    """
    # Original flattening logic from here:
    # https://stackoverflow.com/questions/6027558/flatten-nested-dictionaries-compressing-keys
    items: List[Tuple[str, Any]] = []
    for key, value in dictionary.items():
        new_key = parent_key + '.' + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(_flatten_constraints(value, new_key).items())
        else:
            # If we have a tuple or set, treat it as an array of possible values
            if isinstance(value, (set, tuple)):
                value = tuple(orjson.dumps(v).decode() for v in value)
            else:
                value = orjson.dumps(value).decode()
            if casefold:
                new_key = new_key.casefold()
            items.append((new_key, value))
    return dict(items)


"""
Convert network output to human readable output
"""


def _make_output_dict(data: Dict[str, Any], flatten: Optional[bool]) -> Dict[str, Any]:
    """
    Unflattens & builds the output dictionary
    """
    if flatten:
        # Get key value pairs directly without building structure
        values = lookup_value_list(data.values())
        for key, value in zip(data.keys(), values):
            data[key] = orjson.loads(value)
        # Flatten node values that themselves are dicts
        return _flatten(data)

    # Original unflattening logic from here:
    # https://stackoverflow.com/questions/6037503/python-unflatten-dict
    result_dict: Dict[str, Any] = dict()
    for key, value in zip(data.keys(), lookup_value_list(data.values())):
        parts = key.split(".")
        d = result_dict
        for part in parts[:-1]:
            if part not in d:
                d[part] = dict()
            d = d[part]
        d[parts[-1]] = orjson.loads(value)

    return result_dict


# Only expose `query` publicly
__all__ = ('query',)
