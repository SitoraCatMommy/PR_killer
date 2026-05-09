from fastapi import HTTPException, UploadFile, status

DEFAULT_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


async def read_upload_file_with_limit(
    file: UploadFile,
    *,
    max_bytes: int,
    chunk_bytes: int = DEFAULT_UPLOAD_READ_CHUNK_BYTES,
) -> bytes:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if chunk_bytes < 1:
        raise ValueError("chunk_bytes must be positive")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(chunk_bytes)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "upload_too_large",
                    "message": f"Upload exceeds configured limit of {max_bytes} bytes.",
                    "max_bytes": max_bytes,
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)
