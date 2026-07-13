"""Vision config validation utilities.

Centralises Vision provider config validation that was previously duplicated
across the indexer and API route handlers.
"""

from __future__ import annotations

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore


class VisionConfigError(Exception):
    """Vision provider 配置缺失或无效。"""


def validate_vision_config(
    config_reader: ConfigReader,
    secret_store: SecretStore,
    *,
    product_id: str | None = None,
) -> None:
    """Validate that Vision provider config is complete.

    Reads the provider name from *config_reader*, resolves the API key, endpoint
    and model through *secret_store*, and raises ``VisionConfigError`` if any
    required field is missing or empty.

    Parameters
    ----------
    config_reader:
        Application config reader.
    secret_store:
        Environment-variable-based secret store.
    product_id:
        Optional product ID for product-scoped config overrides.

    Raises
    ------
    VisionConfigError
        If any required field (provider, endpoint, model, api_key) is missing or
        empty.
    """
    config = config_reader.get_vision_config(product_id=product_id)
    provider = config.get("provider", "")

    api_key = secret_store.get_vision_api_key(config_reader, product_id=product_id)
    endpoint = secret_store.get_vision_endpoint(config_reader, product_id=product_id)
    model = secret_store.get_vision_model(config_reader, product_id=product_id)

    missing: list[str] = []
    if not provider:
        missing.append("provider")
    if not endpoint:
        missing.append("endpoint")
    if not api_key:
        missing.append("api_key")
    if not model:
        missing.append("model")

    if missing:
        msg = f"Vision 配置不完整，缺失字段: {', '.join(missing)}"
        raise VisionConfigError(msg)
