"""Reading YAML data files with libyaml's C loader when it is installed (several times faster on the multi-MB
catalogues than the pure-Python loader; same safe subset of YAML)."""

import yaml

Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def load(stream):
    return yaml.load(stream, Loader=Loader)
