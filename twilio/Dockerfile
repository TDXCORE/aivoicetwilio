FROM dailyco/pipecat-base:latest

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir --upgrade -r requirements.txt

EXPOSE 8000

CMD ["python", "main.py"]
