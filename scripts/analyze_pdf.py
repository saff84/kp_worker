"""Quick PDF diagnostics (stdlib only). Usage: python scripts/analyze_pdf.py <path>"""
import re
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1])
    data = path.read_bytes()
    print("size_bytes:", len(data))
    for marker in (b"/Font", b"/Image", b"/Type/Page", b"FlateDecode", b"JBIG2", b"DCTDecode"):
        print(f"  {marker.decode()}: {data.count(marker)}")
    # PDF text in parentheses (literal strings)
    strings = re.findall(rb"\(([^\)]{4,200})\)", data)
    print("literal_strings:", len(strings))
    for s in strings[:30]:
        try:
            print(" ", s.decode("utf-8", errors="replace")[:120])
        except Exception:
            print(" ", s[:80])
    # UTF-16BE chunks sometimes used in PDFs
    cyr = re.findall(rb"[\xd0\xd1][\x80-\xbf]{2,40}", data)
    print("cyrillic_byte_runs:", len(cyr))


if __name__ == "__main__":
    main()
