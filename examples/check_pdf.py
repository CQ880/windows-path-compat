import json
from importlib.metadata import version
from pathlib import Path
import sys

from docling_parse.pdf_parser import DoclingPdfParser


def main():
    path = Path(sys.argv[1]).resolve(strict=True)
    parser = DoclingPdfParser()
    try:
        doc = parser.load(path)
        pages = doc.number_of_pages()
        if pages != 1:
            raise ValueError(f"Expected one page, got {pages}")
    except Exception as error:
        print(json.dumps({"docling_parse": version("docling-parse"),
                          "error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps({"docling_parse": version("docling-parse"), "pages": pages}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
