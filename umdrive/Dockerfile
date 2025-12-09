# Imagem base oficial do Python
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia os ficheiros do teu projeto para o container
COPY . /app

# Instala dependências (Flask, werkzeug, prometheus_client)
RUN pip install --no-cache-dir flask werkzeug prometheus_client

# Define a variável de ambiente para o Flask
ENV FLASK_APP=umdrive.py
ENV PYTHONUNBUFFERED=1

# Expõe a porta 5000
EXPOSE 5000

# Comando para iniciar o servidor Flask
CMD ["python", "umdrive.py"]
