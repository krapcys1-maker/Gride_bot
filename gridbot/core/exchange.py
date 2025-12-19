import os
import time
from typing import Callable, Optional

import ccxt
from dotenv import load_dotenv


class NullExchange:
    """Minimal offline stub implementing the subset used by the bot."""

    id = "offline"

    def __init__(self, price_provider: Optional[Callable[[], Optional[float]]] = None) -> None:
        self._price_provider = price_provider

    def fetch_ticker(self, symbol: str) -> dict:
        price = self._price_provider() if self._price_provider else None
        return {"symbol": symbol, "last": price, "close": price}

    def fetch_balance(self) -> dict:
        return {}

    def create_order(self, symbol: str, order_type: str, side: str, amount: float, price: Optional[float] = None) -> dict:
        return {
            "id": f"offline_{symbol}_{side}_{price}",
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "status": "open",
            "timestamp": int(time.time() * 1000),
        }

    def fetch_order(self, order_id: str, symbol: Optional[str] = None) -> dict:
        return {"id": order_id, "symbol": symbol, "status": "open"}

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> dict:
        return {"id": order_id, "symbol": symbol, "status": "canceled"}


def init_exchange(offline: bool = False, price_provider: Optional[Callable[[], Optional[float]]] = None):
    """Configure the ccxt KuCoin client using environment credentials."""
    if offline:
        return NullExchange(price_provider=price_provider)

    load_dotenv()
    api_key = os.getenv("KUCOIN_API_KEY")
    api_secret = os.getenv("KUCOIN_API_SECRET")
    passphrase = os.getenv("KUCOIN_PASSPHRASE")
    if not api_key or not api_secret or not passphrase:
        raise EnvironmentError(
            "KUCOIN_API_KEY, KUCOIN_API_SECRET and KUCOIN_PASSPHRASE must be set in the environment"
        )

    return ccxt.kucoin(
        {
            "apiKey": api_key,
            "secret": api_secret,
            "password": passphrase,
            "enableRateLimit": True,
        }
    )
