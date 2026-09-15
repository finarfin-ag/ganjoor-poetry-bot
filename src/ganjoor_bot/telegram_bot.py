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

from .db import connect
from .fortune import format_fortune_text, get_hafez_fortune
from .search import search_verses, smart_search


DB_ENV = "POETRY_DB"
TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
DEFAULT_DB = Path("data/poetry.sqlite")


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
    # Plain text is useful as a search shortcut even if the user did not tap Search.
    await _handle_search_text(update, context, text)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

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

    if data in {"menu:random", "menu:poets", "menu:bookmarks"}:
        await query.message.reply_text(
            "این بخش در مرحلهٔ بعدی رابط کاربری فعال می‌شود.",
            reply_markup=main_menu(),
        )
        return

    if data == "menu:help":
        await query.message.reply_text(
            "🔎 جست‌وجو: بخشی از شعر را بفرستید.\n"
            "🔮 فال حافظ: یک غزل کامل و تصادفی از حافظ.\n"
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
