"""打包/运行入口。

以「正常导入包」的方式调用 desk_buddy.main.main()，这样 main.py 里的相对
导入（from .app import App 等）能正确解析到父包——PyInstaller 直接把
src/desk_buddy/main.py 当顶层脚本跑时会报 "attempted relative import with
no known parent package"，本脚本规避了这个问题。
"""

import sys

from desk_buddy.main import main

if __name__ == "__main__":
    sys.exit(main())
