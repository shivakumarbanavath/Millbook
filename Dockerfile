FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home millbook && mkdir -p /app/data && chown millbook /app/data
COPY --chown=millbook . .
USER millbook
ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python","app.py"]
