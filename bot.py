import logging
import os
import time
import ffmpeg
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes
from telegram.ext.filters import VIDEO, COMMAND  # Importation correcte

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Variables d'environnement
TOKEN = os.environ.get("BOT_TOKEN", "7844193910:AAF6hVAQERF6g4itTrbloTShxWlnuA2qbtI")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# Dictionnaire pour stocker le format choisi par utilisateur (par défaut : MP4)
user_formats = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /start : Affiche un message de bienvenue."""
    user = update.message.from_user
    logger.info(f"Commande /start reçue de {user.id}")
    await update.message.reply_text(
        "Salut ! Je suis le bot de compression vidéo par @Kevloudy 😎\n"
        "Envoie-moi une vidéo (<50 Mo) à compresser en 360p.\n"
        "Choisis le format avec /format mp4 ou /format avi (défaut : MP4)."
    )

async def set_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /format : Définit le format de sortie (mp4 ou avi)."""
    user = update.message.from_user
    if not context.args or context.args[0].lower() not in ['mp4', 'avi']:
        await update.message.reply_text("Utilise : /format mp4 ou /format avi")
        return
    format_choice = context.args[0].lower()
    user_formats[user.id] = format_choice
    logger.info(f"Utilisateur {user.id} a choisi le format {format_choice}")
    await update.message.reply_text(f"Format défini : {format_choice.upper()}")

def compress_video(file_path: str, output_path: str, original_size_mb: float, duration: float = None, format_choice: str = 'mp4') -> tuple:
    """Compresse la vidéo en 360p avec FFmpeg."""
    try:
        logger.info("Début de la compression vidéo")
        start_time = time.time()
        stream = ffmpeg.input(file_path)
        target_size_mb = original_size_mb * 0.65  # Cible : 65% de la taille
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
    """Gère les vidéos envoyées et les compresse."""
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
    format_choice = user_formats.get(user.id, 'mp4')  # Par défaut : MP4
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

async def main():
    """Démarre le bot avec webhook."""
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("format", set_format))
    application.add_handler(MessageHandler(VIDEO, handle_video))  # Utilisation de VIDEO

    logger.info("Bot démarré, configuration du webhook...")
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
        logger.info(f"Webhook configuré : {WEBHOOK_URL}/{TOKEN}")
    else:
        logger.error("WEBHOOK_URL non défini !")
        return

    # Lancer Flask pour le webhook
    from flask import Flask, request
    flask_app = Flask(__name__)

    @flask_app.route(f'/{TOKEN}', methods=['POST'])
    async def webhook():
        update = Update.de_json(request.get_json(), application.bot)
        await application.process_update(update)
        return 'OK'

    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8443)))

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())