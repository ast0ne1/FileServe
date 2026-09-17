import base64
import io

import segno


def png_bytes(url: str) -> bytes:
    qr = segno.make(url, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=8, border=4, dark="#000000", light="#ffffff")
    return buffer.getvalue()


def png_data_uri(url: str) -> str:
    encoded = base64.b64encode(png_bytes(url)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def page_url(share_url: str, path: str) -> str:
    clean = (path or "").lstrip("/")
    return f"{share_url.rstrip('/')}/{clean}"
