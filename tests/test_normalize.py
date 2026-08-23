from ganjoor_bot.normalize import normalize_persian


def test_arabic_forms_normalize():
    assert normalize_persian("مي آيد") == "می اید"
    assert normalize_persian("می‌آید") == "میاید"


def test_diacritics_and_whitespace_normalize():
    assert normalize_persian("  عِشق\n  آسان  ") == "عشق اسان"
