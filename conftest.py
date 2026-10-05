"""
pytest 公共配置：确保在任何工作目录下都能 import 到 core。

运行方式（在项目根目录 CodeAgent/ 下）：
    python -m pytest -q
"""

import sys
from pathlib import Path

# 把仓库根目录（core/ 的父目录）加入 sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
