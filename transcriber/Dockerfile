FROM python:3.10-slim-buster

WORKDIR /app

# Install uv
RUN pip install uv

# COPY requirements.txt .
# RUN uv pip install --no-cache-dir -r requirements.txt

COPY . /app

WORKDIR /app
RUN uv sync --frozen 

# Install ffmpeg (required by moviepy and pydub)
RUN apt-get update && apt-get install -y ffmpeg

# Install moviepy and its dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1-mesa-utils \
#     xvfb

RUN pip install imageio[ffmpeg]

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

CMD ["/app/.venv/bin/flask", "run", "--host=0.0.0.0", "--port=5002"]
