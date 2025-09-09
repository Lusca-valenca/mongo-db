FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \ PYTHONUNBUFFRED=1 \ PIP_NO_CACHE_DIR=1

WORKDIR /app

#Opicional

RUN python -m pip install --upgrade pip

#instalar as dependencias
COPY requirements.txt .
RUN pip install -r requirements.txt

#copiar o app por ultimo p aproveitar o cache

COPY app ./app

#documenta a porta usada pela aplicação dentro do conteiner
#Não é uma publicação de porta no host, quem publicar é o docker run -p/compose
#METADADO
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

