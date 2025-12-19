import os

import ccxt
from dotenv import load_dotenv


def init_exchange() -> ccxt.Exchange:
    """Configure the ccxt KuCoin client using environment credentials."""
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

