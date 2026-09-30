from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


source, output = map(Path, sys.argv[1:3])
with Image.open(source) as image:
    square = image.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    square.save(output, format="ICNS", append_images=[square])
