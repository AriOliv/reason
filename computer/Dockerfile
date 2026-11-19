# reason computer: a virtual desktop with a visible Chromium, driven by Playwright MCP,
# watched (and taken over for logins) through noVNC. Multi-arch (amd64, arm64).
FROM node:22-bookworm-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       xvfb x11vnc openbox novnc websockify supervisor fonts-noto-color-emoji fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/computer
COPY package.json package-lock.json ./
# The browser comes from the MCP's own Playwright, so its revision always matches.
RUN npm ci --omit=dev --no-audit --no-fund \
    && npx --no-install playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm

COPY policy.json /etc/chromium/policies/managed/reason.json
COPY supervisord.conf /etc/supervisor/reason.conf
COPY reason-mcp /usr/local/bin/reason-mcp
COPY entrypoint.sh /usr/local/bin/reason-computer

RUN useradd --create-home --uid 10001 reason \
    && mkdir -p /data && chown reason:reason /data \
    && chmod 0755 /usr/local/bin/reason-mcp /usr/local/bin/reason-computer \
    && node /opt/computer/node_modules/@playwright/mcp/cli.js --version \
    && "$(find /ms-playwright -path '*chrome-linux*/chrome' -type f | head -1)" --version

USER reason
VOLUME /data
EXPOSE 8931 6080
ENTRYPOINT ["/usr/local/bin/reason-computer"]
