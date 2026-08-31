FROM python:3.11-slim

ARG INSTALL_FULL=false
ARG INSTALL_DEV=false
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential git libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements; keep API deps minimal for fast builds. Copy both files so
# INSTALL_FULL can install the full requirements when requested.
COPY requirements-api.txt requirements-api.txt ./
COPY requirements.txt requirements.txt ./
COPY requirements-dev.txt requirements-dev.txt ./

RUN pip install --upgrade pip
RUN pip install -r requirements-api.txt
# If full install requested, install the main requirements.txt (may be large)
RUN if [ "${INSTALL_FULL}" = "true" ]; then pip install -r requirements.txt; fi
# If development install requested, install dev requirements (pytest, requests)
RUN if [ "${INSTALL_DEV}" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
