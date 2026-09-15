from ganjoor_bot.telegram_bot import (
    _poet_keyboard,
    _poets_keyboard,
    _search_results_keyboard,
    _works_keyboard,
    main_menu,
)


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_main_menu_contains_core_actions():
    callbacks = _callbacks(main_menu())
    assert {
        "menu:search",
        "menu:fortune",
        "menu:random",
        "menu:poets",
        "menu:bookmarks",
        "menu:help",
    } <= callbacks


def test_search_results_are_clickable_poems():
    markup = _search_results_keyboard(
        [
            {"poem_id": 221, "poet": "حافظ", "poem_title": "غزل شمارهٔ ۲۲۱"},
            {"poem_id": 555, "poet": "سعدی", "poem_title": "غزل شمارهٔ ۱"},
        ],
        include_fuzzy=True,
    )
    callbacks = _callbacks(markup)
    assert {"poem:221", "poem:555", "search:fuzzy", "menu:home"} <= callbacks


def test_poets_keyboard_has_navigation_and_poet_actions():
    markup = _poets_keyboard(
        {
            "items": [
                {"id": 1, "nickname": "حافظ", "name": "خواجه حافظ", "poem_count": 495},
                {"id": 2, "nickname": "سعدی", "name": "سعدی شیرازی", "poem_count": 700},
            ],
            "page": 1,
            "pages": 3,
            "has_prev": True,
            "has_next": True,
        }
    )
    callbacks = _callbacks(markup)
    assert {"poet:1", "poet:2", "poets:0", "poets:2", "menu:home"} <= callbacks


def test_poet_and_works_keyboards_use_compact_callbacks():
    poet_markup = _poet_keyboard(
        {"id": 1, "poem_count": 495},
        [{"id": 10, "title": "غزلیات"}, {"id": 11, "title": "قطعات"}],
    )
    assert {"cat:10", "cat:11", "pworks:1:0", "poets:0"} <= _callbacks(poet_markup)

    works_markup = _works_keyboard(
        {
            "items": [{"id": 100, "title": "غزل شمارهٔ ۱"}],
            "page": 0,
            "pages": 2,
            "has_prev": False,
            "has_next": True,
        },
        category_id=10,
    )
    callbacks = _callbacks(works_markup)
    assert {"poem:100", "cworks:10:1", "cat:10", "menu:home"} <= callbacks
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)
