import base64
from collections.abc import MutableMapping
from pathlib import Path
from typing import List, Tuple

import numpy as np
import orjson
from indexed_zstd import IndexedZstdFile

from .bayesian_network import extract_json
from .pkgman import __is_module__, assert_downloaded

DATA_DIR = Path(__file__).parent / 'data'

VALUES_JSON = DATA_DIR / 'values.json'
VALUES_DATA = DATA_DIR / 'values.dat'

assert_downloaded(VALUES_JSON, VALUES_DATA)


def load_values_json() -> List[Tuple[str, List[str]]]:
    values_json = extract_json(VALUES_JSON)
    return list(values_json.items())


if not __is_module__():
    # Do not attempt to load values.json if we are running as a module
    VALUE_PAIRS = load_values_json()


def base85_to_int(s: str) -> int:
    # Decode using base85
    decoded_bytes = base64.b85decode(s)
    # Convert bytes to integer
    return int.from_bytes(decoded_bytes, byteorder='big')


def get_dat_file():
    """
    Returns a seekable file descriptor (or indexed zst file)
    """
    if VALUES_DATA.exists():
        return open(VALUES_DATA, 'rb')
    elif (zst_path := VALUES_DATA.with_suffix('.dat.zst')).exists():
        return IndexedZstdFile(str(zst_path))

    raise FileNotFoundError(f'Missing required file: {VALUES_DATA}')


def lookup_value(index):
    offset, length = VALUE_PAIRS[base85_to_int(index)]
    file = get_dat_file()
    file.seek(int(offset, 16))
    data = file.read(length).decode('utf-8')
    file.close()
    return data


def lookup_value_list(index_list):
    """
    Returns a list of values from the data file given a list of lookup values
    """
    # Empty numpy array of len(index_list)
    value_map = np.empty(len(index_list), dtype=object)

    file = get_dat_file()
    # Read in order from lowest index to highest
    sorted_indices = sorted(
        (base85_to_int(lookup_index), n) for n, lookup_index in enumerate(index_list)
    )

    for index, n in sorted_indices:
        offset, length = VALUE_PAIRS[index]
        file.seek(int(offset, 16))
        # Set to key in order of the original list
        value_map[n] = file.read(length).decode('utf-8')

    file.close()
    return value_map


def flatten(dictionary, parent_key='', casefold=False):
    # Original flattening logic from here:
    # https://stackoverflow.com/questions/6027558/flatten-nested-dictionaries-compressing-keys

    items = []
    for key, value in dictionary.items():
        new_key = parent_key + '.' + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(flatten(value, new_key).items())
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


def make_output_dict(data):
    # Original unflattening logic from here:
    # https://stackoverflow.com/questions/6037503/python-unflatten-dict

    result_dict = dict()
    for key, value in zip(data.keys(), lookup_value_list(data.values())):
        parts = key.split(".")
        d = result_dict
        for part in parts[:-1]:
            if part not in d:
                d[part] = dict()
            d = d[part]
        d[parts[-1]] = orjson.loads(value)

    return result_dict
    return result_dict
