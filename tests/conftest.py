import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def latex_map(tmp_path_factory):
    """Paper map of the synthetic LaTeX test paper."""
    from paper_check.ingest import ingest
    from paper_check.model import PaperMap

    out = tmp_path_factory.mktemp("latex_basic")
    ingest(FIXTURES / "latex_basic", output=str(out))
    return PaperMap.load(out / "paper-check-work" / "paper_map.json"), out / "paper-check-work"


@pytest.fixture()
def work_copy(latex_map, tmp_path):
    """A fresh copy of the LaTeX work folder for tests that write findings."""
    _, work = latex_map
    dst = tmp_path / "paper-check-work"
    shutil.copytree(work, dst)
    return dst
