"""Entry point: ``python -m mask_creator [image.h5]``."""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("Mask Creator")

    from .main_window import MainWindow

    window = MainWindow(initial_path=argv[1] if len(argv) > 1 else None)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
