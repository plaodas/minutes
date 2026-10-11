FROM python:3.11-slim

ARG INSTALL_FULL=false
ARG INSTALL_WORKER=false
ARG INSTALL_DEV=false
ARG INSTALL_HAYAMIMI=false
ARG HAYAMIMI_REF=09c8081420c7c88374eb24ae533ea470de794203
ENV PYTHONUNBUFFERED=1
ENV PIP_DEFAULT_TIMEOUT=120

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential git libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements; keep API deps minimal for fast builds. Copy both files so
# INSTALL_FULL can install the full requirements when requested.
COPY requirements-api.txt requirements-api.txt ./
COPY requirements.txt requirements.txt ./
COPY requirements-worker.txt requirements-worker.txt ./
COPY requirements-dev.txt requirements-dev.txt ./
COPY requirements-hayamimi.txt requirements-hayamimi.txt ./

RUN pip install --disable-pip-version-check --no-cache-dir --upgrade pip setuptools wheel || \
    pip install --disable-pip-version-check --no-cache-dir --upgrade pip setuptools wheel --timeout 120
RUN pip install --no-cache-dir -r requirements-api.txt
# The default portfolio worker uses faster-whisper on CPU without the
# CUDA/PyTorch-heavy full development dependency set.
RUN if [ "${INSTALL_WORKER}" = "true" ]; then pip install --no-cache-dir -r requirements-worker.txt; fi
# If full install requested, install the main requirements.txt (may be large)
RUN if [ "${INSTALL_FULL}" = "true" ]; then pip install --no-cache-dir -r requirements.txt; fi
# If development install requested, install dev requirements (pytest, requests)
RUN if [ "${INSTALL_DEV}" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi
# Optional Japanese engine. Weights stay on a volume; this only fetches source.
RUN if [ "${INSTALL_HAYAMIMI}" = "true" ]; then \
      pip install --no-cache-dir -r requirements-hayamimi.txt \
      && git clone https://github.com/oboroge0/hayamimi.git /opt/hayamimi \
      && git -C /opt/hayamimi checkout ${HAYAMIMI_REF} \
      && rm -rf /opt/hayamimi/.git; \
    fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
