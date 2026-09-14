import base64
import io

import segno


def png_data_uri(url: str) -> str:
    qr = segno.make(url, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=8, border=4, dark="#000000", light="#ffffff")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def page_url(share_url: str, slug: str) -> str:
    return f"{share_url.rstrip('/')}/{slug}"
