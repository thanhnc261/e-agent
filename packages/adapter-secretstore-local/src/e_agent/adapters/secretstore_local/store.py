"""Envelope encryption: each secret gets its own AES-256-GCM data key, which is
wrapped by a key-encryption key (KEK) held outside the repository and database.

The KEK comes from E_AGENT_SECRET_KEY (urlsafe base64, 32 bytes) or a key file.
Secret references look like ``secretref:local/<name>``; associated data binds
each ciphertext to its reference so blobs cannot be swapped between refs.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from e_agent.sdk.auth import Secret

PREFIX = "secretref:local/"


class SecretNotFound(KeyError):
    pass


def generate_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode())


class LocalSecretStore:
    def __init__(self, path: Path, kek: str) -> None:
        key = _unb64(kek)
        if len(key) != 32:
            raise ValueError("KEK must be 32 bytes (urlsafe base64)")
        self._kek = AESGCM(key)
        self._path = path

    @classmethod
    def from_environment(cls, path: Path | None = None) -> LocalSecretStore:
        kek = os.environ.get("E_AGENT_SECRET_KEY")
        key_file = os.environ.get("E_AGENT_SECRET_KEY_FILE")
        if not kek and key_file:
            kek = Path(key_file).read_text("utf-8").strip()
        if not kek:
            raise ValueError("set E_AGENT_SECRET_KEY or E_AGENT_SECRET_KEY_FILE")
        default = Path(os.environ.get("E_AGENT_SECRETS_PATH", "~/.e-agent/secrets.json"))
        return cls((path or default).expanduser(), kek)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        data: dict[str, dict[str, str]] = json.loads(self._path.read_text("utf-8"))
        return data

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), "utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)

    @staticmethod
    def _check(ref: str) -> None:
        if not ref.startswith(PREFIX) or len(ref) == len(PREFIX):
            raise ValueError(f"local secret refs look like {PREFIX}<name>")

    async def put(self, secret_ref: str, value: Secret) -> None:
        self._check(secret_ref)
        dek = AESGCM.generate_key(bit_length=256)
        nonce, wrap_nonce = secrets.token_bytes(12), secrets.token_bytes(12)
        aad = secret_ref.encode()
        data = self._load()
        data[secret_ref] = {
            "v": "1",
            "ct": _b64(AESGCM(dek).encrypt(nonce, value.reveal().encode(), aad)),
            "n": _b64(nonce),
            "wk": _b64(self._kek.encrypt(wrap_nonce, dek, aad)),
            "wn": _b64(wrap_nonce),
        }
        self._save(data)

    async def get(self, secret_ref: str) -> Secret:
        self._check(secret_ref)
        entry = self._load().get(secret_ref)
        if entry is None:
            raise SecretNotFound(secret_ref)
        aad = secret_ref.encode()
        dek = self._kek.decrypt(_unb64(entry["wn"]), _unb64(entry["wk"]), aad)
        plain = AESGCM(dek).decrypt(_unb64(entry["n"]), _unb64(entry["ct"]), aad)
        return Secret(plain.decode())

    async def delete(self, secret_ref: str) -> None:
        self._check(secret_ref)
        data = self._load()
        data.pop(secret_ref, None)
        self._save(data)
