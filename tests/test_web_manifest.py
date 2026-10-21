"""The web app is installable to the home screen (ADR-0006 rule 1).

Chrome offers to install only when the manifest names a standalone app with
192 and 512 pixel icons, and Android's adaptive icons need a maskable one.
These check web/public/manifest.webmanifest and that each icon file exists at
the size it claims.
"""

import json
import struct
from pathlib import Path

WEB_PUBLIC = Path(__file__).parents[1] / "web" / "public"


def _manifest() -> dict[str, object]:
    manifest: dict[str, object] = json.loads(
        (WEB_PUBLIC / "manifest.webmanifest").read_text()
    )
    return manifest


def _png_size(src: str) -> str:
    data = (WEB_PUBLIC / src.lstrip("/")).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{src} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return f"{width}x{height}"


def test_manifest_is_a_standalone_app_from_the_root() -> None:
    manifest = _manifest()
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    icons = manifest["icons"]
    assert isinstance(icons, list)
    purposes = {f"{icon['sizes']} {icon['purpose']}" for icon in icons}
    assert {"192x192 any", "512x512 any", "512x512 maskable"} <= purposes


def test_every_icon_exists_at_the_size_it_claims() -> None:
    icons = _manifest()["icons"]
    assert isinstance(icons, list)
    for icon in icons:
        assert icon["type"] == "image/png"
        assert _png_size(icon["src"]) == icon["sizes"]
    assert _png_size("/icons/apple-touch-icon.png") == "180x180"
