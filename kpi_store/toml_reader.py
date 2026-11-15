"""Reads TOML on every Python the Databricks side runs on.

Python 3.11 brought tomllib. The notebook also runs on Python 3.10: Databricks serverless compute of environment
version 1 has it, and the first real run met it there. So the modules that run in the notebook read TOML through
this module, which takes the first of three readers that is there:

    tomllib            Python 3.11 and later
    tomli              the same reader as a package; the notebook installs it
    pip._vendor.tomli  the copy that pip carries on a Python below 3.11

All three are one code base, with one loads() and one TOMLDecodeError. The notebook's own bootstrap cannot import
this module, because it runs before the zip is unpacked; it holds the same few lines.

The modules of the machine side (the runner, the setup check, the local settings, the intake pack) import tomllib
directly and need Python 3.11, which the setup check enforces.
"""
import importlib
import sys

READERS = ("tomllib", "tomli", "pip._vendor.tomli")


def reader(names=READERS, load=importlib.import_module):
    """The first TOML reader that can be imported. Raises ImportError with one sentence when none is there."""
    for name in names:
        try:
            return load(name)
        except ImportError:
            continue
    version = ".".join(str(part) for part in sys.version_info[:3])
    raise ImportError(f"Python {version} has no TOML reader. Python 3.11 and later bring one (tomllib); on an older "
                      "Python install the package tomli")


_reader = reader()
loads = _reader.loads
TOMLDecodeError = _reader.TOMLDecodeError
