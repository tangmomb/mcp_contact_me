#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/srv/mcp_contact_me"
SERVICE_USER="mcp-contact-me"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CADDYFILE="/etc/caddy/Caddyfile"
DOMAIN="mcp-contact-me.tanguym.fr"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Ce script doit être exécuté avec sudo." >&2
    exit 1
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --home-dir "${APP_ROOT}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

install -d -o root -g "${SERVICE_USER}" -m 0750 "${APP_ROOT}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${APP_ROOT}/data"
install -d -o root -g caddy -m 0755 "/var/www/mcp-contact-me"
cp -a "${SOURCE_DIR}/src" "${APP_ROOT}/"
cp -a "${SOURCE_DIR}/pyproject.toml" "${SOURCE_DIR}/README.md" "${APP_ROOT}/"
install -o root -g "${SERVICE_USER}" -m 0640 "${SOURCE_DIR}/.env" "${APP_ROOT}/.env"
install -o root -g caddy -m 0644 "${SOURCE_DIR}/public/index.html" "/var/www/mcp-contact-me/index.html"

python3 -m venv "${APP_ROOT}/.venv"
"${APP_ROOT}/.venv/bin/python" -m pip install --upgrade pip
"${APP_ROOT}/.venv/bin/python" -m pip install "${APP_ROOT}"

install -o root -g root -m 0644 \
    "${SOURCE_DIR}/deploy/mcp-contact-me.service" \
    "/etc/systemd/system/mcp-contact-me.service"
systemctl daemon-reload
systemctl enable --now mcp-contact-me.service

if ! grep -qF "${DOMAIN}" "${CADDYFILE}"; then
    candidate="$(mktemp)"
    trap 'rm -f "${candidate:-}"' EXIT
    cp "${CADDYFILE}" "${candidate}"
    printf '\n' >> "${candidate}"
    sed '1{/^# Bloc à ajouter/d;}' "${SOURCE_DIR}/deploy/Caddyfile" >> "${candidate}"
    caddy validate --config "${candidate}" --adapter caddyfile
    cp -a "${CADDYFILE}" "${CADDYFILE}.backup-$(date +%Y%m%d-%H%M%S)"
    install -o root -g root -m 0644 "${candidate}" "${CADDYFILE}"
fi

caddy validate --config "${CADDYFILE}"
systemctl reload caddy.service
systemctl --no-pager --full status mcp-contact-me.service
