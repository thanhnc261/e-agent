import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from e_agent.adapters.secretstore_local import LocalSecretStore, generate_key
from e_agent.sdk.auth import Secret

pytestmark = pytest.mark.asyncio
CANARY = "odoo-api-key-CANARY-91f2"


async def test_round_trip_and_ciphertext_hides_value(tmp_path: Path) -> None:
    store = LocalSecretStore(tmp_path / "s.json", generate_key())
    await store.put("secretref:local/odoo", Secret(CANARY))
    assert (await store.get("secretref:local/odoo")).reveal() == CANARY
    assert CANARY not in (tmp_path / "s.json").read_text()
    assert (tmp_path / "s.json").stat().st_mode & 0o077 == 0


async def test_wrong_key_cannot_decrypt(tmp_path: Path) -> None:
    await LocalSecretStore(tmp_path / "s.json", generate_key()).put(
        "secretref:local/a", Secret("x")
    )
    with pytest.raises(InvalidTag):
        await LocalSecretStore(tmp_path / "s.json", generate_key()).get("secretref:local/a")


async def test_ciphertexts_cannot_be_swapped_between_refs(tmp_path: Path) -> None:
    store = LocalSecretStore(tmp_path / "s.json", generate_key())
    await store.put("secretref:local/a", Secret("aaa"))
    await store.put("secretref:local/b", Secret("bbb"))
    data = json.loads((tmp_path / "s.json").read_text())
    data["secretref:local/a"] = data["secretref:local/b"]
    (tmp_path / "s.json").write_text(json.dumps(data))
    with pytest.raises(InvalidTag):
        await store.get("secretref:local/a")


async def test_secret_repr_is_redacted() -> None:
    assert CANARY not in repr(Secret(CANARY)) and CANARY not in str(Secret(CANARY))


async def test_invalid_refs_rejected(tmp_path: Path) -> None:
    store = LocalSecretStore(tmp_path / "s.json", generate_key())
    with pytest.raises(ValueError, match="secretref"):
        await store.put("plain-name", Secret("x"))
