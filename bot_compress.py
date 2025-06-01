import asyncio
import aiofiles
import json
import logging
import os
from pathlib import Path
import time

from dotenv import load_dotenv
from telegram import (Update,
                      InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.helpers import escape_markdown
from telegram.ext import (ApplicationBuilder,
                          CommandHandler,
                          CallbackQueryHandler,
                          ConversationHandler,
                          MessageHandler,
                          ContextTypes,
                          filters)


# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.WARNING)
logger = logging.getLogger(__name__)

# Variables d'environnement
load_dotenv(dotenv_path = ".token/token.env")
TOKEN = str(os.environ.get("TOKEN"))

if not TOKEN:
    raise ValueError("TOKEN must be set in environment variables")

# Data file configuration
DATA_FILE = "compresse_data.json"

class BotManager:

    async def load_data(self) -> dict:
        if not os.path.exists(DATA_FILE):
            return {}
        async with aiofiles.open(DATA_FILE, "r") as f:
            content = await f.read()
            if not content.strip():
                return {}
            return json.loads(content)

    async def save_data(self, data) -> None:
        async with aiofiles.open(DATA_FILE, "w") as f:
            await f.write(json.dumps(data, indent=4))

    async def init_new_user(self, user_id, data):
        if user_id not in data:
            data[user_id] = {
                "upload_type": "media",
                "video_format": "mp4",
                "compresse_resolution": "1280:720",
                "prefixe": "",
                "suffixe": "",
                "thumbnail": "Not exist",
                "bitrate": "480k",
                "tune": "film"
            }
            await self.save_data(data)

    async def reset_user(self, user_id):
        data = await self.load_data()
        data[user_id] = {
            "upload_type": "media",
            "video_format": "mp4",
            "compresse_resolution": "1280:720",
            "prefixe": "",
            "suffixe": "",
            "thumbnail": "Not exist",
            "bitrate": "480k",
            "tune": "film"
        }
        await self.save_data(data)

bot_manager = BotManager()

ASK_PREFIX_SUFFIX = 0
ASK_THUMBNAIL = 1

# === Menu de paramètre principal ===
def build_settings_message(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    """
        Generates the text and keyboard markup for the settings menu.

        Args:
            user (dict): User's saved settings.

        Returns:
            tuple: A Markdown-formatted message and its InlineKeyboardMarkup.
        """

    upload_type = "Media" if user['upload_type'] == "document" else "Document"
    keyboard = [
        [InlineKeyboardButton(f"Upload comme {upload_type}", callback_data="upload_type")],
        [
            InlineKeyboardButton("Output Format", callback_data="compresse_format"),
            InlineKeyboardButton("Résolution", callback_data="compresse_resolution")
        ],
        [
            InlineKeyboardButton("Préfixe", callback_data="prefixe"),
            InlineKeyboardButton("Suffixe", callback_data="suffixe")
        ],
        [InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumbnail")],
        [
            InlineKeyboardButton("Bitrate", callback_data="change_bitrate"),
            InlineKeyboardButton("Tune", callback_data="tune")
        ],
        [InlineKeyboardButton("🔄 Réinitialiser les paramètres", callback_data="reset_user_settings")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ]
    text = (
        "🛠 *Paramètres de compression et d'upload*\n\n"
        f"Upload as : *{escape_markdown(text=user['upload_type'], version=2).upper()}*\n"
        f"Compression format : *{escape_markdown(text=user['video_format'], version=2).upper()}*\n"
        f"Résolution de la compression : *{escape_markdown(text=user['compresse_resolution'], version=2)}*\n"
        f"Préfixe : `{escape_markdown(text=user['prefixe'], version=2)}`\n"
        f"Suffixe : `{escape_markdown(text=user['suffixe'], version=2)}`\n"
        f"Thumbnail : *{escape_markdown(text=user['thumbnail'], version=2)}*\n"
        f"Compression bitrate : *{escape_markdown(text=user['bitrate'], version=2).upper()}*\n"
        f"Tune : *{escape_markdown(text=user['tune'], version=2).upper()}*\n"
    )
    return text, InlineKeyboardMarkup(keyboard)


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
        Displays or updates the main compression settings menu for the user.
        Can be triggered by command or callback.
        """

    data = await bot_manager.load_data()
    user_id = str(update.effective_user.id)
    if user_id not in data:
        await bot_manager.init_new_user(user_id=user_id, data=data)
    user = data[user_id]

    text, reply_markup = build_settings_message(user)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )


# === Génération des sous-claviers ===
def build_choice_keyboard(param_name: str, choices: list[str]) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(label.upper(), callback_data=f"set {param_name} {label}")]
        for label in choices
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="back_to_settings")])
    return InlineKeyboardMarkup(keyboard)


# === Gestion des set:param:value ===
async def handle_set_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
        Callback handler to set a specific user parameter (e.g., bitrate, format).
        Updates the data store and refreshes the settings message.
        """

    query = update.callback_query
    _, param_name, value = query.data.split(" ")

    user_id = str(update.effective_user.id)
    data = await bot_manager.load_data()
    data[user_id][param_name] = value
    await bot_manager.save_data(data)
    await settings(update, context)


# === Génération des sous-claviers pour préfixe/suffixe===
def pre_suffix_keyboard(param_name: str):
    keyboard = [
        [InlineKeyboardButton("🗑 Supprimer", callback_data=f"delete_{param_name}")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="back_to_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def set_prefix_suffix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
        Entry point for asking the user to type a custom prefix or suffix.
        Stores the request context and parameter name in user_data.
        """

    query = update.callback_query
    await query.answer()

    # Save currect update to edit after the good message : avoid to send new setting message
    context.user_data['current_update'] = update

    param_name = query.data
    context.user_data["param_name"] = param_name

    await query.edit_message_text(
        f"✏️ Envoyez le {param_name.title()} que vous voulez utiliser :",
        reply_markup=pre_suffix_keyboard(param_name)
    )
    return ASK_PREFIX_SUFFIX


# === Changer préfixe ou suffixe ===
async def receive_prefix_suffix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
        Handles text input from the user to set the prefix or suffix.
        Updates the stored settings and refreshes the UI.
        """

    user_id = str(update.effective_user.id)
    data = await bot_manager.load_data()
    param_name = context.user_data.pop('param_name')
    data[user_id][f"{param_name}"] = update.message.text
    await bot_manager.save_data(data)
    await context.bot.delete_message(chat_id= update.effective_chat.id, message_id=update.effective_message.id)

    last_update = context.user_data.pop('current_update')
    await settings(update=last_update, context=context)
    return ConversationHandler.END


async def delete_pre_suffix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = await bot_manager.load_data()
    param_name = context.user_data.get('param_name', 'suffixe')
    data[user_id][param_name] = ""
    await bot_manager.save_data(data)
    last_update = context.user_data.pop('current_update')
    await settings(update=last_update, context=context)
    return ConversationHandler.END


async def handle_change_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Save currect update to edit after the good message : avoid to send new setting message
    context.user_data['current_update'] = update
    await query.edit_message_text(f"🖼️ Envoyez l'image que vous voulez utiliser comme thumbnail :",
                                  reply_markup=pre_suffix_keyboard(param_name="thumbnail"))
    return ASK_THUMBNAIL


async def receive_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    user_id = str(update.effective_user.id)
    user_dir = Path(Path.cwd() / f"{user_id}")
    user_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = user_dir / "thumbnail.jpeg"
    await file.download_to_drive(custom_path=thumbnail_path)
    data = await bot_manager.load_data()
    data[user_id]['thumbnail'] = "Exist"
    await bot_manager.save_data(data)
    await context.bot.delete_message(update.effective_chat.id, update.effective_message.id)

    last_update = context.user_data.pop('current_update')
    await settings(update=last_update, context=context)
    return ConversationHandler.END


async def delete_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_dir = Path(Path.cwd() / f"{user_id}")
    thumbnail_path = user_dir / "thumbnail.jpeg"
    if thumbnail_path.exists():
        thumbnail_path.unlink(missing_ok=True)
        data = await bot_manager.load_data()
        data[user_id]['thumbnail'] = "Not Exist"
        await bot_manager.save_data(data)

    last_update = context.user_data.pop('current_update')
    await settings(update=last_update, context=context)
    return ConversationHandler.END


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.effective_message.id)
    return ConversationHandler.END


async def conversation_back_to_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_update = context.user_data.pop('current_update')
    await settings(update=last_update, context=context)
    return ConversationHandler.END


# === Routeur principal ===
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
        Main dispatcher for all inline button actions in the settings menu.
        Routes button presses to the correct action.
        """

    query = update.callback_query
    data = query.data

    if data.startswith("set"):
        await handle_set_param(update, context)

    elif data == "upload_type":
        data = await bot_manager.load_data()
        user_id = str(update.effective_user.id)
        data[user_id]['upload_type'] = "media" if data[user_id]['upload_type'] == "document" else "document"
        await bot_manager.save_data(data)
        text, reply_markup = build_settings_message(data[user_id])
        await query.edit_message_text(text=text, parse_mode='MarkdownV2', reply_markup=reply_markup)


    elif data == "compresse_format":
        await query.edit_message_text(
            "Choisissez le format de compression :",
            reply_markup=build_choice_keyboard("video_format", ["mp4", "mkv", "avi", "ts"])
        )

    elif data == "compresse_resolution":
        await query.edit_message_text(
            "Choisissez la résolution de compression :",
            reply_markup=build_choice_keyboard("compresse_resolution",
                                               ["1920:1080", "1280:720", "720:480"])
        )

    elif data == "change_bitrate":
        await query.edit_message_text(
            "Choisissez le bitrate de compression :",
            reply_markup=build_choice_keyboard("bitrate", ["480k", "1000k", "1500k", "2000k"])
        )

    elif data == "tune":
        await query.edit_message_text(
            "Choisissez le tune de compression :",
            reply_markup=build_choice_keyboard(param_name="tune",
                                               choices=["animation", "film", "grain", "stillimage", "zerolatency"])
        )

    elif data == "reset_user_settings":
        user_id = str(update.effective_user.id)
        await bot_manager.reset_user(user_id)
        await query.answer("🔄 Paramètres réinitialisés")
        await settings(update, context)

    elif data == "back_to_settings":
        await settings(update, context)

    elif data == "close":
        await cancel_callback(update, context)

    else:
        await query.answer("❌ Action inconnue")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /start : Affiche un message de bienvenue."""
    data = await bot_manager.load_data()
    user_id = str(update.message.from_user.id)
    if not user_id in data:
        await bot_manager.init_new_user(user_id=user_id, data=data)

    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=(
                                       "Salut ! Je suis le bot de compression vidéo par @Kevloudy 😎\n"
                                       "Faites la commande /help pour afficher l'aide."
                                        )
                                   )


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help instructions to the user."""
    help_text = (
        "📚 *Video Compression Bot \\- Help*\n\n"
        "You can send me a video file and I will compress it based on your preferences\\.\n\n"
        "⚙️ *Settings*\n"
        "/settings \\- Open the compression settings menu\\:\n"
        "• Output format \\(mp4, mkv, avi\\.\\.\\.\\)\n"
        "• Resolution \\(e\\.g\\., 1280x720\\)\n"
        "• Bitrate \\(e\\.g\\., 480k, 1000k\\)\n"
        "• Filename prefix\\/suffix\n"
        "• Thumbnail\n"
        "• FFmpeg tune profile\n\n"
        "▶️ *How to use*\n"
        "1\\. Set your preferences via /settings\\.\n"
        "2\\. Send me a video file \\(max \\~2000MB for upload\\)\\.\n"
        "3\\. I will compress it and send it back to you\\.\n\n"
        "🔄 You can reset your settings anytime in the settings menu\\.\n\n"
        "👨‍💻 Created by @Kevloudy and @Samson\\_Hyacinth"
    )

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_text,
        parse_mode="MarkdownV2"
    )


if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    settings_handler = CommandHandler('settings', settings)
    help_handler = CommandHandler('help', help)
    main_router_handler = CallbackQueryHandler(callback_router)
    cancel_handler = CallbackQueryHandler(cancel_callback, pattern="^cancel$")

    conv_handler_pre_suffix = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_prefix_suffix, pattern="^(prefixe|suffixe)$")
        ],
        states={
            ASK_PREFIX_SUFFIX: [
                MessageHandler(filters.TEXT, receive_prefix_suffix),
                CallbackQueryHandler(conversation_back_to_setting, pattern="^back_to_settings$"),
                CallbackQueryHandler(delete_pre_suffix, pattern="^delete_prefixe$"),
                CallbackQueryHandler(delete_pre_suffix, pattern="^delete_suffixe$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_callback)],
        allow_reentry=True
    )

    conv_handler_thumbnail = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_change_thumbnail, pattern="^thumbnail$")],
        states={
            ASK_THUMBNAIL: [
                MessageHandler(filters.PHOTO, receive_thumbnail),
                CallbackQueryHandler(conversation_back_to_setting, pattern="^back_to_settings$"),
                CallbackQueryHandler(delete_thumbnail, pattern="^delete_thumbnail$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_callback)],
        allow_reentry=True
    )

    application.add_handler(start_handler)
    application.add_handler(settings_handler)
    application.add_handler(help_handler)
    application.add_handler(conv_handler_thumbnail)
    application.add_handler(conv_handler_pre_suffix)
    application.add_handler(main_router_handler)
    application.add_handler(cancel_handler)

    application.run_polling()