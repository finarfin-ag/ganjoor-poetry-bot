from ganjoor_bot.telegram_bot import main_menu


def test_main_menu_contains_core_actions():
    markup = main_menu()
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }

    assert {
        "menu:search",
        "menu:fortune",
        "menu:random",
        "menu:poets",
        "menu:bookmarks",
        "menu:help",
    } <= callbacks
