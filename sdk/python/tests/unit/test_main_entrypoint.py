"""`python -m agentspan` must invoke the same entry point as the `agentspan` console
script (the `agentspan.cli:main` entry point). This guards the Windows-friendly
module-execution path so it can't silently regress.
"""
import importlib


def test_main_module_reexports_cli_main():
    main_mod = importlib.import_module("agentspan.__main__")
    from agentspan.cli import main as cli_main

    assert main_mod.main is cli_main


def test_importing_main_module_does_not_run_cli(monkeypatch):
    # Importing the module must NOT execute the CLI — only `python -m agentspan`
    # (running it as __main__) should. Importing it here must stay side-effect free.
    import agentspan.cli as cli

    called = []
    monkeypatch.setattr(cli, "main", lambda *a, **k: called.append(True))
    importlib.reload(importlib.import_module("agentspan.__main__"))

    assert called == []
