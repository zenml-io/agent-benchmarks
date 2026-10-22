FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tmux asciinema procps time && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir numpy==2.1.3 pytest==8.4.1 pyyaml==6.0.2
RUN pip install --no-cache-dir ray==2.50.1
WORKDIR /app
COPY app/ /app/
COPY gen/ /tmp/gen/
RUN cd /app && bash /tmp/gen/gen.sh && rm -rf /tmp/gen
