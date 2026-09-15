from ganjoor_bot.sharing import ganjoor_url_from_source_path, telegram_share_url


def test_ganjoor_url_from_source_path():
    assert (
        ganjoor_url_from_source_path("poets/hafez/ghazal/sh221.json")
        == "https://ganjoor.net/hafez/ghazal/sh221"
    )


def test_telegram_share_url_encodes_text():
    url = telegram_share_url(
        "https://ganjoor.net/hafez/ghazal/sh221",
        "حافظ — غزل شمارهٔ ۲۲۱",
    )
    assert url.startswith("https://t.me/share/url?")
    assert "ganjoor.net" in url
    assert "%D8%AD%D8%A7%D9%81%D8%B8" in url
