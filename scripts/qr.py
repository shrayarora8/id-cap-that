"""Make a QR code for the demo URL.

    python scripts/qr.py https://id-cap-that.onrender.com
    python scripts/qr.py --tunnel          # read it from the running tunnel

Writes demo/qr.png, big enough to fill a slide, plus demo/qr.txt for a
terminal. Pure standard library apart from qrcode, so it works offline.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "demo"


def tunnel_url() -> str | None:
    """Find the current Cloudflare quick-tunnel URL from its log."""
    for log in (Path("/tmp/tunnel.log"), ROOT / "tunnel.log"):
        if log.exists():
            found = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log.read_text())
            if found:
                return found[-1]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="the URL to encode")
    parser.add_argument("--tunnel", action="store_true", help="use the running tunnel")
    args = parser.parse_args()

    url = args.url or (tunnel_url() if args.tunnel else None)
    if not url:
        print("Give a URL, or --tunnel with a tunnel running.")
        return 1

    try:
        import qrcode
    except ImportError:
        print("pip install qrcode[pil]")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    # High error correction: a QR on a slide gets photographed at an angle,
    # in bad light, from the back of a room.
    qr = qrcode.QRCode(box_size=20, border=3,
                       error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(OUT / "qr.png")

    ascii_qr = qrcode.QRCode(border=1)
    ascii_qr.add_data(url)
    import io

    sink = io.StringIO()
    ascii_qr.print_ascii(out=sink)
    (OUT / "qr.txt").write_text(sink.getvalue())

    print(f"{url}\n  -> demo/qr.png  (slide-sized)\n  -> demo/qr.txt  (terminal)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
