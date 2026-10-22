FROM python:3.12-slim
RUN pip install --no-cache-dir "mcp==1.26.0"
COPY uw /opt/uw
RUN python3 -c "import lzma, shutil; shutil.copyfileobj(lzma.open('/opt/uw/env/insurance.db.xz'), open('/opt/uw/env/insurance.db', 'wb'))" \
    && rm /opt/uw/env/insurance.db.xz
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python3", "/opt/uw/server.py"]
