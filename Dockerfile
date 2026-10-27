FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /srv

# Runtime deps only (requirements.txt also lists the test tools).
RUN pip install --no-cache-dir fastapi==0.140.4 uvicorn==0.54.0 pydantic==2.14.1 PyJWT==2.15.1

COPY app ./app
COPY docs ./docs

RUN useradd --system --uid 10001 sim
USER sim
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
