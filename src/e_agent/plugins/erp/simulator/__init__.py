"""ERP simulator: the discovered provider plugin ``fixture-erp`` (ADR 0026).

A FIXTURE: an in-memory ERP with deterministic scenarios. Evidence produced with
it is labelled ``environment=fixture`` and is never a capability claim. A profile
that does not enable ``fixture-erp`` never imports this package.
"""

from importlib.resources import files
from pathlib import Path


def fixture_profile_path() -> Path:
    """The fixture profile that enables this simulator; the server ships no profile."""
    return Path(str(files(__name__).joinpath("fixture_profile.json")))
