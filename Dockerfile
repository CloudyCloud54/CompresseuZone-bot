FROM jrottenberg/ffmpeg:4.4-ubuntu

# Installer Python et pip
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
# Vérifier que gunicorn est installé
RUN python3 -m pip show gunicorn || { echo "gunicorn not installed"; exit 1; }
COPY . .

# Utiliser une commande shell pour s'assurer que gunicorn est exécuté
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 bot:app