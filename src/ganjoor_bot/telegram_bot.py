from __future__ import annotations

import asyncio
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .browse import (
    format_poem,
    get_category,
    get_poem,
    get_poet,
    list_category_children,
    list_poems_by_poet,
    list_poems_in_category,
    list_poets,
    list_root_categories,
)
from .db import connect
from .fortune import format_fortune_text, get_hafez_fortune
from .search import search_verses, smart_search
from .sharing import poem_share_info, telegram_share_url
from .state import (
    add_bookmark,
    bookmark_counts,
    connect_state,
    create_collection,
    delete_collection,
    get_bookmark,
    get_collection,
    list_bookmarks,
    list_collections,
    move_bookmark,
    remove_bookmark,
    rename_collection,
    touch_user,
)


DB_ENV = "POETRY_DB"
STATE_DB_ENV = "BOT_STATE_DB"
TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
DEFAULT_DB = Path("data/poetry.sqlite")
DEFAULT_STATE_DB = Path("data/bot_state.sqlite")
POETS_PAGE_SIZE = 12
WORKS_PAGE_SIZE = 10
BOOKMARKS_PAGE_SIZE = 10


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔎 جست‌وجوی شعر", callback_data="menu:search"),
                InlineKeyboardButton("🔮 فال حافظ", callback_data="menu:fortune"),
            ],
            [
                InlineKeyboardButton("🎲 شعر تصادفی", callback_data="menu:random"),
                InlineKeyboardButton("📚 شاعران", callback_data="menu:poets"),
            ],
            [
                InlineKeyboardButton("⭐ ذخیره‌ها", callback_data="menu:bookmarks"),
                InlineKeyboardButton("ℹ️ راهنما", callback_data="menu:help"),
            ],
        ]
    )


def _db_path() -> Path:
    return Path(os.environ.get(DB_ENV, str(DEFAULT_DB)))


def _state_db_path() -> Path:
    return Path(os.environ.get(STATE_DB_ENV, str(DEFAULT_STATE_DB)))


def _open_db():
    path = _db_path()
    if not path.exists():
        raise FileNotFoundError(f"Poetry database not found: {path}")
    return connect(path)


def _open_state():
    return connect_state(_state_db_path())


