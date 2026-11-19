# reason phone: mobile-mcp (pinned) + adb, driving an Android device (Redroid) over TCP.
# Multi-arch (amd64, arm64): the lockfile carries mobilecli for both.
FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends adb ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/android/platform-tools \
    && ln -s /usr/bin/adb /opt/android/platform-tools/adb

ENV ANDROID_HOME=/opt/android

WORKDIR /opt/phone
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && rm -rf /root/.npm \
    && node /opt/phone/node_modules/@mobilenext/mobile-mcp/lib/index.js --version

COPY entrypoint.sh /usr/local/bin/reason-phone
RUN chmod 0755 /usr/local/bin/reason-phone && useradd --create-home --uid 10002 reason

USER reason
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/reason-phone"]
