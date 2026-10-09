FROM python:3.12-slim
WORKDIR /app
COPY aifactory/ /app/
RUN pip install --no-cache-dir .
EXPOSE 4710
VOLUME ["/data"]
CMD ["python", "-m", "aifactory.database.server", "--host", "0.0.0.0", "--data-dir", "/data"]
