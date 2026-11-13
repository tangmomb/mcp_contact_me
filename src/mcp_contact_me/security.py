import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


class TokenRegistry:
    """Registre de jetons hachés, relu pour permettre la révocation immédiate."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_project(project: str) -> str:
        project = project.strip().lower()
        if not PROJECT_PATTERN.fullmatch(project):
            raise ValueError(
                "Le projet doit contenir 2 à 64 caractères : lettres minuscules, chiffres, _ ou -."
            )
        return project

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "projects": {}}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("version") != 1 or not isinstance(data.get("projects"), dict):
            raise ValueError("Format du registre de jetons invalide.")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def import_token(self, project: str, token: str, *, only_if_missing: bool = False) -> None:
        if len(token) < 32:
            raise ValueError("Un jeton doit contenir au moins 32 caractères.")
        project = self._validate_project(project)
        with self._lock:
            data = self._read()
            if only_if_missing and project in data["projects"]:
                return
            data["projects"][project] = {
                "token_hash": self._hash(token),
                "enabled": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
            self._write(data)

    def create(self, project: str, *, replace: bool = False) -> str:
        project = self._validate_project(project)
        token = secrets.token_urlsafe(48)
        with self._lock:
            data = self._read()
            if project in data["projects"] and not replace:
                raise ValueError(f"Le projet {project!r} existe déjà. Utiliser rotate.")
            data["projects"][project] = {
                "token_hash": self._hash(token),
                "enabled": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
            self._write(data)
        return token

    def revoke(self, project: str) -> None:
        project = self._validate_project(project)
        with self._lock:
            data = self._read()
            if project not in data["projects"]:
                raise ValueError(f"Projet inconnu : {project}")
            data["projects"][project]["enabled"] = False
            data["projects"][project]["revoked_at"] = datetime.now(UTC).isoformat()
            self._write(data)

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            projects = self._read()["projects"]
        return [
            {
                "project": project,
                "enabled": bool(record.get("enabled")),
                "created_at": record.get("created_at"),
                "revoked_at": record.get("revoked_at"),
            }
            for project, record in sorted(projects.items())
        ]

    def verify_authorization(self, authorization: str | None) -> str | None:
        if not authorization:
            return None
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer":
            return None
        if len(token) < 32:
            return None
        candidate = self._hash(token)
        with self._lock:
            projects = self._read()["projects"]

        matched_project: str | None = None
        for project, record in projects.items():
            is_match = secrets.compare_digest(candidate, str(record.get("token_hash", "")))
            if is_match and record.get("enabled") is True:
                matched_project = project
        return matched_project


class RateLimitExceededError(RuntimeError):
    pass


class DeliveryRateLimiter:
    """Quota persistant et combiné pour les deux canaux."""

    def __init__(self, path: Path, per_minute: int, per_day: int) -> None:
        self.path = path
        self.per_minute = per_minute
        self.per_day = per_day
        self._lock = threading.Lock()

    def check_and_record(self, project: str, *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS deliveries (project TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS deliveries_project_time ON deliveries(project, created_at)"
            )
            connection.execute("DELETE FROM deliveries WHERE created_at < ?", (timestamp - 86400,))
            minute_count = connection.execute(
                "SELECT COUNT(*) FROM deliveries WHERE project = ? AND created_at >= ?",
                (project, timestamp - 60),
            ).fetchone()[0]
            day_count = connection.execute(
                "SELECT COUNT(*) FROM deliveries WHERE project = ? AND created_at >= ?",
                (project, timestamp - 86400),
            ).fetchone()[0]
            if minute_count >= self.per_minute:
                raise RateLimitExceededError(
                    f"Limite atteinte : {self.per_minute} envois par minute pour ce projet."
                )
            if day_count >= self.per_day:
                raise RateLimitExceededError(
                    f"Limite atteinte : {self.per_day} envois sur 24 heures pour ce projet."
                )
            connection.execute(
                "INSERT INTO deliveries(project, created_at) VALUES (?, ?)", (project, timestamp)
            )
        os.chmod(self.path, 0o600)


class AuditLogger:
    """Journal JSON sans jeton, sujet ni contenu de message."""

    def __init__(self, path: Path, max_bytes: int = 5_000_000, backups: int = 5) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups
        self._lock = threading.Lock()

    def _rotate_if_needed(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.backups}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backups - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
        self.path.replace(self.path.with_name(f"{self.path.name}.1"))

    def write(
        self,
        *,
        project: str,
        channel: str,
        status: str,
        request_id: str,
        error_type: str | None = None,
    ) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "project": project,
            "channel": channel,
            "status": status,
            "request_id": request_id,
        }
        if error_type:
            event["error_type"] = error_type
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._rotate_if_needed()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            os.chmod(self.path, 0o600)
