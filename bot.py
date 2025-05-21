import logging
import time
import requests
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes
from telegram.ext.filters import filters  # Changement ici
from PIL import Image
import ffmpeg
import urllib3.exceptions
import re
from urllib.parse import urlparse
from flask import Flask, request
import asyncio

app = Flask(__name__)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger('telegram').setLevel(logging.WARNING)

TOKEN = os.environ.get("BOT_TOKEN", "7844193910:AAF6hVAQERF6g4itTrbloTShxWlnuA2qbtI")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug("Commande /start reçue")
    await update.message.reply_text(
        "Salut ! Je suis le bot de compression des chaînes zone créer par @Kevloudy 😎. "
        "Envoie-moi une image, une vidéo (<50 Mo), ou un lien vers un fichier (>100 Mo) pour le compresser ! 😎"
    )

def compress_image(file_path: str, output_path: str, original_size_mb: float) -> tuple:
    try:
        logger.debug("Compression de l'image")
        start_time = time.time()
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            img.save(output_path, "JPEG", quality=50)
        end_time = time.time()
        compression_time = end_time - start_time
        compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.debug(f"Taille de l'image compressée : {compressed_size_mb:.2f} Mo")
        return compressed_size_mb, compression_time
    except Exception as e:
        logger.error(f"Erreur compression image : {str(e)}")
        raise

def compress_video(file_path: str, output_path: str, original_size_mb: float, duration: float = None) -> tuple:
    try:
        logger.debug("Début de la compression vidéo")
        start_time = time.time()
        stream = ffmpeg.input(file_path)
        target_size_mb = original_size_mb * 0.65
        target_bitrate = int(target_size_mb * 8 * 1000 / duration) if duration else 400
        stream = ffmpeg.output(
            stream,
            output_path,
            vcodec="libx264",
            crf=35,
            s="640x360",
            **{"b:v": f"{target_bitrate}k"}
        )
        ffmpeg.run(stream)
        end_time = time.time()
        compression_time = end_time - start_time
        compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.debug(f"Taille de la vidéo compressée : {compressed_size_mb:.2f} Mo")
        return compressed_size_mb, compression_time
    except Exception as e:
        logger.error(f"Erreur compression vidéo : {str(e)}")
        raise

