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


DB_ENV = "POETRY_DB"
TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
DEFAULT_DB = Path("data/poetry.sqlite")
POETS_PAGE_SIZE = 12
WORKS_PAGE_SIZE = 10


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


def _open_db():
    path = _db_path()
    if not path.exists():
        raise FileNotFoundError(f"Poetry database not found: {path}")
    return connect(path)


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


def _fortune_text() -> str:
    conn = _open_db()
    try:
        fortune = get_hafez_fortune(conn)
        return format_fortune_text(fortune)
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
        return list_poems_in_category(
            conn,
            category_id,
            page=page,
            page_size=WORKS_PAGE_SIZE,
        )
    finally:
        conn.close()


def _poet_works(poet_id: int, page: int) -> dict[str, object]:
    conn = _open_db()
    try:
        return list_poems_by_poet(
            conn,
            poet_id,
            page=page,
            page_size=WORKS_PAGE_SIZE,
        )
    finally:
        conn.close()


def _full_poem(poem_id: int) -> dict[str, object] | None:
    conn = _open_db()
    try:
        return get_poem(conn, poem_id)
    finally:
        conn.close()


def _short_label(text: object, max_chars: int = 44) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


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


def _poets_keyboard(page_data: dict[str, object]) -> InlineKeyboardMarkup:
    items = list(page_data.get("items") or [])
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        name = _short_label(item.get("nickname") or item.get("name") or "شاعر", 28)
        count = int(item.get("poem_count") or 0)
        rows.append(
            [InlineKeyboardButton(f"{name} · {count} اثر", callback_data=f"poet:{int(item['id'])}")]
        )

    nav: list[InlineKeyboardButton] = []
    page = int(page_data.get("page") or 0)
    if page_data.get("has_prev"):
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"poets:{page - 1}"))
    nav.append(
        InlineKeyboardButton(
            f"{page + 1}/{int(page_data.get('pages') or 1)}",
            callback_data="noop",
        )
    )
    if page_data.get("has_next"):
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"poets:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _poet_keyboard(poet: dict[str, object], roots: list[dict[str, object]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for category in roots:
        rows.append(
            [
                InlineKeyboardButton(
                    f"📂 {_short_label(category.get('title'), 42)}",
                    callback_data=f"cat:{int(category['id'])}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                f"📜 همهٔ آثار ({int(poet.get('poem_count') or 0)})",
                callback_data=f"pworks:{int(poet['id'])}:0",
            )
        ]
    )
    rows.append([InlineKeyboardButton("⬅️ فهرست شاعران", callback_data="poets:0")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _category_keyboard(
    category: dict[str, object],
    children: list[dict[str, object]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for child in children:
        rows.append(
            [
                InlineKeyboardButton(
                    f"📂 {_short_label(child.get('title'), 42)}",
                    callback_data=f"cat:{int(child['id'])}",
                )
            ]
        )

    direct_count = int(category.get("direct_poem_count") or 0)
    if direct_count:
        rows.append(
            [
                InlineKeyboardButton(
                    f"📜 آثار این بخش ({direct_count})",
                    callback_data=f"cworks:{int(category['id'])}:0",
                )
            ]
        )

    parent_id = category.get("parent_id")
    if parent_id is not None:
        rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"cat:{int(parent_id)}")])
    else:
        rows.append([InlineKeyboardButton("⬅️ شاعر", callback_data=f"poet:{int(category['poet_id'])}")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _works_keyboard(
    page_data: dict[str, object],
    *,
    category_id: int | None = None,
    poet_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in list(page_data.get("items") or []):
        rows.append(
            [
                InlineKeyboardButton(
                    f"📄 {_short_label(item.get('title') or f'اثر {item[\"id\"]}', 43)}",
                    callback_data=f"poem:{int(item['id'])}",
                )
            ]
        )

    page = int(page_data.get("page") or 0)
    nav: list[InlineKeyboardButton] = []
    prefix = f"cworks:{category_id}" if category_id is not None else f"pworks:{poet_id}"
    if page_data.get("has_prev"):
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"{prefix}:{page - 1}"))
    nav.append(
        InlineKeyboardButton(
            f"{page + 1}/{int(page_data.get('pages') or 1)}",
            callback_data="noop",
        )
    )
    if page_data.get("has_next"):
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"{prefix}:{page + 1}"))
    rows.append(nav)

    if category_id is not None:
        rows.append([InlineKeyboardButton("⬅️ بازگشت به مجموعه", callback_data=f"cat:{category_id}")])
    elif poet_id is not None:
        rows.append([InlineKeyboardButton("⬅️ بازگشت به شاعر", callback_data=f"poet:{poet_id}")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
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
        await message.reply_text(
            part,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_search"] = False
    await update.effective_message.reply_text(
        "به جست‌وجوی شعر فارسی خوش آمدید. یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=main_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "می‌توانید بخشی از یک شعر را بفرستید تا در متن اصلی آثار جست‌وجو شود.\n\n"
        "فال حافظ یک غزل کامل و تصادفی از متن محلی گنجور برمی‌گرداند.\n"
        "از بخش شاعران می‌توانید شاعر، مجموعه، زیرمجموعه و متن کامل آثار را مرور کنید.\n"
        "نتایج تقریبی با علامت ≈ مشخص می‌شوند و از متن اصلی جدا از توضیحات هوش مصنوعی جست‌وجو می‌شوند.",
        reply_markup=main_menu(),
    )


async def fortune_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await asyncio.to_thread(_fortune_text)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔮 فال دوباره", callback_data="menu:fortune")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")],
        ]
    )
    await _send_long(update.effective_message, text, reply_markup=keyboard)


