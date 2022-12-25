FROM python:3.9

ENV PYTHONUNBUFFERED=1
ENV USE_ENV_CONFIG=1

WORKDIR /app

# Python Dependencies
COPY requirements/requirements.txt .
RUN pip install -r requirements.txt

# App setup
COPY panel /app/panel
COPY main.py /app

EXPOSE 1337
CMD ["python3.9", "main.py"]
