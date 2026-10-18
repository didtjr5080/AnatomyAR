import os
from pathlib import Path
from PySide6.QtGui import QFont,QFontDatabase


def configure_font(app):
    # Offscreen Qt does not enumerate Windows fonts, so load the OS font explicitly.
    if "Malgun Gothic" not in QFontDatabase.families():
        font_dir=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"
        for filename in ("malgun.ttf","malgunbd.ttf"):
            path=font_dir/filename
            if path.is_file(): QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Malgun Gothic",10))
