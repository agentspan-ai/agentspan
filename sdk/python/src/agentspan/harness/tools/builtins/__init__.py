# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Built-in tools shipped with the harness."""

from .delete_file import DeleteFile
from .file_outline import FileOutline
from .find_references import FindReferences
from .github import FetchIssue, FetchPR, OpenPR, SetupRepo
from .list_files import ListFiles
from .multi_edit import MultiEdit
from .patch_file import PatchFile
from .read_file import ReadFile
from .read_symbol import ReadSymbol
from .read_task_output import ReadTaskOutput, StopTask
from .search_text import SearchText
from .shared_store_tools import SharedStoreList, SharedStoreRead, SharedStoreWrite
from .shell import Shell
from .spawn_agent import SpawnAgent
from .structured_output import StructuredOutput
from .update_plan import UpdatePlan
from .web_fetch import WebFetch
from .write_file import WriteFile

__all__ = [
    "DeleteFile",
    "FetchIssue",
    "FetchPR",
    "FileOutline",
    "FindReferences",
    "ListFiles",
    "MultiEdit",
    "OpenPR",
    "PatchFile",
    "ReadFile",
    "ReadSymbol",
    "ReadTaskOutput",
    "SearchText",
    "SetupRepo",
    "SharedStoreList",
    "SharedStoreRead",
    "SharedStoreWrite",
    "Shell",
    "SpawnAgent",
    "StopTask",
    "StructuredOutput",
    "UpdatePlan",
    "WebFetch",
    "WriteFile",
]


def default_readonly_tools():
    """Read-only built-ins: read_file, list_files, search_text, file_outline,
    find_references, read_symbol."""
    return [
        ReadFile(), ListFiles(), SearchText(),
        FileOutline(), FindReferences(), ReadSymbol(),
    ]


def default_edit_tools():
    """Read + write tools (no shell, no spawn_agent)."""
    return default_readonly_tools() + [
        WriteFile(), PatchFile(), MultiEdit(), DeleteFile(),
    ]


def default_full_tools():
    """The full v1 set: read + edit + shell + plan + task tools + shared store.

    ``spawn_agent`` and the GitHub primitives are omitted — embedders
    add ``SpawnAgent(factory=...)`` and ``SetupRepo()`` / ``FetchIssue()``
    / ``FetchPR()`` / ``OpenPR()`` based on whether they want subagent
    spawning and GitHub workflow support.
    """
    return default_edit_tools() + [
        Shell(),
        UpdatePlan(),
        StructuredOutput(),
        ReadTaskOutput(),
        StopTask(),
        SharedStoreRead(),
        SharedStoreWrite(),
        SharedStoreList(),
    ]


def default_github_tools():
    """The GitHub-flavored tools that depend on the ``gh`` CLI."""
    return [SetupRepo(), FetchIssue(), FetchPR(), OpenPR()]
