"""Optional dotenv loader for the validation module."""


def load_env():
    """Load .env if python-dotenv is available, otherwise no-op."""
    try:
        from dotenv import find_dotenv, load_dotenv

        load_dotenv(find_dotenv())
    except ImportError:
        pass