def _remember_user(update: Update) -> None:
    user = update.effective_user
    if not user:
        return
    conn = _open_state()
    try:
        touch_user(
            conn,
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    finally:
        conn.close()


def _primary_search(query: str, limit: int = 5) -> tuple[str, list[dict[str, object]]]:
    conn = _open_db()
    try:
        exact = search_verses(conn, query, limit=limit, mode="exact")
        if exact:
            return "exact", [dict(row) for row in exact]
        all_rows = search_verses(conn, query, limit=limit, mode="all")
        if all_rows:
            return "all", [dict(row) for row in all_rows]
        return "none", []
    finally:
        conn.close()


def _fuzzy_search(query: str, limit: int = 5) -> list[dict[str, object]]:
    conn = _open_db()
    try:
        return smart_search(conn, query, limit=limit)
    finally:
        conn.close()


def _fortune_payload() -> tuple[dict[str, object], str]:
    conn = _open_db()
    try:
        fortune = get_hafez_fortune(conn)
        return fortune, format_fortune_text(fortune)
    finally:
        conn.close()


def _poets_page(page: int) -> dict[str, object]:
    conn = _open_db()
    try:
        return list_poets(conn, page=page, page_size=POETS_PAGE_SIZE)
    finally:
        conn.close()


def _poet_screen(poet_id: int) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    conn = _open_db()
    try:
        return get_poet(conn, poet_id), list_root_categories(conn, poet_id)
    finally:
        conn.close()


def _category_screen(category_id: int) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    conn = _open_db()
    try:
        return get_category(conn, category_id), list_category_children(conn, category_id)
    finally:
        conn.close()


def _category_works(category_id: int, page: int) -> dict[str, object]:
    conn = _open_db()
    try:
        return list_poems_in_category(conn, category_id, page=page, page_size=WORKS_PAGE_SIZE)
    finally:
        conn.close()


def _poet_works(poet_id: int, page: int) -> dict[str, object]:
    conn = _open_db()
    try:
        return list_poems_by_poet(conn, poet_id, page=page, page_size=WORKS_PAGE_SIZE)
    finally:
        conn.close()


def _full_poem(poem_id: int) -> dict[str, object] | None:
    conn = _open_db()
    try:
        return get_poem(conn, poem_id)
    finally:
        conn.close()


def _share_url(poem_id: int, *, fortune: bool = False) -> str | None:
    conn = _open_db()
    try:
        info = poem_share_info(conn, poem_id)
    finally:
        conn.close()
    if not info:
        return None
    prefix = "🔮 فال حافظ\n" if fortune else "📖 شعر فارسی\n"
    return telegram_share_url(info["url"], prefix + info["label"])


def _short_label(text: object, max_chars: int = 44) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= max_chars else value[: max_chars - 1] + "…"


def _format_results(rows: list[dict[str, object]], *, approximate: bool = False) -> str:
    if not rows:
        return "نتیجه‌ای پیدا نشد."
    blocks: list[str] = []
    for index, row in enumerate(rows, start=1):
        prefix = "≈ " if approximate or row.get("match_type") == "fuzzy" else ""
        poet = str(row.get("poet") or "")
        title = str(row.get("poem_title") or "")
        text = str(row.get("text") or "")
        similarity = row.get("similarity")
        score_text = ""
        if row.get("match_type") == "fuzzy" and isinstance(similarity, (int, float)):
            score_text = f" — شباهت {float(similarity):.0%}"
        blocks.append(f"{index}. {prefix}{poet} — {title}{score_text}\n{text}")
    return "\n\n".join(blocks)


def _search_results_keyboard(
    rows: list[dict[str, object]],
    *,
    include_fuzzy: bool,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    seen: set[int] = set()
    for index, row in enumerate(rows, start=1):
        poem_id = int(row["poem_id"])
        if poem_id in seen:
            continue
        seen.add(poem_id)
        label = f"📖 {index}. {_short_label(row.get('poet'), 16)} — {_short_label(row.get('poem_title'), 24)}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"poem:{poem_id}")])
    if include_fuzzy:
        buttons.append([InlineKeyboardButton("≈ جست‌وجوی تقریبی", callback_data="search:fuzzy")])
    buttons.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(buttons)


def _poem_actions_keyboard(
    poem_id: int,
    user_id: int,
    *,
    back_callback: str | None = None,
    fortune: bool = False,
) -> InlineKeyboardMarkup:
    state = _open_state()
    try:
        saved = get_bookmark(state, user_id, poem_id)
    finally:
        state.close()

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "✅ ذخیره شده" if saved else "⭐ ذخیره",
                callback_data=f"bm:toggle:{poem_id}",
            ),
            InlineKeyboardButton("📂 دسته‌بندی", callback_data=f"bm:assign:{poem_id}"),
        ]
    ]
    share = _share_url(poem_id, fortune=fortune)
    if share:
        rows.append([InlineKeyboardButton("📤 اشتراک‌گذاری", url=share)])
    if fortune:
        rows.append([InlineKeyboardButton("🔮 فال دوباره", callback_data="menu:fortune")])
    if back_callback:
        rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=back_callback)])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _poets_keyboard(page_data: dict[str, object]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in list(page_data.get("items") or []):
        name = _short_label(item.get("nickname") or item.get("name") or "شاعر", 28)
        rows.append([InlineKeyboardButton(f"{name} · {int(item.get('poem_count') or 0)} اثر", callback_data=f"poet:{int(item['id'])}")])
    page = int(page_data.get("page") or 0)
    nav: list[InlineKeyboardButton] = []
    if page_data.get("has_prev"):
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"poets:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{int(page_data.get('pages') or 1)}", callback_data="noop"))
    if page_data.get("has_next"):
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"poets:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _poet_keyboard(poet: dict[str, object], roots: list[dict[str, object]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for category in roots:
        rows.append([InlineKeyboardButton(f"📂 {_short_label(category.get('title'), 42)}", callback_data=f"cat:{int(category['id'])}")])
    rows.append([InlineKeyboardButton(f"📜 همهٔ آثار ({int(poet.get('poem_count') or 0)})", callback_data=f"pworks:{int(poet['id'])}:0")])
    rows.append([InlineKeyboardButton("⬅️ فهرست شاعران", callback_data="poets:0")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _category_keyboard(category: dict[str, object], children: list[dict[str, object]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for child in children:
        rows.append([InlineKeyboardButton(f"📂 {_short_label(child.get('title'), 42)}", callback_data=f"cat:{int(child['id'])}")])
    direct_count = int(category.get("direct_poem_count") or 0)
    if direct_count:
        rows.append([InlineKeyboardButton(f"📜 آثار این بخش ({direct_count})", callback_data=f"cworks:{int(category['id'])}:0")])
    parent_id = category.get("parent_id")
    if parent_id is not None:
        rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"cat:{int(parent_id)}")])
    else:
        rows.append([InlineKeyboardButton("⬅️ شاعر", callback_data=f"poet:{int(category['poet_id'])}")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _works_keyboard(page_data: dict[str, object], *, category_id: int | None = None, poet_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in list(page_data.get("items") or []):
        title = item.get("title") or f"اثر {int(item['id'])}"
        rows.append([InlineKeyboardButton(f"📄 {_short_label(title, 43)}", callback_data=f"poem:{int(item['id'])}")])
    page = int(page_data.get("page") or 0)
    prefix = f"cworks:{category_id}" if category_id is not None else f"pworks:{poet_id}"
    nav: list[InlineKeyboardButton] = []
    if page_data.get("has_prev"):
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"{prefix}:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{int(page_data.get('pages') or 1)}", callback_data="noop"))
    if page_data.get("has_next"):
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"{prefix}:{page + 1}"))
    rows.append(nav)
    if category_id is not None:
        rows.append([InlineKeyboardButton("⬅️ بازگشت به مجموعه", callback_data=f"cat:{category_id}")])
    elif poet_id is not None:
        rows.append([InlineKeyboardButton("⬅️ بازگشت به شاعر", callback_data=f"poet:{poet_id}")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _bookmark_menu(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    conn = _open_state()
    try:
        counts = bookmark_counts(conn, user_id)
        collections = list_collections(conn, user_id)
    finally:
        conn.close()
    text = f"⭐ ذخیره‌ها\nهمه: {counts['total']}\nبدون دسته: {counts['uncategorized']}"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(f"⭐ همهٔ ذخیره‌ها ({counts['total']})", callback_data="bml:all:0")]
    ]
    if counts["uncategorized"]:
        rows.append([InlineKeyboardButton(f"📄 بدون دسته ({counts['uncategorized']})", callback_data="bml:none:0")])
    for collection in collections:
        rows.append([InlineKeyboardButton(f"📁 {_short_label(collection['name'], 28)} ({int(collection['bookmark_count'])})", callback_data=f"bmc:{int(collection['id'])}:0")])
    rows.append([InlineKeyboardButton("➕ دستهٔ جدید", callback_data="col:new")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return text, InlineKeyboardMarkup(rows)


def _bookmark_page(user_id: int, collection: str | int, page: int) -> tuple[dict[str, object], dict[int, dict[str, object]]]:
    state = _open_state()
    try:
        page_data = list_bookmarks(state, user_id, collection=collection, page=page, page_size=BOOKMARKS_PAGE_SIZE)
    finally:
        state.close()
    ids = [int(item["poem_id"]) for item in page_data["items"]]
    summaries: dict[int, dict[str, object]] = {}
    if ids:
        db = _open_db()
        try:
            placeholders = ",".join("?" for _ in ids)
            for row in db.execute(
                f"""
                SELECT p.id, p.title, po.nickname AS poet
                FROM poems p JOIN poets po ON po.id = p.poet_id
                WHERE p.id IN ({placeholders})
                """,
                ids,
            ):
                summaries[int(row["id"])] = dict(row)
        finally:
            db.close()
    return page_data, summaries


def _bookmark_list_keyboard(user_id: int, collection: str | int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    page_data, summaries = _bookmark_page(user_id, collection, page)
    rows: list[list[InlineKeyboardButton]] = []
    for item in page_data["items"]:
        poem_id = int(item["poem_id"])
        summary = summaries.get(poem_id, {})
        label = f"📖 {_short_label(summary.get('poet'), 15)} — {_short_label(summary.get('title') or poem_id, 26)}"
        rows.append([InlineKeyboardButton(label, callback_data=f"poem:{poem_id}")])
    current = int(page_data["page"])
    nav: list[InlineKeyboardButton] = []
    prefix = f"bmc:{collection}" if isinstance(collection, int) else f"bml:{collection}"
    if page_data.get("has_prev"):
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"{prefix}:{current - 1}"))
    nav.append(InlineKeyboardButton(f"{current + 1}/{int(page_data['pages'])}", callback_data="noop"))
    if page_data.get("has_next"):
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"{prefix}:{current + 1}"))
    if nav:
        rows.append(nav)
    title = "همهٔ ذخیره‌ها" if collection == "all" else "بدون دسته"
    if isinstance(collection, int):
        state = _open_state()
        try:
            info = get_collection(state, user_id, collection)
        finally:
            state.close()
        title = str((info or {}).get("name") or "دسته")
        rows.append([
            InlineKeyboardButton("✏️ تغییر نام", callback_data=f"col:rename:{collection}"),
            InlineKeyboardButton("🗑 حذف دسته", callback_data=f"col:delete:{collection}"),
        ])
    rows.append([InlineKeyboardButton("⬅️ ذخیره‌ها", callback_data="menu:bookmarks")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    text = f"⭐ {title}\n{int(page_data['total'])} مورد ذخیره‌شده"
    return text, InlineKeyboardMarkup(rows)


def _assign_keyboard(user_id: int, poem_id: int) -> InlineKeyboardMarkup:
    conn = _open_state()
    try:
        collections = list_collections(conn, user_id)
    finally:
        conn.close()
    rows = [[InlineKeyboardButton("📄 بدون دسته", callback_data=f"bmm:{poem_id}:none")]]
    for collection in collections:
        rows.append([InlineKeyboardButton(f"📁 {_short_label(collection['name'], 32)}", callback_data=f"bmm:{poem_id}:{int(collection['id'])}")])
    rows.append([InlineKeyboardButton("➕ دستهٔ جدید", callback_data=f"col:newfor:{poem_id}")])
    rows.append([InlineKeyboardButton("📖 بازگشت به شعر", callback_data=f"poem:{poem_id}")])
    return InlineKeyboardMarkup(rows)


async def _send_long(update_or_message, text: str, reply_markup=None) -> None:
    message = getattr(update_or_message, "message", update_or_message)
    if len(text) <= 3900:
        await message.reply_text(text, reply_markup=reply_markup)
        return
    paragraphs = text.split("\n")
    chunk = ""
    chunks: list[str] = []
    for paragraph in paragraphs:
        candidate = f"{chunk}\n{paragraph}" if chunk else paragraph
        if len(candidate) > 3900 and chunk:
            chunks.append(chunk)
            chunk = paragraph
        else:
            chunk = candidate
    if chunk:
        chunks.append(chunk)
    for index, part in enumerate(chunks):
        await message.reply_text(part, reply_markup=reply_markup if index == len(chunks) - 1 else None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _remember_user(update)
    context.user_data.clear()
    await update.effective_message.reply_text(
        "به جست‌وجوی شعر فارسی خوش آمدید. یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=main_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🔎 بخشی از شعر را بفرستید تا در متن اصلی آثار جست‌وجو شود.\n"
        "📖 روی دکمهٔ هر نتیجه بزنید تا متن کامل اثر باز شود.\n"
        "🔮 فال حافظ یک غزل کامل و تصادفی است.\n"
        "⭐ شعرها و فال‌ها را ذخیره و در دسته‌های شخصی مرتب کنید.\n"
        "📤 از صفحهٔ کامل هر اثر می‌توانید آن را با لینک رسمی گنجور به اشتراک بگذارید.",
        reply_markup=main_menu(),
    )


async def fortune_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _remember_user(update)
    fortune, text = await asyncio.to_thread(_fortune_payload)
    user_id = update.effective_user.id
    await _send_long(update.effective_message, text, reply_markup=_poem_actions_keyboard(int(fortune["poem_id"]), user_id, fortune=True))


async def poets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page_data = await asyncio.to_thread(_poets_page, 0)
    await update.effective_message.reply_text(
        f"📚 شاعران — {int(page_data.get('total') or 0)} شاعر\nیک شاعر را انتخاب کنید:",
        reply_markup=_poets_keyboard(page_data),
    )


async def bookmarks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _remember_user(update)
    text, keyboard = await asyncio.to_thread(_bookmark_menu, update.effective_user.id)
    await update.effective_message.reply_text(text, reply_markup=keyboard)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        context.user_data["awaiting_search"] = True
        await update.effective_message.reply_text("بخشی از شعر یا عبارتی را که به یاد دارید بفرستید.")
        return
    await _handle_search_text(update, context, query)


async def _handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    context.user_data["awaiting_search"] = False
    context.user_data["last_query"] = query
    mode, rows = await asyncio.to_thread(_primary_search, query)
    if rows:
        label = "نتیجهٔ دقیق" if mode == "exact" else "نتایج دارای همهٔ واژه‌ها"
        await update.effective_message.reply_text(
            f"{label}:\n\n{_format_results(rows)}",
            reply_markup=_search_results_keyboard(rows, include_fuzzy=True),
        )
        return
    await update.effective_message.reply_text(
        "تطبیق مستقیم پیدا نشد. می‌توانید جست‌وجوی تقریبی را امتحان کنید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("≈ جست‌وجوی تقریبی", callback_data="search:fuzzy")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")],
        ]),
    )


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    user_id = update.effective_user.id

    pending_new = context.user_data.pop("awaiting_collection_name", None)
    if pending_new is not None:
        state = _open_state()
        try:
            try:
                collection_id = create_collection(state, user_id, text)
            except Exception as exc:
                await update.effective_message.reply_text(f"این نام قابل استفاده نیست: {exc}")
                return
            poem_id = context.user_data.pop("collection_for_poem", None)
            if poem_id is not None:
                add_bookmark(state, user_id, int(poem_id), collection_id=collection_id)
        finally:
            state.close()
        if poem_id is not None:
            await update.effective_message.reply_text("دسته ساخته شد و شعر داخل آن قرار گرفت.", reply_markup=_poem_actions_keyboard(int(poem_id), user_id))
        else:
            menu_text, keyboard = _bookmark_menu(user_id)
            await update.effective_message.reply_text("دستهٔ جدید ساخته شد.\n\n" + menu_text, reply_markup=keyboard)
        return

    rename_id = context.user_data.pop("awaiting_collection_rename", None)
    if rename_id is not None:
        state = _open_state()
        try:
            try:
                ok = rename_collection(state, user_id, int(rename_id), text)
            except Exception as exc:
                await update.effective_message.reply_text(f"تغییر نام انجام نشد: {exc}")
                return
        finally:
            state.close()
        await update.effective_message.reply_text("نام دسته تغییر کرد." if ok else "دسته پیدا نشد.")
        menu_text, keyboard = _bookmark_menu(user_id)
        await update.effective_message.reply_text(menu_text, reply_markup=keyboard)
        return

    await _handle_search_text(update, context, text)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user_id = update.effective_user.id
    _remember_user(update)

    if data == "noop":
        return
    if data == "menu:home":
        context.user_data.clear()
        await query.message.reply_text("منوی اصلی:", reply_markup=main_menu())
        return
    if data == "menu:search":
        context.user_data["awaiting_search"] = True
        await query.message.reply_text("بخشی از شعر یا عبارتی را که به یاد دارید بفرستید.")
        return
    if data == "menu:fortune":
        fortune, text = await asyncio.to_thread(_fortune_payload)
        await _send_long(query.message, text, reply_markup=_poem_actions_keyboard(int(fortune["poem_id"]), user_id, fortune=True))
        return
    if data == "menu:poets":
        page_data = await asyncio.to_thread(_poets_page, 0)
        await query.message.reply_text(f"📚 شاعران — {int(page_data.get('total') or 0)} شاعر\nیک شاعر را انتخاب کنید:", reply_markup=_poets_keyboard(page_data))
        return
    if data == "menu:bookmarks":
        text, keyboard = await asyncio.to_thread(_bookmark_menu, user_id)
        await query.message.reply_text(text, reply_markup=keyboard)
        return
    if data == "menu:random":
        await query.message.reply_text("شعر تصادفی در مرحلهٔ بعد فعال می‌شود.", reply_markup=main_menu())
        return
    if data == "menu:help":
        await query.message.reply_text(
            "🔎 جست‌وجو: بخشی از شعر را بفرستید.\n"
            "📖 دکمهٔ زیر هر نتیجه، شعر کامل را باز می‌کند.\n"
            "🔮 فال حافظ: یک غزل کامل و تصادفی.\n"
            "📚 شاعران: مرور مجموعه‌ها و آثار.\n"
            "⭐ ذخیره‌ها: ساخت دسته، جابه‌جایی و مدیریت شعرهای ذخیره‌شده.\n"
            "📤 اشتراک: ارسال لینک رسمی اثر در Telegram.",
            reply_markup=main_menu(),
        )
        return

    if data.startswith("poets:"):
        page = int(data.split(":", 1)[1])
        page_data = await asyncio.to_thread(_poets_page, page)
        await query.message.reply_text(f"📚 شاعران — صفحه {int(page_data['page']) + 1} از {int(page_data['pages'])}", reply_markup=_poets_keyboard(page_data))
        return
    if data.startswith("poet:"):
        poet_id = int(data.split(":", 1)[1])
        poet, roots = await asyncio.to_thread(_poet_screen, poet_id)
        if not poet:
            await query.message.reply_text("شاعر پیدا نشد.", reply_markup=main_menu())
            return
        name = poet.get("nickname") or poet.get("name") or "شاعر"
        description = " ".join(str(poet.get("description") or "").split())
        if len(description) > 900:
            description = description[:899] + "…"
        text = f"📚 {name}\nتعداد آثار: {int(poet.get('poem_count') or 0)}"
        if description:
            text += f"\n\n{description}"
        await query.message.reply_text(text, reply_markup=_poet_keyboard(poet, roots))
        return
    if data.startswith("cat:"):
        category_id = int(data.split(":", 1)[1])
        category, children = await asyncio.to_thread(_category_screen, category_id)
        if not category:
            await query.message.reply_text("این مجموعه پیدا نشد.", reply_markup=main_menu())
            return
        details = [f"📂 {category.get('title') or 'مجموعه'}"]
        if int(category.get("child_count") or 0):
            details.append(f"زیرمجموعه‌ها: {int(category['child_count'])}")
        if int(category.get("direct_poem_count") or 0):
            details.append(f"آثار مستقیم: {int(category['direct_poem_count'])}")
        await query.message.reply_text("\n".join(details), reply_markup=_category_keyboard(category, children))
        return
    if data.startswith("cworks:"):
        _, category_text, page_text = data.split(":", 2)
        category_id = int(category_text)
        page_data = await asyncio.to_thread(_category_works, category_id, int(page_text))
        category, _ = await asyncio.to_thread(_category_screen, category_id)
        title = (category or {}).get("title") or "آثار"
        await query.message.reply_text(f"📜 {title}\nصفحه {int(page_data['page']) + 1} از {int(page_data['pages'])}", reply_markup=_works_keyboard(page_data, category_id=category_id))
        return
    if data.startswith("pworks:"):
        _, poet_text, page_text = data.split(":", 2)
        poet_id = int(poet_text)
        page_data = await asyncio.to_thread(_poet_works, poet_id, int(page_text))
        poet, _ = await asyncio.to_thread(_poet_screen, poet_id)
        name = (poet or {}).get("nickname") or (poet or {}).get("name") or "شاعر"
        await query.message.reply_text(f"📜 همهٔ آثار {name}\nصفحه {int(page_data['page']) + 1} از {int(page_data['pages'])}", reply_markup=_works_keyboard(page_data, poet_id=poet_id))
        return

    if data.startswith("poem:"):
        poem_id = int(data.split(":", 1)[1])
        poem = await asyncio.to_thread(_full_poem, poem_id)
        if not poem:
            await query.message.reply_text("اثر پیدا نشد.", reply_markup=main_menu())
            return
        back = f"cat:{int(poem['category_id'])}" if poem.get("category_id") is not None else f"poet:{int(poem['poet_id'])}"
        await _send_long(query.message, format_poem(poem), reply_markup=_poem_actions_keyboard(poem_id, user_id, back_callback=back))
        return

    if data == "search:fuzzy":
        last_query = str(context.user_data.get("last_query") or "").strip()
        if not last_query:
            await query.message.reply_text("ابتدا یک عبارت برای جست‌وجو بفرستید.")
            return
        status = await query.message.reply_text("در حال جست‌وجوی تقریبی…")
        rows = await asyncio.to_thread(_fuzzy_search, last_query)
        await status.edit_text(
            "نتایج تقریبی:\n\n" + _format_results(rows, approximate=True),
            reply_markup=_search_results_keyboard(rows, include_fuzzy=False),
        )
        return

    if data.startswith("bm:toggle:"):
        poem_id = int(data.rsplit(":", 1)[1])
        state = _open_state()
        try:
            existing = get_bookmark(state, user_id, poem_id)
            if existing:
                remove_bookmark(state, user_id, poem_id)
                await query.answer("از ذخیره‌ها حذف شد", show_alert=False)
                await query.message.reply_text("از ذخیره‌ها حذف شد.", reply_markup=_poem_actions_keyboard(poem_id, user_id))
            else:
                add_bookmark(state, user_id, poem_id)
                await query.answer("ذخیره شد", show_alert=False)
                await query.message.reply_text("⭐ ذخیره شد. اگر خواستید آن را دسته‌بندی کنید:", reply_markup=_assign_keyboard(user_id, poem_id))
        finally:
            state.close()
        return
    if data.startswith("bm:assign:"):
        poem_id = int(data.rsplit(":", 1)[1])
        state = _open_state()
        try:
            add_bookmark(state, user_id, poem_id)
        finally:
            state.close()
        await query.message.reply_text("این شعر را در کدام دسته قرار بدهم؟", reply_markup=_assign_keyboard(user_id, poem_id))
        return
    if data.startswith("bmm:"):
        _, poem_text, collection_text = data.split(":", 2)
        poem_id = int(poem_text)
        collection_id = None if collection_text == "none" else int(collection_text)
        state = _open_state()
        try:
            add_bookmark(state, user_id, poem_id)
            ok = move_bookmark(state, user_id, poem_id, collection_id)
        finally:
            state.close()
        await query.message.reply_text("دسته‌بندی ذخیره شد." if ok else "دسته پیدا نشد.", reply_markup=_poem_actions_keyboard(poem_id, user_id))
        return

    if data.startswith("bml:"):
        _, filter_name, page_text = data.split(":", 2)
        text, keyboard = await asyncio.to_thread(_bookmark_list_keyboard, user_id, filter_name, int(page_text))
        await query.message.reply_text(text, reply_markup=keyboard)
        return
    if data.startswith("bmc:"):
        _, collection_text, page_text = data.split(":", 2)
        text, keyboard = await asyncio.to_thread(_bookmark_list_keyboard, user_id, int(collection_text), int(page_text))
        await query.message.reply_text(text, reply_markup=keyboard)
        return

    if data == "col:new":
        context.user_data["awaiting_collection_name"] = True
        context.user_data.pop("collection_for_poem", None)
        await query.message.reply_text("نام دستهٔ جدید را بفرستید:")
        return
    if data.startswith("col:newfor:"):
        poem_id = int(data.rsplit(":", 1)[1])
        context.user_data["awaiting_collection_name"] = True
        context.user_data["collection_for_poem"] = poem_id
        await query.message.reply_text("نام دستهٔ جدید را بفرستید؛ این شعر خودکار داخل آن قرار می‌گیرد:")
        return
    if data.startswith("col:rename:"):
        collection_id = int(data.rsplit(":", 1)[1])
        context.user_data["awaiting_collection_rename"] = collection_id
        await query.message.reply_text("نام جدید دسته را بفرستید:")
        return
    if data.startswith("col:delete:"):
        collection_id = int(data.rsplit(":", 1)[1])
        state = _open_state()
        try:
            info = get_collection(state, user_id, collection_id)
        finally:
            state.close()
        if not info:
            await query.message.reply_text("دسته پیدا نشد.")
            return
        await query.message.reply_text(
            f"دستهٔ «{info['name']}» حذف شود؟ شعرهای داخل آن پاک نمی‌شوند و به بدون دسته منتقل می‌شوند.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 بله، حذف شود", callback_data=f"col:confirm:{collection_id}")],
                [InlineKeyboardButton("لغو", callback_data="menu:bookmarks")],
            ]),
        )
        return
    if data.startswith("col:confirm:"):
        collection_id = int(data.rsplit(":", 1)[1])
        state = _open_state()
        try:
            ok = delete_collection(state, user_id, collection_id)
        finally:
            state.close()
        text, keyboard = _bookmark_menu(user_id)
        await query.message.reply_text(("دسته حذف شد.\n\n" if ok else "دسته پیدا نشد.\n\n") + text, reply_markup=keyboard)
        return


def build_application(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("fal", fortune_command))
    app.add_handler(CommandHandler("fortune", fortune_command))
    app.add_handler(CommandHandler("poets", poets_command))
    app.add_handler(CommandHandler("bookmarks", bookmarks_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    return app


def main() -> None:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(f"Missing {TOKEN_ENV}. Store the Telegram bot token in the VPS environment, not in Git.")
    db_path = _db_path()
    if not db_path.exists():
        raise SystemExit(f"Poetry database not found: {db_path}")
    state = _open_state()
    state.close()
    build_application(token).run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
