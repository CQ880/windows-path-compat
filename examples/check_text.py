"""Small probe for the quick start and the Action smoke workflow."""

from pathlib import Path
import sys


path = Path(sys.argv[1])
if "--fail-on-unicode" in sys.argv[2:] and not str(path).isascii():
    sys.exit("Deliberate failure on a Unicode path")
if path.read_text(encoding="utf-8").strip() != "Windows path sample":
    sys.exit("Unexpected sample contents")
