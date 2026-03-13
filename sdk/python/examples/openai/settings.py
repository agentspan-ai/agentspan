# Re-export from parent so subdir examples can `from settings import settings`.
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "settings", Path(__file__).resolve().parent.parent / "settings.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
settings = _mod.settings
