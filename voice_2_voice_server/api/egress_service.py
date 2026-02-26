"""LiveKit Egress service for recording call audio to S3/MinIO."""

import os
import json
import logging
from typing import Optional, Dict, Any

from loguru import logger
import livekit.api as lk_api
from livekit.protocol import egress as lk_egress

from storage.minio_client import MinIOStorage

logger = logging.getLogger(__name__)


def _get_livekit_credentials() -> tuple[str, str, str]:
    """Get LiveKit credentials from environment."""
    url = os.getenv("LIVEKIT_URL", "")
    key = os.getenv("LIVEKIT_API_KEY", "")
    secret = os.getenv("LIVEKIT_API_SECRET", "")
    if not all([url, key, secret]):
        raise ValueError(
            "Missing LiveKit credentials: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET"
        )
    return url, key, secret


def _get_minio_s3_config() -> Dict[str, str]:
    """Get MinIO credentials formatted for S3 upload."""
    return {
        "access_key": os.getenv("MINIO_ACCESS_KEY", ""),
        "secret": os.getenv("MINIO_SECRET_KEY", ""),
        "endpoint": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        "bucket": os.getenv("MINIO_RECORDINGS_BUCKET", "recordings"),
        "region": os.getenv("MINIO_REGION", "us-east-1"),
    }


async def start_room_audio_egress(
    room_name: str,
    call_sid: str,
    audio_format: str = "mp3",
) -> Optional[str]:
    """
    Start recording the room's audio using LiveKit Egress.

    Records all audio tracks mixed together and saves to S3/MinIO.

    Args:
        room_name: The LiveKit room name to record
        call_sid: Call identifier for naming the output file
        audio_format: Output format (mp3, wav, ogg)

    Returns:
        Egress ID if started successfully, None otherwise
    """
    try:
        url, key, secret = _get_livekit_credentials()

        # Get MinIO/S3 config
        s3_config = _get_minio_s3_config()

        # Determine file type based on format
        file_type_map = {
            "mp3": lk_egress.EncodedFileType.MP3,
            "wav": lk_egress.EncodedFileType.OGG,
            "ogg": lk_egress.EncodedFileType.OGG,
        }
        file_type = file_type_map.get(
            audio_format.lower(), lk_egress.EncodedFileType.MP3
        )

        # Create S3 upload config for MinIO (S3-compatible)
        # Note: For MinIO, we use the endpoint and force_path_style=true
        s3_upload = lk_egress.S3Upload(
            access_key=s3_config["access_key"],
            secret=s3_config["secret"],
            bucket=s3_config["bucket"],
            endpoint=s3_config["endpoint"],  # MinIO endpoint
            region=s3_config["region"],
            force_path_style=True,  # Required for MinIO
        )

        # Output filename template
        filepath = f"calls/{call_sid}.{audio_format}"

        # Create file output
        file_output = lk_egress.EncodedFileOutput(
            file_type=file_type,
            filepath=filepath,
            s3=s3_upload,
        )

        # Build the egress request for track composite (audio only)
        request = lk_egress.StartTrackCompositeEgressRequest(
            room_name=room_name,
            audio_only=True,
            audio_mixing=lk_egress.AudioMixing.DEFAULT_MIXING,
            file_outputs=[file_output],
        )

        logger.info(f"Starting audio egress for room: {room_name}, file: {filepath}")

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            result = await lk.egress.start_track_composite_egress(request)
            egress_id = result.egress_id
            logger.info(f"Started egress: {egress_id} for room: {room_name}")
            return egress_id

    except ValueError as e:
        logger.error(f"Missing credentials for egress: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to start egress: {e}")
        import traceback

        logger.debug(traceback.format_exc())
        return None


async def stop_egress(egress_id: str) -> Optional[Dict[str, Any]]:
    """
    Stop an active egress.

    Args:
        egress_id: The ID of the egress to stop

    Returns:
        Egress info if stopped successfully, None otherwise
    """
    try:
        url, key, secret = _get_livekit_credentials()

        request = lk_egress.StopEgressRequest(egress_id=egress_id)

        logger.info(f"Stopping egress: {egress_id}")

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            result = await lk.egress.stop_egress(request)
            logger.info(f"Stopped egress: {egress_id}")
            return _parse_egress_info(result)

    except Exception as e:
        logger.error(f"Failed to stop egress {egress_id}: {e}")
        return None


async def get_egress_info(egress_id: str) -> Optional[Dict[str, Any]]:
    """
    Get information about an egress.

    Args:
        egress_id: The ID of the egress

    Returns:
        Egress info dict or None
    """
    try:
        url, key, secret = _get_livekit_credentials()

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            # List egress and find the one we want
            list_request = lk_egress.ListEgressRequest(
                egress_id=egress_id,
            )
            list_result = await lk.egress.list_egress(list_request)

            for item in list_result.items:
                if item.egress_id == egress_id:
                    return _parse_egress_info(item)

        return None

    except Exception as e:
        logger.error(f"Failed to get egress info: {e}")
        return None


async def wait_for_egress_completion(
    egress_id: str, timeout: int = 300
) -> Optional[Dict[str, Any]]:
    """
    Wait for egress to complete and return the final info.

    Args:
        egress_id: The ID of the egress
        timeout: Maximum seconds to wait

    Returns:
        Final egress info or None on timeout/error
    """
    import asyncio

    start_time = asyncio.get_event_loop().time()

    while True:
        info = await get_egress_info(egress_id)
        if not info:
            return None

        status = info.get("status", "")

        if status == "EGRESS_COMPLETE":
            logger.info(f"Egress {egress_id} completed")
            return info
        elif status in ("EGRESS_FAILED", "EGRESS_ABORTED", "EGRESS_LIMIT_REACHED"):
            logger.error(f"Egress {egress_id} ended with status: {status}")
            return info

        # Check timeout
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            logger.warning(f"Egress {egress_id} timed out after {timeout}s")
            await stop_egress(egress_id)
            return None

        # Wait before checking again
        await asyncio.sleep(2)


def _parse_egress_info(info) -> Dict[str, Any]:
    """Parse egress info into a dict."""
    result = {
        "egress_id": info.egress_id,
        "room_name": info.room_name,
        "status": info.status.name
        if hasattr(info.status, "name")
        else str(info.status),
        "started_at": info.started_at,
        "ended_at": info.ended_at,
    }

    # Extract file results if available
    if hasattr(info, "file_results") and info.file_results:
        result["files"] = []
        for file_info in info.file_results:
            result["files"].append(
                {
                    "filename": file_info.filename,
                    "location": file_info.location,
                    "duration": file_info.duration,
                    "size": file_info.size,
                }
            )

    return result


async def upload_transcript_json(
    storage: MinIOStorage,
    call_sid: str,
    transcript_data: Dict[str, Any],
) -> str:
    """
    Save transcript as JSON to MinIO.

    Args:
        storage: MinIOStorage instance
        call_sid: Call identifier
        transcript_data: Transcript data dict

    Returns:
        Object name in MinIO
    """
    import asyncio
    import io

    json_content = json.dumps(transcript_data, indent=2)
    json_bytes = json_content.encode("utf-8")
    buffer = io.BytesIO(json_bytes)

    object_name = f"transcripts/{call_sid}.json"

    await asyncio.to_thread(
        storage.client.put_object,
        bucket_name="transcripts",
        object_name=object_name,
        data=buffer,
        length=len(json_bytes),
        content_type="application/json",
    )

    logger.info(f"Saved transcript JSON: minio://transcripts/{object_name}")
    return object_name
