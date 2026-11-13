# openEDM API. Build from the repository root:  docker build -f server/Dockerfile .
FROM python:3.13-alpine
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY server/requirements.txt server/
RUN pip install --no-cache-dir -r server/requirements.txt
COPY tools/import_rive_claire.py tools/rc_quality.py tools/
COPY rive-claire/EIAK-RC-Guide-Donnees-vf.html rive-claire/
COPY server/ server/
USER nobody
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
