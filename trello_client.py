"""
Trello API Client for Patty's Knowledge Brain

This module handles all communication with the Trello API to fetch
boards, lists, cards, and their content.

Rate limits: 100 requests per 10 seconds per token, 300 per 10 seconds per API key.
"""

import requests
import time
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from collections import deque


@dataclass
class TrelloCard:
    """Represents a Trello card with its content."""
    id: str
    name: str
    description: str
    board_name: str
    list_name: str
    labels: list[str]
    comments: list[str]
    last_activity: datetime
    url: str


class RateLimiter:
    """Simple rate limiter to avoid hitting Trello API limits."""

    def __init__(self, max_requests: int = 80, time_window: float = 10.0):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in time window (default 80, leaving buffer from 100 limit)
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()

    def wait_if_needed(self):
        """Wait if we're approaching the rate limit."""
        now = time.time()

        # Remove old requests outside the time window
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()

        # If at limit, wait until oldest request expires
        if len(self.requests) >= self.max_requests:
            sleep_time = self.requests[0] - (now - self.time_window) + 0.1
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Record this request
        self.requests.append(time.time())


class TrelloClient:
    """Client for interacting with the Trello API."""

    BASE_URL = "https://api.trello.com/1"

    def __init__(self, api_key: str, token: str):
        """
        Initialize the Trello client.

        Args:
            api_key: Trello API key
            token: Trello user token
        """
        self.api_key = api_key
        self.token = token
        self._session = requests.Session()
        self._rate_limiter = RateLimiter(max_requests=80, time_window=10.0)

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make an authenticated request to the Trello API with rate limiting."""
        # Wait if we're approaching rate limit
        self._rate_limiter.wait_if_needed()

        url = f"{self.BASE_URL}{endpoint}"
        request_params = {
            "key": self.api_key,
            "token": self.token,
            **(params or {})
        }

        response = self._session.get(url, params=request_params)
        response.raise_for_status()
        return response.json()

    def test_connection(self) -> tuple[bool, str]:
        """
        Test if the API credentials are valid.

        Returns:
            Tuple of (success, message)
        """
        try:
            member = self._make_request("/members/me")
            return True, f"Connected as: {member.get('fullName', 'Unknown')}"
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return False, "Invalid API key or token"
            return False, f"HTTP Error: {e}"
        except Exception as e:
            return False, f"Connection error: {e}"

    def get_all_boards(self) -> list[dict]:
        """Fetch all boards the user has access to."""
        boards = self._make_request("/members/me/boards", {
            "fields": "name,desc,url,dateLastActivity",
            "filter": "open"
        })
        return boards

    def get_board_lists(self, board_id: str) -> list[dict]:
        """Fetch all lists in a board."""
        lists = self._make_request(f"/boards/{board_id}/lists", {
            "fields": "name"
        })
        return lists

    def get_list_cards(self, list_id: str) -> list[dict]:
        """Fetch all cards in a list."""
        cards = self._make_request(f"/lists/{list_id}/cards", {
            "fields": "name,desc,labels,url,dateLastActivity"
        })
        return cards

    def get_card_comments(self, card_id: str) -> list[str]:
        """Fetch all comments on a card."""
        actions = self._make_request(f"/cards/{card_id}/actions", {
            "filter": "commentCard"
        })
        return [action["data"]["text"] for action in actions if "data" in action and "text" in action["data"]]

    def get_all_cards(self, include_comments: bool = True, progress_callback=None) -> list[TrelloCard]:
        """
        Fetch all cards from all boards.

        Args:
            include_comments: Whether to fetch comments for each card
            progress_callback: Optional callback(current, total, message) for progress updates

        Returns:
            List of TrelloCard objects
        """
        all_cards = []
        boards = self.get_all_boards()

        total_boards = len(boards)

        for board_idx, board in enumerate(boards):
            board_name = board["name"]
            board_id = board["id"]

            if progress_callback:
                progress_callback(board_idx, total_boards, f"Syncing board: {board_name}")

            try:
                lists = self.get_board_lists(board_id)
                list_names = {lst["id"]: lst["name"] for lst in lists}

                for lst in lists:
                    cards = self.get_list_cards(lst["id"])

                    for card in cards:
                        comments = []
                        if include_comments:
                            try:
                                comments = self.get_card_comments(card["id"])
                            except Exception:
                                pass  # Skip if we can't get comments

                        labels = [label.get("name", "") for label in card.get("labels", []) if label.get("name")]

                        last_activity = datetime.now()
                        if card.get("dateLastActivity"):
                            try:
                                last_activity = datetime.fromisoformat(card["dateLastActivity"].replace("Z", "+00:00"))
                            except ValueError:
                                pass

                        trello_card = TrelloCard(
                            id=card["id"],
                            name=card["name"],
                            description=card.get("desc", ""),
                            board_name=board_name,
                            list_name=list_names.get(lst["id"], "Unknown"),
                            labels=labels,
                            comments=comments,
                            last_activity=last_activity,
                            url=card.get("url", "")
                        )
                        all_cards.append(trello_card)

            except Exception as e:
                if progress_callback:
                    progress_callback(board_idx, total_boards, f"Error with board {board_name}: {e}")
                continue

        if progress_callback:
            progress_callback(total_boards, total_boards, f"Sync complete! {len(all_cards)} cards fetched.")

        return all_cards

    def card_to_text(self, card: TrelloCard) -> str:
        """Convert a TrelloCard to searchable text format."""
        parts = [
            f"=== TRELLO CARD: {card.name} ===",
            f"Board: {card.board_name}",
            f"List: {card.list_name}",
        ]

        if card.labels:
            parts.append(f"Labels: {', '.join(card.labels)}")

        if card.description:
            parts.append(f"\nDescription:\n{card.description}")

        if card.comments:
            parts.append(f"\nComments ({len(card.comments)}):")
            for i, comment in enumerate(card.comments, 1):
                parts.append(f"  {i}. {comment}")

        parts.append(f"\nURL: {card.url}")
        parts.append("")  # Empty line separator

        return "\n".join(parts)
