#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/srv/mcp_contact_me"
REPO_DIR="${APP_ROOT}/repo"
REPO_URL="https://github.com/tangmomb/mcp_contact_me.git"
REVISION_FILE="${APP_ROOT}/deployed_revision"
PUBLIC_FILE="/var/www/mcp-contact-me/index.html"
LOCK_FILE="/run/lock/mcp-contact-me-deploy.lock"

if [[ ! "${1:-}" =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
    echo "Commande de déploiement invalide." >&2
    exit 1
fi
requested_revision="${BASH_REMATCH[1]}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    echo "Un déploiement est déjà en cours." >&2
    exit 1
fi

if [[ ! -d "${REPO_DIR}/.git" ]]; then
    git clone --branch main "${REPO_URL}" "${REPO_DIR}"
else
    if [[ "$(realpath -m "${REPO_DIR}")" != "${REPO_DIR}" ]]; then
        echo "Chemin du dépôt inattendu." >&2
        exit 1
    fi
    git -C "${REPO_DIR}" fetch --prune origin main
fi

if ! git -C "${REPO_DIR}" cat-file -e "${requested_revision}^{commit}" 2>/dev/null; then
    echo "Révision demandée introuvable." >&2
    exit 1
fi
if ! git -C "${REPO_DIR}" merge-base --is-ancestor "${requested_revision}" origin/main; then
    echo "La révision demandée n'appartient pas à la branche main." >&2
    exit 1
fi

git -C "${REPO_DIR}" checkout --force --detach "${requested_revision}"
git -C "${REPO_DIR}" clean -fdx
new_revision="${requested_revision}"
previous_revision=""
if [[ -f "${REVISION_FILE}" ]]; then
    previous_revision="$(<"${REVISION_FILE}")"
fi

if [[ "${new_revision}" == "${previous_revision}" ]]; then
    echo "Révision ${new_revision} déjà déployée."
    exit 0
fi

page_backup="$(mktemp)"
trap 'rm -f "${page_backup}"' EXIT
cp "${PUBLIC_FILE}" "${page_backup}"

rollback() {
    echo "Échec du contrôle de santé, restauration de ${previous_revision}." >&2
    if [[ -n "${previous_revision}" ]] && git -C "${REPO_DIR}" cat-file -e "${previous_revision}^{commit}"; then
        git -C "${REPO_DIR}" checkout --force "${previous_revision}"
        "${APP_ROOT}/.venv/bin/python" -m pip install --disable-pip-version-check --no-input "${REPO_DIR}"
        install -o root -g caddy -m 0644 "${page_backup}" "${PUBLIC_FILE}"
        systemctl restart mcp-contact-me.service
    fi
    exit 1
}

"${APP_ROOT}/.venv/bin/python" -m compileall -q "${REPO_DIR}/src"
"${APP_ROOT}/.venv/bin/python" -m pip install --disable-pip-version-check --no-input "${REPO_DIR}"
install -o root -g caddy -m 0644 "${REPO_DIR}/public/index.html" "${PUBLIC_FILE}"
systemctl restart mcp-contact-me.service

healthy=false
for _ in {1..20}; do
    if systemctl is-active --quiet mcp-contact-me.service; then
        status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
            --max-time 5 --header 'Host: mcp-contact-me.tanguym.fr' \
            http://127.0.0.1:8000/mcp || true)"
        if [[ "${status}" == "401" ]]; then
            healthy=true
            break
        fi
    fi
    sleep 0.5
done

if [[ "${healthy}" != true ]]; then
    rollback
fi

printf '%s\n' "${new_revision}" > "${REVISION_FILE}.tmp"
mv "${REVISION_FILE}.tmp" "${REVISION_FILE}"
echo "Révision ${new_revision} déployée avec succès."
