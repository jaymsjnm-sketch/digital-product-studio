import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="dps-test-")
os.environ["DPS_DATA_DIR"] = _tmp
os.environ["DPS_RENDER_DPI"] = "40"          # fast renders in tests (production default is 300)
for k in ("ETSY_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CANVA_CLIENT_ID"):
    os.environ.pop(k, None)


@pytest.fixture(scope="session", autouse=True)
def db():
    from app import db as D
    D.reset_engine()
    D.init_db()
    from app.research import engine as R
    R.load_seed()
    R.rank_all()
    yield
