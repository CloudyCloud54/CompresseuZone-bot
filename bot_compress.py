import asyncio
import aiofiles
import json
import logging
import os
from pathlib import Path
import time

from dotenv import load_dotenv
import ffmpeg
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
    def __init__(self):
        pass

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
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await bot_manager.load_data()
    user_id = str(update.effective_user.id)
    if user_id not in data:
        await bot_manager.init_new_user(user_id=user_id, data=data)
    user = data[user_id]

    upload_type = "Media" if user['upload_type'] == "document" else "Document"

    keyboard = [
        [InlineKeyboardButton(f"Upload comme {upload_type}", callback_data="upload_type")],
        [
            InlineKeyboardButton("🎞 Format de compression de la Vidéo",
                                  callback_data="compresse_format"),
            InlineKeyboardButton("🎬 Résolution de compression de la vidéo",
                                  callback_data="compresse_resolution")
         ],
        [
            InlineKeyboardButton("➕ Préfixe du nom du fichier", callback_data="prefixe"),
            InlineKeyboardButton("Suffixe du nom du fichier", callback_data="suffixe")
        ],
        [InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumbnail")],
        [
            InlineKeyboardButton("📶 Bitrate de compression", callback_data="change_bitrate"),
            InlineKeyboardButton("Tune", callback_data="tune")
         ],
        [InlineKeyboardButton("🔄 Réinitialiser les paramètres", callback_data="reset_user_settings")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "🛠 *Paramètres de compression et d'upload*\n\n"
            f"Upload as *{escape_markdown(text=user['upload_type'], version=2)}*\n"
            f"Compression format : *{escape_markdown(text=user['video_format'], version=2)}*\n"
            f"Résolution de la compression : *{escape_markdown(text=user['compresse_resolution'], version=2)}*\n"
            f"Préfixe du nom du fichier : `{escape_markdown(text=user['prefixe'], version=2)}`\n"
            f"Suffixe du nom du fichier : `{escape_markdown(text=user['suffixe'], version=2)}`\n"
            f"Thumbnail *{escape_markdown(text=user['thumbnail'], version=2)}*\n"
            f"Compression bitrate *{escape_markdown(text=user['bitrate'], version=2)}*\n"
            f"Tune *{escape_markdown(text=user['tune'], version=2)}*\n"
        ),
        parse_mode='MarkdownV2',
        reply_markup=reply_markup
    )

# === Génération des sous-claviers ===
def build_choice_keyboard(param_name: str, choices: list[str]) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(label.upper(), callback_data=f"set:{param_name}:{label}")]
        for label in choices
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="back_to_settings")])
    return InlineKeyboardMarkup(keyboard)


# === Gestion des set:param:value ===
async def handle_set_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, param_name, value = query.data.split(":")

    user_id = str(update.effective_user.id)
    data = await bot_manager.load_data()
    data[user_id][param_name] = value
    await bot_manager.save_data(data)

    await query.answer(f"✅ {param_name} mis à jour : {value.upper()}")
    await settings(update, context)