async def poets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page_data = await asyncio.to_thread(_poets_page, 0)
    await update.effective_message.reply_text(
        f"📚 شاعران — {int(page_data.get('total') or 0)} شاعر\nیک شاعر را انتخاب کنید:",
        reply_markup=_poets_keyboard(page_data),
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        context.user_data["awaiting_search"] = True
        await update.effective_message.reply_text(
            "بخشی از شعر یا عبارتی را که به یاد دارید بفرستید."
        )
        return
    await _handle_search_text(update, context, query)


async def _handle_search_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
) -> None:
    context.user_data["awaiting_search"] = False
    context.user_data["last_query"] = query

    mode, rows = await asyncio.to_thread(_primary_search, query)
    if rows:
        label = "نتیجهٔ دقیق" if mode == "exact" else "نتایج دارای همهٔ واژه‌ها"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("≈ جست‌وجوی تقریبی", callback_data="search:fuzzy")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")],
            ]
        )
        await update.effective_message.reply_text(
            f"{label}:\n\n{_format_results(rows)}",
            reply_markup=keyboard,
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("≈ جست‌وجوی تقریبی", callback_data="search:fuzzy")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")],
        ]
    )
    await update.effective_message.reply_text(
        "تطبیق مستقیم پیدا نشد. می‌توانید جست‌وجوی تقریبی را امتحان کنید.",
        reply_markup=keyboard,
    )


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    await _handle_search_text(update, context, text)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "noop":
        return

    if data == "menu:home":
        context.user_data["awaiting_search"] = False
        await query.message.reply_text("منوی اصلی:", reply_markup=main_menu())
        return

    if data == "menu:search":
        context.user_data["awaiting_search"] = True
        await query.message.reply_text("بخشی از شعر یا عبارتی را که به یاد دارید بفرستید.")
        return

    if data == "menu:fortune":
        text = await asyncio.to_thread(_fortune_text)
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔮 فال دوباره", callback_data="menu:fortune")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")],
            ]
        )
        await _send_long(query.message, text, reply_markup=keyboard)
        return

    if data == "menu:poets":
        page_data = await asyncio.to_thread(_poets_page, 0)
        await query.message.reply_text(
            f"📚 شاعران — {int(page_data.get('total') or 0)} شاعر\nیک شاعر را انتخاب کنید:",
            reply_markup=_poets_keyboard(page_data),
        )
        return

    if data.startswith("poets:"):
        page = int(data.split(":", 1)[1])
        page_data = await asyncio.to_thread(_poets_page, page)
        await query.message.reply_text(
            f"📚 شاعران — صفحه {int(page_data['page']) + 1} از {int(page_data['pages'])}",
            reply_markup=_poets_keyboard(page_data),
        )
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
        details: list[str] = [f"📂 {category.get('title') or 'مجموعه'}"]
        child_count = int(category.get("child_count") or 0)
        direct_count = int(category.get("direct_poem_count") or 0)
        if child_count:
            details.append(f"زیرمجموعه‌ها: {child_count}")
        if direct_count:
            details.append(f"آثار مستقیم: {direct_count}")
        await query.message.reply_text(
            "\n".join(details),
            reply_markup=_category_keyboard(category, children),
        )
        return

    if data.startswith("cworks:"):
        _, category_text, page_text = data.split(":", 2)
        category_id = int(category_text)
        page_data = await asyncio.to_thread(_category_works, category_id, int(page_text))
        category, _ = await asyncio.to_thread(_category_screen, category_id)
        title = (category or {}).get("title") or "آثار"
        await query.message.reply_text(
            f"📜 {title}\nصفحه {int(page_data['page']) + 1} از {int(page_data['pages'])}",
            reply_markup=_works_keyboard(page_data, category_id=category_id),
        )
        return

    if data.startswith("pworks:"):
        _, poet_text, page_text = data.split(":", 2)
        poet_id = int(poet_text)
        page_data = await asyncio.to_thread(_poet_works, poet_id, int(page_text))
        poet, _ = await asyncio.to_thread(_poet_screen, poet_id)
        name = (poet or {}).get("nickname") or (poet or {}).get("name") or "شاعر"
        await query.message.reply_text(
            f"📜 همهٔ آثار {name}\nصفحه {int(page_data['page']) + 1} از {int(page_data['pages'])}",
            reply_markup=_works_keyboard(page_data, poet_id=poet_id),
        )
        return

    if data.startswith("poem:"):
        poem_id = int(data.split(":", 1)[1])
        poem = await asyncio.to_thread(_full_poem, poem_id)
        if not poem:
            await query.message.reply_text("اثر پیدا نشد.", reply_markup=main_menu())
            return
        rows: list[list[InlineKeyboardButton]] = []
        category_id = poem.get("category_id")
        if category_id is not None:
            rows.append([InlineKeyboardButton("⬅️ بازگشت به مجموعه", callback_data=f"cat:{int(category_id)}")])
        else:
            rows.append([InlineKeyboardButton("⬅️ بازگشت به شاعر", callback_data=f"poet:{int(poem['poet_id'])}")])
        rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu:home")])
        await _send_long(
            query.message,
            format_poem(poem),
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if data == "search:fuzzy":
        last_query = str(context.user_data.get("last_query") or "").strip()
        if not last_query:
            await query.message.reply_text("ابتدا یک عبارت برای جست‌وجو بفرستید.")
            return
        status = await query.message.reply_text("در حال جست‌وجوی تقریبی…")
        rows = await asyncio.to_thread(_fuzzy_search, last_query)
        await status.edit_text(
            "نتایج تقریبی:\n\n" + _format_results(rows, approximate=True)
        )
        return

    if data in {"menu:random", "menu:bookmarks"}:
        await query.message.reply_text(
            "این بخش در مرحلهٔ بعدی رابط کاربری فعال می‌شود.",
            reply_markup=main_menu(),
        )
        return

    if data == "menu:help":
        await query.message.reply_text(
            "🔎 جست‌وجو: بخشی از شعر را بفرستید.\n"
            "🔮 فال حافظ: یک غزل کامل و تصادفی از حافظ.\n"
            "📚 شاعران: مرور شاعر، مجموعه‌ها و متن کامل آثار.\n"
            "≈ جست‌وجوی تقریبی: برای بیت ناقص یا اشتباه‌تایپ‌شده.",
            reply_markup=main_menu(),
        )


def build_application(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("fal", fortune_command))
    app.add_handler(CommandHandler("fortune", fortune_command))
    app.add_handler(CommandHandler("poets", poets_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    return app


def main() -> None:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(
            f"Missing {TOKEN_ENV}. Store the Telegram bot token in the VPS environment, not in Git."
        )

    db_path = _db_path()
    if not db_path.exists():
        raise SystemExit(f"Poetry database not found: {db_path}")

    build_application(token).run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
