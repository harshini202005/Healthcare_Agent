import os
from mistralai import Mistral

_client = None


def _get_client() -> Mistral:
    global _client
    if _client is None:
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key or api_key == "your-mistral-api-key-here":
            raise ValueError("MISTRAL_API_KEY not configured")
        _client = Mistral(api_key=api_key)
    return _client


def embed(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    response = client.embeddings.create(model="mistral-embed", inputs=texts)
    return [item.embedding for item in response.data]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
