"""
Shared test configuration.

Makes the tests runnable straight from a checkout: puts the core library and the
v2 backend on the import path, and sets the auth environment the backend requires
so `import main` succeeds without a real secret.
"""
import os
import pathlib
import sys
import tempfile

import numpy as np
import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
# core lives in v1/src/core; the backend modules (main/auth/api/models) are flat in v2/backend
sys.path.insert(0, str(_ROOT / "v1" / "src"))
sys.path.insert(0, str(_ROOT / "v2" / "backend"))

# Auth config must exist before `import main` (auth.py fails fast if these are unset).
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("APP_USERNAME", "tester")
if "APP_PASSWORD_HASH" not in os.environ:
    from argon2 import PasswordHasher

    os.environ["APP_PASSWORD_HASH"] = PasswordHasher().hash("testpass")

# Saved-routes storage → an isolated temp dir, so tests never touch real data.
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="trackalong-test-"))

# Known-good credentials the API tests log in with.
TEST_USERNAME = os.environ["APP_USERNAME"]
TEST_PASSWORD = "testpass"


@pytest.fixture
def synthetic_profile() -> np.ndarray:
    """
    A (N, 4) profile [chainage, lat, lng, ground_elev] with a single hill, so the
    optimiser produces a mix of cut and fill. Straight in plan (no horizontal curves).
    """
    n = 501
    chainage = np.linspace(0.0, 5000.0, n)
    lat = np.linspace(-33.00, -33.02, n)
    lng = np.linspace(151.00, 151.05, n)
    elev = 100.0 + 60.0 * np.exp(-(((chainage - 2500.0) / 700.0) ** 2))
    return np.column_stack([chainage, lat, lng, elev])
