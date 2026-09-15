from ganjoor_bot.state import (
    add_bookmark,
    bookmark_counts,
    connect_state,
    create_collection,
    delete_collection,
    get_bookmark,
    list_bookmarks,
    list_collections,
    move_bookmark,
    remove_bookmark,
    rename_collection,
    touch_user,
)


def test_bookmark_collections_round_trip(tmp_path):
    conn = connect_state(tmp_path / "state.sqlite")
    touch_user(conn, 100, username="reader", first_name="Reader")

    fav = create_collection(conn, 100, "علاقه‌مندی‌ها")
    later = create_collection(conn, 100, "برای بعد")
    assert [item["name"] for item in list_collections(conn, 100)] == ["برای بعد", "علاقه‌مندی‌ها"]

    bookmark_id, created = add_bookmark(conn, 100, 1234)
    assert bookmark_id > 0 and created
    assert bookmark_counts(conn, 100) == {"total": 1, "uncategorized": 1}

    assert move_bookmark(conn, 100, 1234, fav)
    item = get_bookmark(conn, 100, 1234)
    assert item and item["collection_name"] == "علاقه‌مندی‌ها"

    assert rename_collection(conn, 100, later, "بعداً بخوانم")
    assert delete_collection(conn, 100, fav)
    item = get_bookmark(conn, 100, 1234)
    assert item and item["collection_id"] is None

    page = list_bookmarks(conn, 100, collection="none")
    assert page["total"] == 1
    assert page["items"][0]["poem_id"] == 1234

    assert remove_bookmark(conn, 100, 1234)
    assert bookmark_counts(conn, 100)["total"] == 0
