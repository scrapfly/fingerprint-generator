# https://stackoverflow.com/a/32888599
class CaseInsensitiveDict(dict):
    @classmethod
    def _k(cls, key):
        return key.casefold() if isinstance(key, str) else key

    def __init__(self, *args, **kwargs):
        super(CaseInsensitiveDict, self).__init__(*args, **kwargs)
        self._convert_keys()

    def __getitem__(self, key):
        return super(CaseInsensitiveDict, self).__getitem__(self.__class__._k(key))

    def __setitem__(self, key, value):
        super(CaseInsensitiveDict, self).__setitem__(self.__class__._k(key), value)

    def __delitem__(self, key):
        return super(CaseInsensitiveDict, self).__delitem__(self.__class__._k(key))

    def __contains__(self, key):
        return super(CaseInsensitiveDict, self).__contains__(self.__class__._k(key))

    def has_key(self, key):
        return super(CaseInsensitiveDict, self).has_key(self.__class__._k(key))

    def pop(self, key, *args, **kwargs):
        return super(CaseInsensitiveDict, self).pop(self.__class__._k(key), *args, **kwargs)

    def get(self, key, *args, **kwargs):
        return super(CaseInsensitiveDict, self).get(self.__class__._k(key), *args, **kwargs)

    def setdefault(self, key, *args, **kwargs):
        return super(CaseInsensitiveDict, self).setdefault(self.__class__._k(key), *args, **kwargs)

    def update(self, E={}, **F):
        super(CaseInsensitiveDict, self).update(self.__class__(E))
        super(CaseInsensitiveDict, self).update(self.__class__(**F))

    def _convert_keys(self):
        for k in list(self.keys()):
            v = super(CaseInsensitiveDict, self).pop(k)
            self.__setitem__(k, v)


# ***********************
# Miscellaneous python list/dict helpers
# ***********************


def _dedupe(lst):
    # Dedupe and sort
    if not any(isinstance(d, (list, dict)) for d in lst):
        return sorted(set(lst))
    # Dedupe unhashable items
    result = []
    for item in lst:
        if item not in result:
            result.append(item)
    return result


def _unflatten(dictionary):
    # Unflatten dicts
    result_dict = dict()
    for key, value in dictionary.items():
        parts = key.split(".")
        d = result_dict
        for part in parts[:-1]:
            if part not in d:
                d[part] = dict()
            d = d[part]
        d[parts[-1]] = value
    return result_dict


def _merge_dicts(dict_list):
    # Merge items in a list of dicts
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


__all__ = ['CaseInsensitiveDict', '_dedupe', '_unflatten', '_merge_dicts']
