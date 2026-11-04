"""Read-only source assets may be mounted separately from installed Python code."""
import os
from pathlib import Path


def project_root():
    return Path(os.environ.get('MNEMO_ASSETS', Path(__file__).resolve().parents[2]))
