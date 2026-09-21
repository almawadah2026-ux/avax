"""
خادم ثابت للوحة المعاينة — بلا اعتماديات.

الاستخدام:
    python tools/serve_web.py --port 8787

⚠️ لا يُشغّل هذا الخادم تلقائياً أي دورة تداول، ولا يمنح أي كتابة:
   الواجهة تقرأ فقط عبر مفتاح publishable محميّ بـRLS.
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class Handler(SimpleHTTPRequestHandler):
    """خادم ثابت مع ترويسات صحيحة للعربية وJSON."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # أقل ضجيجاً
        sys.stderr.write("  · %s\n" % (fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser(description="خادم لوحة ديسك أفالانش")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if not (WEB / "index.html").exists():
        print(f"⛔ لا يوجد {WEB / 'index.html'}")
        return 1
    if not (WEB / "config.js").exists():
        print("⚠️ تنبيه: web/config.js غير موجود — انسخه من config.example.js")
        print("   اللوحة ستُظهر رسالة إعداد بدل البيانات (وهذا مقصود).")

    httpd = ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(WEB)))
    print("═" * 66)
    print("  🏔️  لوحة ديسك أفالانش")
    print("═" * 66)
    print(f"  الرابط: http://{args.host}:{args.port}/")
    print(f"  المجلد: {WEB}")
    print("  القراءة فقط — لا كتابة ولا تنفيذ (المادة 0.2)")
    print("═" * 66)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  أُوقف الخادم.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