def download_file_from_url(url: str, output_path: str) -> float:
    try:
        logger.debug(f"Téléchargement du fichier depuis {url}")
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.debug(f"Taille du fichier téléchargé : {file_size_mb:.2f} Mo")
        return file_size_mb
    except Exception as e:
        logger.error(f"Erreur téléchargement URL : {str(e)}")
        raise

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    logger.debug(f"Image reçue de l'utilisateur {user.id}")
    
    photo_file = update.message.photo[-1].get_file()
    photo_path = f"/tmp/{user.id}_original.jpg"
    compressed_path = f"/tmp/{user.id}_compressed.jpg"

    file_size_mb = photo_file.file_size / (1024 * 1024) if hasattr(photo_file, 'file_size') else 0
    logger.debug(f"Taille de l'image : {file_size_mb:.2f} Mo")
    if file_size_mb > 50:
        await update.message.reply_text(
            f"Désolé, l'image est trop grosse ({file_size_mb:.2f} Mo). Limite Telegram : 50 Mo. "
            "Envoie un lien vers le fichier (ex. : Google Drive) pour les fichiers >50 Mo."
        )
        return

    try:
        logger.debug("Téléchargement de l'image")
        await update.message.reply_text("Téléchargement de l'image en cours...")
        await photo_file.download_to_drive(photo_path, timeout=120)
    except urllib3.exceptions.HTTPError as e:
        logger.error(f"Erreur réseau lors du téléchargement image : {str(e)}")
        await update.message.reply_text("Erreur réseau : timeout ou connexion instable.")
        return
    except Exception as e:
        logger.error(f"Erreur téléchargement image : {str(e)}")
        await update.message.reply_text(f"Erreur lors du téléchargement : {str(e)}")
        return

    try:
        await update.message.reply_text("Compression de l'image en cours...")
        compressed_size_mb, compression_time = compress_image(photo_path, compressed_path, file_size_mb)

        if compressed_size_mb > 50:
            await update.message.reply_text(
                f"La compression a réduit l'image à {compressed_size_mb:.2f} Mo, mais c'est trop gros pour Telegram (limite 50 Mo). "
                "Je peux uploader le fichier compressé sur un service externe si tu configures Google Drive."
            )
            os.remove(photo_path)
            os.remove(compressed_path)
            return

        await update.message.reply_text(
            f"Compression terminée en {compression_time:.2f} secondes ! "
            f"Taille initiale : {file_size_mb:.2f} Mo, Taille compressée : {compressed_size_mb:.2f} Mo"
        )
        with open(compressed_path, "rb") as compressed_file:
            await update.message.reply_photo(compressed_file, caption="Voici ton image compressée !")
        
        os.remove(photo_path)
        os.remove(compressed_path)

    except Exception as e:
        await update.message.reply_text(f"Oops, erreur lors de la compression : {str(e)}")
        if os.path.exists(photo_path):
            os.remove(photo_path)
        if os.path.exists(compressed_path):
            os.remove(compressed_path)

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    logger.debug(f"Vidéo reçue de l'utilisateur {user.id}")
    video = update.message.video

    if not hasattr(video, 'file_size') or video.file_size is None:
        logger.error("Taille de la vidéo non disponible")
        await update.message.reply_text("Erreur : impossible de vérifier la taille de la vidéo.")
        return

    file_size_mb = video.file_size / (1024 * 1024)
    logger.debug(f"Taille de la vidéo : {file_size_mb:.2f} Mo")
    if file_size_mb > 50:
        await update.message.reply_text(
            f"Désolé, la vidéo est trop grosse ({file_size_mb:.2f} Mo). Limite Telegram : 50 Mo. "
            "Envoie un lien vers le fichier (ex. : Google Drive) pour les fichiers >50 Mo."
        )
        return

    video_file = video.get_file()
    video_path = f"/tmp/{user.id}_original.mp4"
    compressed_path = f"/tmp/{user.id}_compressed.mp4"

    try:
        logger.debug("Téléchargement de la vidéo")
        await update.message.reply_text("Téléchargement de la vidéo en cours...")
        await video_file.download_to_drive(video_path, timeout=120)
    except urllib3.exceptions.HTTPError as e:
        logger.error(f"Erreur réseau lors du téléchargement vidéo : {str(e)}")
        await update.message.reply_text("Erreur réseau : timeout ou connexion instable.")
        return
    except Exception as e:
        logger.error(f"Erreur téléchargement vidéo : {str(e)}")
        await update.message.reply_text(f"Erreur lors du téléchargement : {str(e)}")
        return

    try:
        await update.message.reply_text("Compression en cours (résolution 360p)...")
        compressed_size_mb, compression_time = compress_video(video_path, compressed_path, file_size_mb, video.duration)

        if compressed_size_mb > 50:
            await update.message.reply_text(
                f"La compression a réduit la vidéo à {compressed_size_mb:.2f} Mo, mais c'est trop gros pour Telegram (limite 50 Mo). "
                "Je peux uploader le fichier compressé sur un service externe si tu configures Google Drive."
            )
            os.remove(video_path)
            os.remove(compressed_path)
            return

        await update.message.reply_text(
            f"Compression terminée en {compression_time:.2f} secondes ! "
            f"Taille initiale : {file_size_mb:.2f} Mo, Taille compressée : {compressed_size_mb:.2f} Mo"
        )
        with open(compressed_path, "rb") as compressed_file:
            await update.message.reply_video(compressed_file, caption="Voici ta vidéo compressée !")

        os.remove(video_path)
        os.remove(compressed_path)

    except Exception as e:
        await update.message.reply_text(f"Oops, erreur lors de la compression : {str(e)}")
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(compressed_path):
            os.remove(compressed_path)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    logger.debug(f"Lien reçu de l'utilisateur {user.id}")
    url = update.message.text

    if not re.match(r'https?://[^\s]+', url):
        await update.message.reply_text("Erreur : envoie un lien valide (ex. : Google Drive, WeTransfer).")
        return

    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path)
    file_ext = os.path.splitext(file_name)[1].lower()
    is_image = file_ext in ['.jpg', '.jpeg', '.png']
    is_video = file_ext in ['.mp4', '.mov', '.avi']

    if not (is_image or is_video):
        await update.message.reply_text("Erreur : seuls les fichiers image (.jpg, .png) ou vidéo (.mp4, .mov, .avi) sont supportés.")
        return

    file_path = f"/tmp/{user.id}_original{file_ext}"
    compressed_path = f"/tmp/{user.id}_compressed{file_ext if is_image else '.mp4'}"

    try:
        await update.message.reply_text(f"Téléchargement du fichier depuis {file_name}...")
        file_size_mb = download_file_from_url(url, file_path)
        if file_size_mb > 200:
            await update.message.reply_text("Erreur : fichier trop gros (>200 Mo) pour le plan gratuit Render.")
            os.remove(file_path)
            return
    except Exception as e:
        await update.message.reply_text(f"Erreur lors du téléchargement : {str(e)}")
        return

    try:
        await update.message.reply_text("Compression en cours..." + (" (résolution 360p)" if is_video else ""))
        if is_image:
            compressed_size_mb, compression_time = compress_image(file_path, compressed_path, file_size_mb)
        else:
            compressed_size_mb, compression_time = compress_video(file_path, compressed_path, file_size_mb)

        if compressed_size_mb > 50:
            await update.message.reply_text(
                f"La compression a réduit le fichier à {compressed_size_mb:.2f} Mo, mais c'est trop gros pour Telegram (limite 50 Mo). "
                "Je peux uploader le fichier compressé sur un service externe si tu configures Google Drive."
            )
            os.remove(file_path)
            os.remove(compressed_path)
            return

        await update.message.reply_text(
            f"Compression terminée en {compression_time:.2f} secondes ! "
            f"Taille initiale : {file_size_mb:.2f} Mo, Taille compressée : {compressed_size_mb:.2f} Mo"
        )
        with open(compressed_path, "rb") as compressed_file:
            if is_image:
                await update.message.reply_photo(compressed_file, caption="Voici ton image compressée !")
            else:
                await update.message.reply_video(compressed_file, caption="Voici ta vidéo compressée !")

        os.remove(file_path)
        os.remove(compressed_path)

    except Exception as e:
        await update.message.reply_text(f"Oops, erreur lors de la compression : {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(compressed_path):
            os.remove(compressed_path)

@app.route(f'/{TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(), application.bot)
    await application.process_update(update)
    return 'OK'

async def main():
    global application
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))  # Changement ici
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))  # Changement ici
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))  # Changement ici

    logger.info("Bot démarré avec succès ! Configuration du webhook...")
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=WEBHOOK_URL + f'/{TOKEN}')
        logger.info(f"Webhook configuré : {WEBHOOK_URL}/{TOKEN}")
    else:
        logger.error("WEBHOOK_URL non défini !")
        return

    from threading import Thread
    def run_flask():
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8443)))
    Thread(target=run_flask).start()

if __name__ == '__main__':
    asyncio.run(main())