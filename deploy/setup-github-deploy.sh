#!/usr/bin/env bash
set -euo pipefail

PUBLIC_KEY_FILE="${1:?Usage: setup-github-deploy.sh /path/to/public-key}"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Ce script doit être exécuté avec les droits root." >&2
    exit 1
fi

if [[ ! -s "${PUBLIC_KEY_FILE}" ]]; then
    echo "Clé publique absente ou vide." >&2
    exit 1
fi

if ! id mcp-deploy >/dev/null 2>&1; then
    useradd --system --create-home --home-dir /var/lib/mcp-deploy --shell /bin/bash mcp-deploy
fi

# OpenSSH refuse les comptes verrouillés avant même de vérifier authorized_keys.
# Le mot de passe aléatoire n'est jamais conservé et l'authentification par mot
# de passe est désactivée explicitement pour ce compte.
if passwd -S mcp-deploy | grep -q ' L '; then
    random_password_hash="$(openssl rand -base64 48 | openssl passwd -6 -stdin)"
    usermod --password "${random_password_hash}" mcp-deploy
    unset random_password_hash
fi

cat > /etc/ssh/sshd_config.d/90-mcp-deploy.conf <<'EOF'
Match User mcp-deploy
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowTcpForwarding no
    X11Forwarding no
    PermitTunnel no
Match all
EOF
chmod 0644 /etc/ssh/sshd_config.d/90-mcp-deploy.conf
sshd -t
systemctl reload ssh

install -o root -g root -m 0755 /tmp/deploy-from-github.sh /usr/local/sbin/deploy-mcp-contact-me
visudo -cf /tmp/mcp-contact-me.sudoers
install -o root -g root -m 0440 /tmp/mcp-contact-me.sudoers /etc/sudoers.d/mcp-contact-me-deploy

install -d -o mcp-deploy -g mcp-deploy -m 0700 /var/lib/mcp-deploy/.ssh
{
    printf '%s ' 'restrict,command="sudo -n /usr/local/sbin/deploy-mcp-contact-me \"$SSH_ORIGINAL_COMMAND\""'
    cat "${PUBLIC_KEY_FILE}"
} > /var/lib/mcp-deploy/.ssh/authorized_keys
chown mcp-deploy:mcp-deploy /var/lib/mcp-deploy/.ssh/authorized_keys
chmod 0600 /var/lib/mcp-deploy/.ssh/authorized_keys

echo "Accès GitHub Actions restreint installé."
