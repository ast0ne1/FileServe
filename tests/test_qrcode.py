from app.services.qrcode import page_url, png_bytes, png_data_uri


def test_png_data_uri_is_a_png():
    uri = png_data_uri("http://fileserve.local:8081/emergency-planner")
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > 200
    raw = png_bytes("http://fileserve.local:8081/emergency-planner")
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_page_url_joins_share_root_and_slug():
    assert page_url("http://fileserve.local:8081", "emergency-planner") == "http://fileserve.local:8081/emergency-planner"
    assert page_url("http://192.168.1.10:8081/", "travel") == "http://192.168.1.10:8081/travel"
