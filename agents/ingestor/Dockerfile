FROM python:3.10-slim
WORKDIR /app
RUN pip install --no-cache-dir openpyxl==3.1.5
COPY app.py .
CMD ["python", "app.py"]
