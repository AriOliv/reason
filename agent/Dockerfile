# reason agent image: Hermes Agent (pinned by digest) + reason_flow + config templates.
# Nothing personal is baked in: the owner, model and keys come from the environment at boot.
FROM nousresearch/hermes-agent:v0.23.0@sha256:adb7890916de63245523492be8f68f9d2095fecbec4e2a6dab7960381f0fc002

USER root

# WhatsApp bridge dependencies at build time (Hermes' own lockfile) plus the stamp its
# adapter checks, so no `npm install` ever runs inside a live agent.
RUN cd /opt/hermes/scripts/whatsapp-bridge \
    && npm ci --omit=dev --no-audit --no-fund --fetch-retries=5 \
    && /opt/hermes/.venv/bin/python -c "import hashlib, pathlib; p = pathlib.Path('package.json'); pathlib.Path('node_modules/.hermes-pkg-hash').write_text(hashlib.sha256(p.read_bytes()).hexdigest()[:16])"

COPY reason_flow /opt/hermes/gateway/reason_flow
COPY patches /opt/reason/patches
COPY config /opt/reason/config
COPY cont-init.d/005-reason-seed /etc/cont-init.d/005-reason-seed
COPY tests /opt/reason/tests

# Patch Hermes, then test against the real, patched Hermes: the build fails if anything is off.
RUN /opt/hermes/.venv/bin/python /opt/reason/patches/apply.py \
    && cd /opt/hermes && /opt/hermes/.venv/bin/python -m unittest discover -s /opt/reason/tests -v \
    && chmod 0755 /etc/cont-init.d/005-reason-seed \
    && chmod -R a+rX,go-w /opt/hermes/gateway/reason_flow /opt/reason /opt/hermes/scripts/whatsapp-bridge

ENV REASON_REACTIONS=1 \
    REASON_NATURAL_TYPING=1 \
    REASON_FOLLOWUPS=1 \
    REASON_SPLIT_REPLIES=1 \
    REASON_SPLIT_PAUSE=0.8 \
    HERMES_TELEGRAM_TEXT_BATCH_DELAY_SECONDS=1.5
