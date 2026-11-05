# The digest pins the CPU runtime and all native libraries, including AVX2 kernels.
FROM vllm/vllm-openai-cpu:v0.27.0-x86_64@sha256:ad2d073b2ff1b755e0d0b9e33a581bfcbadde22c13a073af1dfff1d553119d38
USER root
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY scripts/check_dependencies.py /app/check_dependencies.py
# All packages are already present in the immutable base. No resolver/network
# is used: verify the entire installed set, including transitive dependencies.
RUN python /app/check_dependencies.py /app/requirements.txt \
    && groupadd --gid 10001 inference \
    && useradd --uid 10001 --gid 10001 --create-home inference \
    && mkdir -p /models/model && chown -R 10001:10001 /models /app
COPY --chown=10001:10001 scripts/privacy_logging.py /app/privacy_logging.py
COPY --chown=10001:10001 config/logging.json /app/config/logging.json
ENV HOME=/tmp \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    VLLM_NO_USAGE_STATS=1 \
    VLLM_LOGGING_CONFIG_PATH=/app/config/logging.json \
    VLLM_CPU_KVCACHE_SPACE=1 \
    VLLM_CPU_OMP_THREADS_BIND=nobind \
    OMP_NUM_THREADS=4
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["vllm"]
