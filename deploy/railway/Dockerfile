FROM python:3.12-slim
WORKDIR /app
COPY gateway /app/gateway
COPY tests/__init__.py tests/fake_upstream.py /app/tests/
COPY deploy/railway/staging.py /app/deploy/railway/staging.py
ENV GATEWAY_HOST=0.0.0.0 GATEWAY_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["python", "deploy/railway/staging.py"]
