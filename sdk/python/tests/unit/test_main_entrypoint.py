"""`python -m conductor.ai` must invoke the same entry point as the `agentspan` console
script (the `conductor.ai.cli:main` entry point). This guards the Windows-friendly
module-execution path so it can't silently regress.
"""
import importlib


def test_main_module_reexports_cli_main():
    main_mod = importlib.import_module("conductor.ai.__main__")
    from conductor.ai.cli import main as cli_main

    assert main_mod.main is cli_main


def test_importing_main_module_does_not_run_cli(monkeypatch):
    # Importing the module must NOT execute the CLI — only `python -m conductor.ai`
    # (running it as __main__) should. Importing it here must stay side-effect free.
    import conductor.ai.cli as cli

    called = []
    monkeypatch.setattr(cli, "main", lambda *a, **k: called.append(True))
    importlib.reload(importlib.import_module("conductor.ai.__main__"))

    assert called == []
