# tests/test_version.py
import re
from pathlib import Path

import desk_buddy

_PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_version_is_defined_and_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", desk_buddy.__version__)


def test_pyproject_reads_version_from_package_not_hardcoded():
    text = _PYPROJECT.read_text(encoding="utf-8")
    # 单一可信源：pyproject 动态读取包属性，而不是再写死一个版本字面量
    assert 'attr = "desk_buddy.__version__"' in text
    assert 'version = "' not in text  # [project] 下不应再有硬编码 version
