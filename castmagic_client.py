"""
Cast Magic API Client for Patty's Knowledge Brain

Handles transcription requests and content retrieval from Cast Magic.
API Docs: https://docs.castmagic.io
"""

import requests
import time
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CastMagicTranscript:
    """Represents a Cast Magic transcript with metadata."""
    id: str
    status: str  # "pending", "processing", "completed", "error"
    title: Optional[str]
    duration_seconds: Optional[float]
    language: Optional[str]
    transcript_text: Optional[str]
    utterances: list[dict]  # Speaker-labeled segments
    created_at: datetime
    source_url: str


class CastMagicClient:
    """Client for interacting with the Cast Magic API."""

    BASE_URL = "https://app.castmagic.io/v1"

    def __init__(self, api_secret: str):
        """
        Initialize the Cast Magic client.

        Args:
            api_secret: Cast Magic API secret (Bearer token)
        """
        self.api_secret = api_secret
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_secret}",
            "Content-Type": "application/json"
        })

    def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict:
        """Make an authenticated request to the Cast Magic API."""
        url = f"{self.BASE_URL}{endpoint}"

        if method == "GET":
            response = self._session.get(url)
        elif method == "POST":
            response = self._session.post(url, json=data)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response.raise_for_status()
        return response.json()

    def test_connection(self) -> tuple[bool, str]:
        """
        Test if the API credentials are valid.

        Returns:
            Tuple of (success, message)
        """
        try:
            # Try to list transcripts to verify credentials
            self._make_request("GET", "/transcripts")
            return True, "Connected to Cast Magic!"
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return False, "Invalid API secret"
            return False, f"HTTP Error: {e}"
        except Exception as e:
            return False, f"Connection error: {e}"

    def submit_transcription(
        self,
        url: str,
        language_code: str = "en",
        auto_detect_language: bool = False,
        boosted_words: Optional[list[str]] = None
    ) -> tuple[bool, str, Optional[str]]:
        """
        Submit an audio/video URL for transcription.

        Args:
            url: URL to audio/video file (aac, m4a, mp4, mpeg, wav, or YouTube)
            language_code: Language code (default "en")
            auto_detect_language: Whether to auto-detect language
            boosted_words: List of words to boost recognition for

        Returns:
            Tuple of (success, message, transcript_id)
        """
        try:
            data = {"url": url}

            if language_code and language_code != "en":
                data["language_code"] = language_code

            if auto_detect_language:
                data["auto_detect_language"] = True

            if boosted_words:
                data["boosted_words"] = boosted_words

            response = self._make_request("POST", "/transcripts", data)
            transcript_id = response.get("id")

            if transcript_id:
                return True, "Transcription submitted successfully!", transcript_id
            else:
                return False, "No transcript ID returned", None

        except requests.exceptions.HTTPError as e:
            return False, f"Submission failed: {e}", None
        except Exception as e:
            return False, f"Error: {e}", None

    def get_transcript(self, transcript_id: str) -> Optional[CastMagicTranscript]:
        """
        Get a transcript by ID.

        Args:
            transcript_id: The transcript ID

        Returns:
            CastMagicTranscript object or None if not found
        """
        try:
            response = self._make_request("GET", f"/transcripts/{transcript_id}")

            # Parse utterances (speaker-labeled segments)
            utterances = response.get("utterances", [])

            # Combine utterances into full transcript text
            transcript_text = ""
            if utterances:
                for utterance in utterances:
                    speaker = utterance.get("speaker", "Unknown")
                    text = utterance.get("text", "")
                    transcript_text += f"[{speaker}]: {text}\n\n"

            return CastMagicTranscript(
                id=response.get("id", transcript_id),
                status=response.get("status", "unknown"),
                title=response.get("title"),
                duration_seconds=response.get("duration_seconds"),
                language=response.get("language"),
                transcript_text=transcript_text.strip() if transcript_text else None,
                utterances=utterances,
                created_at=datetime.now(),  # API may provide this
                source_url=response.get("url", "")
            )

        except requests.exceptions.HTTPError:
            return None
        except Exception:
            return None

    def list_transcripts(self, limit: int = 50) -> list[dict]:
        """
        List recent transcripts.

        Args:
            limit: Maximum number to return

        Returns:
            List of transcript metadata dicts
        """
        try:
            response = self._make_request("GET", "/transcripts")
            transcripts = response if isinstance(response, list) else response.get("transcripts", [])
            return transcripts[:limit]
        except Exception:
            return []

    def wait_for_completion(
        self,
        transcript_id: str,
        timeout_minutes: int = 20,
        poll_interval_seconds: int = 5,
        progress_callback=None
    ) -> tuple[bool, str, Optional[CastMagicTranscript]]:
        """
        Wait for a transcript to complete (polling).

        Args:
            transcript_id: The transcript ID to wait for
            timeout_minutes: Maximum time to wait
            poll_interval_seconds: Time between status checks
            progress_callback: Optional callback(status, message)

        Returns:
            Tuple of (success, message, transcript)
        """
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                return False, "Timeout waiting for transcription", None

            transcript = self.get_transcript(transcript_id)
            if not transcript:
                return False, "Failed to retrieve transcript status", None

            status = transcript.status

            if progress_callback:
                minutes_elapsed = int(elapsed / 60)
                progress_callback(status, f"Status: {status} ({minutes_elapsed}m elapsed)")

            if status == "completed":
                return True, "Transcription completed!", transcript

            if status == "error":
                return False, "Transcription failed with error", transcript

            time.sleep(poll_interval_seconds)

    def transcript_to_text(self, transcript: CastMagicTranscript) -> str:
        """Convert a transcript to searchable text format for the Knowledge Brain."""
        parts = [
            f"=== CAST MAGIC TRANSCRIPT: {transcript.title or 'Untitled'} ===",
            f"Source: {transcript.source_url}",
            f"Language: {transcript.language or 'Unknown'}",
        ]

        if transcript.duration_seconds:
            minutes = int(transcript.duration_seconds / 60)
            parts.append(f"Duration: {minutes} minutes")

        parts.append(f"\n--- TRANSCRIPT ---")

        if transcript.transcript_text:
            parts.append(transcript.transcript_text)
        elif transcript.utterances:
            for utterance in transcript.utterances:
                speaker = utterance.get("speaker", "Unknown")
                text = utterance.get("text", "")
                parts.append(f"[{speaker}]: {text}")

        parts.append("")  # Empty line separator

        return "\n".join(parts)
