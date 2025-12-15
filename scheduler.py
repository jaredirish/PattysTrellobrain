"""
Background Scheduler for Patty's Knowledge Brain

Handles automatic periodic syncing of Trello data.

Note: On Streamlit Cloud, background jobs may be interrupted when the app
goes to sleep. The app will check on startup if a sync is needed.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from trello_client import TrelloClient
from database import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncScheduler:
    """Manages background syncing of Trello data."""

    def __init__(
        self,
        trello_client: TrelloClient,
        database: DatabaseManager,
        sync_interval_hours: int = 24
    ):
        """
        Initialize the sync scheduler.

        Args:
            trello_client: Configured Trello API client
            database: Database manager instance
            sync_interval_hours: Hours between automatic syncs
        """
        self.trello_client = trello_client
        self.database = database
        self.sync_interval_hours = sync_interval_hours
        self.scheduler: Optional[BackgroundScheduler] = None
        self._is_syncing = False
        self._last_sync_status = ""

    def sync_trello_data(self, progress_callback: Optional[Callable] = None) -> tuple[bool, str]:
        """
        Perform a full sync of Trello data.

        Args:
            progress_callback: Optional callback(current, total, message) for progress

        Returns:
            Tuple of (success, status_message)
        """
        if self._is_syncing:
            return False, "Sync already in progress"

        self._is_syncing = True
        self._last_sync_status = "Starting sync..."

        try:
            # Test connection first
            success, message = self.trello_client.test_connection()
            if not success:
                self._last_sync_status = f"Connection failed: {message}"
                return False, self._last_sync_status

            # Fetch all cards
            def update_progress(current, total, msg):
                self._last_sync_status = msg
                if progress_callback:
                    progress_callback(current, total, msg)

            cards = self.trello_client.get_all_cards(
                include_comments=True,
                progress_callback=update_progress
            )

            # Clear existing and insert new
            self.database.clear_trello_cards()

            for card in cards:
                content_text = self.trello_client.card_to_text(card)
                self.database.upsert_trello_card(
                    card_id=card.id,
                    name=card.name,
                    description=card.description,
                    board_name=card.board_name,
                    list_name=card.list_name,
                    labels=card.labels,
                    comments=card.comments,
                    url=card.url,
                    last_activity=card.last_activity,
                    content_text=content_text
                )

            # Update sync timestamp
            self.database.set_last_sync_time()

            self._last_sync_status = f"Synced {len(cards)} cards successfully!"
            logger.info(self._last_sync_status)
            return True, self._last_sync_status

        except Exception as e:
            self._last_sync_status = f"Sync failed: {str(e)}"
            logger.error(self._last_sync_status)
            return False, self._last_sync_status

        finally:
            self._is_syncing = False

    def needs_sync(self) -> bool:
        """Check if a sync is needed based on the last sync time."""
        last_sync = self.database.get_last_sync_time()
        if last_sync is None:
            return True

        time_since_sync = datetime.now() - last_sync.replace(tzinfo=None)
        return time_since_sync > timedelta(hours=self.sync_interval_hours)

    def start_scheduler(self):
        """Start the background scheduler for automatic syncing."""
        if self.scheduler is not None:
            return

        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            func=lambda: self.sync_trello_data(),
            trigger=IntervalTrigger(hours=self.sync_interval_hours),
            id="trello_sync",
            name="Trello Data Sync",
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(f"Scheduler started. Syncing every {self.sync_interval_hours} hours.")

    def stop_scheduler(self):
        """Stop the background scheduler."""
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
            logger.info("Scheduler stopped.")

    @property
    def is_syncing(self) -> bool:
        """Check if a sync is currently in progress."""
        return self._is_syncing

    @property
    def last_sync_status(self) -> str:
        """Get the status of the last sync operation."""
        return self._last_sync_status

    def get_next_sync_time(self) -> Optional[datetime]:
        """Get the next scheduled sync time."""
        last_sync = self.database.get_last_sync_time()
        if last_sync is None:
            return None
        return last_sync.replace(tzinfo=None) + timedelta(hours=self.sync_interval_hours)
