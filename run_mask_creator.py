#!/usr/bin/env python
"""Launch Mask Creator without installing the package.

Usage:  python run_mask_creator.py [image.h5]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mask_creator.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
