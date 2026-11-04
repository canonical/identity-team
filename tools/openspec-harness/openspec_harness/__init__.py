"""OpenSpec integration package for Google's harness2 in canonical repositories."""

from .adapter import OpenSpecAdapter
from .drift import check_drift, load_drift_config
from .init import init_repository
from .proposer import OpenSpecScriptedProposer
from .validation import validate_workspace

__all__ = [
    "OpenSpecAdapter",
    "OpenSpecScriptedProposer",
    "check_drift",
    "init_repository",
    "load_drift_config",
    "validate_workspace",
]