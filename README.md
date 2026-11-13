# MCP Contact Me

Serveur MCP privé permettant aux projets IA de Tanguy d'envoyer un e-mail ou un message Telegram.
Les destinataires sont configurés uniquement côté serveur : un client ne peut pas transformer le
service en relais vers une adresse arbitraire.

## Installation locale

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Renseigner ensuite les secrets dans `.env` (ce fichier est ignoré par Git), puis démarrer :

```powershell
mcp-contact-me
```

Le point d'entrée local est `http://127.0.0.1:8000/mcp`. Sur le VPS, Caddy expose
le point d'entrée public `https://mcp-contact-me.tanguym.fr/mcp`.

Toutes les requêtes doivent fournir l'en-tête suivant :

```text
Authorization: Bearer <CONTACT_API_TOKEN>
```

Le serveur refuse de démarrer si le jeton n'est pas configuré ou s'il contient moins de
32 caractères.

## Outils exposés

- `send_email(subject, message, urgency)`
- `send_telegram(subject, message, urgency)`

`urgency` accepte `low`, `normal` ou `high`.
Le nom du projet est déterminé par son jeton et ne peut pas être fourni par le client.

## Jetons par projet

Le registre ne conserve que les empreintes SHA-256 des jetons. Sur le VPS, exécuter les
commandes avec l'utilisateur du service :

```bash
cd /srv/mcp_contact_me
sudo -u mcp-contact-me .venv/bin/mcp-contact-token list
sudo -u mcp-contact-me .venv/bin/mcp-contact-token create mon-projet
sudo -u mcp-contact-me .venv/bin/mcp-contact-token rotate mon-projet
sudo -u mcp-contact-me .venv/bin/mcp-contact-token revoke mon-projet
```

Les commandes `create` et `rotate` affichent le secret une seule fois. Les quotas combinés
e-mail/Telegram sont de 5 envois par minute et 50 sur 24 heures pour chaque projet.
Le journal `data/audit.log` contient uniquement la date, le projet, le canal et le résultat.

## Tests

```powershell
pytest
```

Les tests simulent les transports : ils n'envoient aucun vrai message.

## Déploiement HTTPS sur le VPS

Le serveur Python ne doit pas être exposé directement sur Internet. Il écoute uniquement sur
`127.0.0.1:8000` et Caddy termine la connexion HTTPS :

```text
Client MCP -> https://mcp-contact-me.tanguym.fr/mcp -> Caddy -> http://127.0.0.1:8000/mcp
```

Pré-requis DNS : créer un enregistrement `A` (et éventuellement `AAAA`) pour
`mcp-contact-me.tanguym.fr` pointant vers le VPS. Les ports 80 et 443 doivent être ouverts ; Caddy utilise
le port 80 pour obtenir et renouveler automatiquement le certificat Let's Encrypt.

Les fichiers de déploiement fournis sont :

- `deploy/Caddyfile`, dont le bloc doit être **ajouté** au Caddyfile existant sans l'écraser ;
- `deploy/mcp-contact-me.service`, à installer dans `/etc/systemd/system/`.
- `deploy/install-vps.sh`, qui installe le projet, valide Caddy et crée une sauvegarde avant modification.

Le projet est prévu dans `/srv/mcp_contact_me` et s'exécute avec un compte système dédié
`mcp-contact-me`. Après installation :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mcp-contact-me
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Si le sous-domaine final est différent, le remplacer à la fois dans le Caddyfile et dans
`CONTACT_ALLOWED_HOSTS`.

## Avant l'ouverture publique

- ne jamais committer `.env` ;
- ajouter une limitation de débit et conserver les journaux d'envoi.
