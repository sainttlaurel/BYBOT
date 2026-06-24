"""
modules/webhook_sender.py - Webhook support for BY BOTS.

Provides an alternative to Discord bot posting by sending post data
to configured webhook endpoints. Useful for integration with other services,
custom notification systems, or event-driven architectures.
"""

import asyncio
import logging
from typing import Optional
from dataclasses import asdict

import httpx

logger = logging.getLogger(__name__)


class WebhookSender:
    """Sends Facebook post data to configured webhook endpoints."""

    def __init__(self, webhook_urls: list[str], timeout: int = 30):
        """
        Initialize webhook sender.

        Args:
            webhook_urls: List of webhook endpoint URLs to send data to
            timeout: Request timeout in seconds (default: 30)
        """
        self.webhook_urls = webhook_urls
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def send_post(self, post_data: dict) -> dict[str, bool]:
        """
        Send post data to all configured webhooks.

        Args:
            post_data: Dictionary containing Facebook post information

        Returns:
            Dictionary mapping webhook URLs to success status (True/False)
        """
        if not self.webhook_urls:
            logger.warning("No webhook URLs configured")
            return {}

        client = await self._ensure_client()
        results = {}

        # Send to all webhooks concurrently
        tasks = [
            self._send_to_webhook(client, url, post_data)
            for url in self.webhook_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for url, response in zip(self.webhook_urls, responses):
            if isinstance(response, Exception):
                logger.error("Error sending to webhook %s: %s", url, response)
                results[url] = False
            else:
                results[url] = response

        return results

    async def _send_to_webhook(
        self, client: httpx.AsyncClient, url: str, data: dict
    ) -> bool:
        """
        Send data to a single webhook endpoint.

        Args:
            client: HTTP client instance
            url: Webhook endpoint URL
            data: Post data to send

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Sending post data to webhook: %s", url)
            response = await client.post(
                url,
                json=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "BY-BOTS-Webhook/1.0",
                },
            )
            response.raise_for_status()
            logger.info(
                "Successfully sent to webhook %s (status: %d)",
                url,
                response.status_code,
            )
            return True
        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error sending to webhook %s: %d %s",
                url,
                e.response.status_code,
                e.response.text,
            )
            return False
        except httpx.RequestError as e:
            logger.error("Request error sending to webhook %s: %s", url, e)
            return False
        except Exception as e:
            logger.error("Unexpected error sending to webhook %s: %s", url, e)
            return False


def format_post_for_webhook(post) -> dict:
    """
    Format a FacebookPost object for webhook delivery.

    Args:
        post: FacebookPost instance

    Returns:
        Dictionary with post data ready for JSON serialization
    """
    from modules.facebook_monitor import FacebookPost

    if isinstance(post, FacebookPost):
        data = asdict(post)
    else:
        data = post

    # Add metadata
    data["event_type"] = "new_facebook_post"
    data["source"] = "BY-BOTS"

    return data
