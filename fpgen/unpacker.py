import base64
from typing import List, Tuple

import numpy as np
from indexed_zstd import IndexedZstdFile

from .bayesian_network import extract_json
from .pkgman import VALUES_DATA, VALUES_JSON, __is_module__


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