# === Génération des sous-claviers pour préfixe/suffixe===
def pre_suffix_keyboard(param_name: str):
    keyboard = [
        [InlineKeyboardButton("🗑 Supprimer", callback_data=f"delete_{param_name}")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="back_to_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def set_prefix_suffix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    param_name:str = context.user_data['param_name']
    await query.edit_message_text(f"✏️ Envoyez le {param_name.title()} que vous voulez utiliser :",
                                  reply_markup=pre_suffix_keyboard(param_name=f"{param_name}"))
    return ASK_PREFIX_SUFFIX


# === Changer préfixe ou suffixe ===
async def receive_prefix_suffix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = await bot_manager.load_data()
    param_name = context.user_data.pop('param_name')
    data[user_id][f"{param_name}"] = update.message.text
    await bot_manager.save_data(data)

    await update.message.reply_text(f"✅ {param_name.title()} enregistré : `{update.message.text}`",
                                    parse_mode="Markdown")
    await settings(update, context)
    return ConversationHandler.END


async def handle_change_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"🖼️ Envoyez l'image que vous voulez utiliser comme thumbnail :",
                                  reply_markup=pre_suffix_keyboard(param_name="thumbnail"))
    return ASK_THUMBNAIL


async def delete_pre_suffix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = await bot_manager.load_data()
    param_name = context.user_data.get('param_name', 'suffixe')
    data[user_id][param_name] = ""
    await bot_manager.save_data(data)
    await update.message.reply_text(f"✅ {param_name} supprimé")
    return ConversationHandler.END


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

    await update.message.reply_text("✅ Thumbnail enregistré")
    await settings(update, context)
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
        await update.message.reply_text("✅ Thumbnail supprimé")
    return ConversationHandler.END


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("❌ Action annulée.")
    return ConversationHandler.END


# === Routeur principal ===
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("set:"):
        await handle_set_param(update, context)

    elif data == "upload_type":
        data = await bot_manager.load_data()
        user_id = str(update.effective_user.id)
        data[user_id]['upload_type'] = "media" if data[user_id]['upload_type'] == "document" else "document"
        await bot_manager.save_data(data)

    elif data == "compresse_format":
        await query.edit_message_text(
            "🎞 Choisissez le format de compression :",
            reply_markup=build_choice_keyboard("video_format", ["mp4", "mkv", "avi", "ts"])
        )

    elif data == "compresse_resolution":
        await query.edit_message_text(
            "Choisissez la résolution de compression :",
            reply_markup=build_choice_keyboard("compresse_resolution",
                                               ["1920:1080", "1280:720", "720:480"])
        )

    elif data == "prefixe":
        context.user_data["param_name"] = "prefixe"
        await set_prefix_suffix(update=update, context=context)

    elif data == "suffixe":
        context.user_data["param_name"] = "suffixe"
        await set_prefix_suffix(update=update, context=context)

    elif data == "change_bitrate":
        await query.edit_message_text(
            "📶 Choisissez le bitrate de compression :",
            reply_markup=build_choice_keyboard("bitrate", ["480k", "1000k", "1500k", "2000k"])
        )

    elif data == "reset_user_settings":
        user_id = str(update.effective_user.id)
        await bot_manager.reset_user(user_id)
        await query.answer("🔄 Paramètres réinitialisés")
        await settings(update, context)

    elif data == "back_to_settings":
        await settings(update, context)

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

"""
def compress_video(file_path: str, output_path: str, original_size_mb: float, duration: float = None, format_choice: str = 'mp4') -> tuple:
    """"""Compresse la vidéo en 360p avec FFmpeg.""""""
    try:
        logger.info("Début de la compression vidéo")
        start_time = time.time()
        stream = ffmpeg.input(file_path)
        target_size_mb = original_size_mb * 0.65
        target_bitrate = int(target_size_mb * 8 * 1000 / duration) if duration else 400
        stream = ffmpeg.output(
            stream,
            output_path,
            vcodec='libx264' if format_choice == 'mp4' else 'mpeg4',
            crf=35,
            s='640x360',
            **{'b:v': f'{target_bitrate}k'},
            f=format_choice
        )
        ffmpeg.run(stream, overwrite_output=True)
        end_time = time.time()
        compression_time = end_time - start_time
        compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"Compression terminée : {compressed_size_mb:.2f} Mo en {compression_time:.2f}s")
        return compressed_size_mb, compression_time
    except Exception as e:
        logger.error(f"Erreur compression vidéo : {str(e)}")
        raise


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """"""Gère les vidéos envoyées et les compresse.""""""
    user = update.message.from_user
    logger.info(f"Vidéo reçue de l'utilisateur {user.id}")
    video = update.message.video

    if not video.file_size:
        logger.error("Taille de la vidéo non disponible")
        await update.message.reply_text("Erreur : impossible de vérifier la taille de la vidéo.")
        return

    file_size_mb = video.file_size / (1024 * 1024)
    if file_size_mb > 50:
        logger.warning(f"Vidéo trop grosse : {file_size_mb:.2f} Mo")
        await update.message.reply_text(
            "Désolé, la vidéo est trop grosse ({:.2f} Mo). Limite Telegram : 50 Mo.".format(file_size_mb)
        )
        return

    video_file = video.get_file()
    format_choice = user_formats.get(user.id, 'mp4')
    video_path = f"/tmp/{user.id}_original.mp4"
    compressed_path = f"/tmp/{user.id}_compressed.{format_choice}"

    try:
        logger.info("Téléchargement de la vidéo")
        await update.message.reply_text("Téléchargement de la vidéo...")
        await video_file.download_to_drive(video_path)
    except Exception as e:
        logger.error(f"Erreur téléchargement vidéo : {str(e)}")
        await update.message.reply_text(f"Erreur lors du téléchargement : {str(e)}")
        return

    try:
        await update.message.reply_text(f"Compression en cours (360p, format {format_choice.upper()})...")
        compressed_size_mb, compression_time = compress_video(
            video_path, compressed_path, file_size_mb, video.duration, format_choice
        )

        if compressed_size_mb > 50:
            logger.warning(f"Vidéo compressée trop grosse : {compressed_size_mb:.2f} Mo")
            await update.message.reply_text(
                f"Vidéo compressée à {compressed_size_mb:.2f} Mo, mais trop grosse pour Telegram (limite 50 Mo)."
            )
            os.remove(video_path)
            os.remove(compressed_path)
            return

        await update.message.reply_text(
            f"Compression terminée en {compression_time:.2f}s !\n"
            f"Taille initiale : {file_size_mb:.2f} Mo\n"
            f"Taille compressée : {compressed_size_mb:.2f} Mo"
        )
        with open(compressed_path, "rb") as compressed_file:
            await update.message.reply_video(
                compressed_file, caption=f"Vidéo compressée en {format_choice.upper()} !"
            )

        os.remove(video_path)
        os.remove(compressed_path)

    except Exception as e:
        logger.error(f"Erreur lors de la compression : {str(e)}")
        await update.message.reply_text(f"Oops, erreur lors de la compression : {str(e)}")
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(compressed_path):
            os.remove(compressed_path)
"""

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    settings_handler = CommandHandler('settings', settings)
    help_handler = CommandHandler('help', help)
    main_router_handler = CallbackQueryHandler(callback_router)
    cancel_handler = CallbackQueryHandler(cancel_callback, pattern="^cancel$")

    conv_handler_pre_suffix = ConversationHandler(
        entry_points=[],
        states={
            ASK_PREFIX_SUFFIX: [
                MessageHandler(filters.TEXT, receive_prefix_suffix),
                CallbackQueryHandler(cancel_callback, pattern="^back_to_settings$"),
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
                CallbackQueryHandler(cancel_callback, pattern="^back_to_settings$"),
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