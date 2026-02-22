# Copyright (c) 2009-2015, Dwight Hubbard
# Copyrights licensed under the New BSD License
# See the accompanying LICENSE.txt file for terms.

from .dlipower import Outlet, PowerSwitch, DLIPowerException

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("dlipower")
except (ImportError, PackageNotFoundError):
    __version__ = str('0.0.0')

__all__ = ['dlipower']
