FROM python:3.11.5
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "src.poebot_test:app", "--host", "0.0.0.0", "--port", "8000"]