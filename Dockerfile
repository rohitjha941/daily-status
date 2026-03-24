FROM python:3.12-alpine

ARG INFISICAL_VERSION=0.43.60

RUN apk add --no-cache bash curl github-cli && \
    case "$(apk --print-arch)" in \
      x86_64) infisical_arch=amd64 ;; \
      aarch64) infisical_arch=arm64 ;; \
      *) echo "unsupported architecture: $(apk --print-arch)" >&2; exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/infisical.apk \
      "https://github.com/Infisical/cli/releases/download/v${INFISICAL_VERSION}/infisical_${INFISICAL_VERSION}_linux_${infisical_arch}.apk" && \
    apk add --allow-untrusted --no-cache /tmp/infisical.apk && \
    rm -f /tmp/infisical.apk

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY daily_status.py .
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
