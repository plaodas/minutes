FROM python:3.11-slim

ARG INSTALL_FULL=false
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements; keep API deps minimal for fast builds. Copy both files so
# INSTALL_FULL can install the full requirements when requested.
COPY requirements-api.txt requirements-api.txt ./
COPY requirements.txt requirements.txt ./

RUN pip install --upgrade pip
RUN pip install -r requirements-api.txt
# If full install requested, install the main requirements.txt (may be large)
RUN if [ "${INSTALL_FULL}" = "true" ]; then pip install -r requirements.txt; fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
