# 🎬 Telegram Video Compressor Bot

A Telegram bot built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) that compresses video files using FFmpeg, and sends the compressed result back to the user. The bot allows users to customize several compression parameters including bitrate, resolution, and output format.

## 🚀 Features

- 📥 Accepts video file uploads from users
- 🧰 Compresses videos using the system-installed `ffmpeg` via Python's `subprocess`
- ⚙️ Customizable compression settings:
  - **Output format**: MP4, MKV, AVI, etc.
  - **Resolution**: e.g., 1080p, 720p, 480p
  - **Bitrate**: define target bitrate in kbps
  - **Filename prefix/suffix**
  - **Thumbnail** selection
  - **FFmpeg tune** options (e.g., `film`, `animation`)
- 📤 Sends back the compressed video


## 🧑‍💻 Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/telegram-video-compressor-bot.git
cd telegram-video-compressor-bot
