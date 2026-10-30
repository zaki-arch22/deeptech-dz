FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client libfribidi0 libharfbuzz0b tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Africa/Algiers PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# the project folder is mounted at /app, so `git pull` updates code and queue in place
CMD ["python", "-m", "dtdz.runner"]
