"""
Vector store service — OpenAI-managed vector stores for File Search.
All functions run the synchronous OpenAI SDK calls directly.
vector_store_id is stored in PostgreSQL (test_materials.vector_store_id).
"""
import logging

from app.services.llm_client import client, CLASSIFIER_MODEL

log = logging.getLogger(__name__)


async def create_vector_store(name: str) -> str:
    """
    Creates a new OpenAI vector store for a document.
    Returns the vector_store_id.
    """
    vs = client.vector_stores.create(name=name)
    log.info("Created vector store '%s' → id=%s", name, vs.id)
    return vs.id


async def delete_vector_store(vector_store_id: str) -> None:
    """Deletes a vector store and all its files."""
    client.vector_stores.delete(vector_store_id)
    log.info("Deleted vector store id=%s", vector_store_id)


async def upload_files_to_vector_store(
    vector_store_id: str,
    prepared_files: list[tuple[str, bytes]],
    batch_size: int = 20,
) -> tuple[int, int]:
    """
    Uploads files to a vector store in batches of `batch_size`.

    Args:
        vector_store_id: Target vector store.
        prepared_files: List of (filename, content_bytes) tuples.
        batch_size: Upload batch size (max 20 per OpenAI limits).

    Returns:
        (total_completed, total_failed) across all batches.
    """
    total_completed = 0
    total_failed = 0

    for start in range(0, len(prepared_files), batch_size):
        batch_slice = prepared_files[start : start + batch_size]
        files_batch = [
            (filename, content_bytes, "text/plain")
            for filename, content_bytes in batch_slice
        ]
        try:
            batch = client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store_id,
                files=files_batch,
            )
            completed = batch.file_counts.completed
            failed = batch.file_counts.failed
            total_completed += completed
            total_failed += failed
            log.info(
                "Vector store batch [%d:%d] — completed=%d failed=%d",
                start,
                start + len(batch_slice),
                completed,
                failed,
            )
            if failed > 0:
                log.warning(
                    "Batch [%d:%d] had %d failed uploads — continuing ingestion",
                    start,
                    start + len(batch_slice),
                    failed,
                )
        except Exception as exc:
            log.error(
                "Batch [%d:%d] upload error: %s — skipping batch",
                start,
                start + len(batch_slice),
                exc,
            )
            total_failed += len(batch_slice)

    log.info(
        "Vector store %s upload complete — total_completed=%d total_failed=%d",
        vector_store_id,
        total_completed,
        total_failed,
    )
    return total_completed, total_failed


async def retrieve_chunks(
    query: str,
    vector_store_id: str,
) -> list[str]:
    """
    Retrieves top 3 relevant chunks using OpenAI File Search via the Responses API.

    NOTE: scaffold parameter enrichment is NOT applied here.
    File Search does not support query injection. The raw query is used directly.
    previous_scaffold.parameters continue to flow to the evaluator LLM via
    session state for context continuity — they no longer influence retrieval.
    """
    log.info(
        "File Search query: %.50s | vector_store_id=%s",
        query,
        vector_store_id,
    )

    try:
        response = client.responses.create(
            model=CLASSIFIER_MODEL,  # nano — retrieval only, no evaluation
            input=query,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [vector_store_id],
                    "max_num_results": 3,
                }
            ],
        )

        chunks: list[str] = []
        output_items = response.output or []

        for item in output_items:
            # Pattern 1: ResponseFileSearchToolCall — item has .results list
            results = getattr(item, "results", None)
            if results:
                for result in results:
                    text = getattr(result, "text", None)
                    if text:
                        chunks.append(text)
                continue

            # Pattern 2: message content with file_search annotations
            content_list = getattr(item, "content", None) or []
            for block in content_list:
                annotations = getattr(block, "annotations", None) or []
                for ann in annotations:
                    if getattr(ann, "type", "") == "file_citation":
                        text = getattr(block, "text", None)
                        if text:
                            chunks.append(text)

        chunks = chunks[:3]
        log.info(
            "File Search retrieved %d chunks — previews: %s",
            len(chunks),
            [c[:50] for c in chunks],
        )
        return chunks

    except Exception as exc:
        log.error("File Search retrieval failed: %s", exc)
        return []

