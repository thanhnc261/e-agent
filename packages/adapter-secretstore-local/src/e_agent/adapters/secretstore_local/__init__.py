"""Local envelope-encrypted secret store (MVP). Replace with OpenBao/Vault/cloud later."""

from .store import LocalSecretStore, generate_key

__all__ = ["LocalSecretStore", "generate_key"]
