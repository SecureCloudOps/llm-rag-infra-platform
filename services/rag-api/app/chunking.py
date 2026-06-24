DEFAULT_CHUNK_SIZE = 500


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    """Split text into ordered, fixed-size chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]
