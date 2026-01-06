"""
EPİAŞ (Turkish Energy Market) Integration
Fetches electricity prices and market data from EPİAŞ Transparency Platform.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# EPİAŞ API Endpoints
EPIAS_BASE_URL = "https://seffaflik.epias.com.tr/transparency/service"
EPIAS_MCP_URL = f"{EPIAS_BASE_URL}/market/day-ahead-mcp"  # Market Clearing Price
EPIAS_SMP_URL = f"{EPIAS_BASE_URL}/market/bpm-order-summary"  # System Marginal Price
EPIAS_CONSUMPTION_URL = f"{EPIAS_BASE_URL}/consumption/real-time-consumption"


class EPIASService:
    """
    EPİAŞ Energy Market Service.
    
    Provides access to Turkish electricity market data:
    - Day-ahead market clearing prices (PTF)
    - System marginal prices (SMF)
    - Real-time consumption data
    
    Usage:
        epias = EPIASService()
        prices = await epias.get_day_ahead_prices(date.today())
    """
    
    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
    ):
        """
        Initialize EPİAŞ service.
        
        Args:
            username: EPİAŞ username (optional for public endpoints)
            password: EPİAŞ password
        """
        self.username = username or settings.epias_username
        self.password = password or settings.epias_password
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
    
    @property
    def is_authenticated(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.username and self.password)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _format_date(self, d: date) -> str:
        """Format date for EPİAŞ API (YYYY-MM-DD)."""
        return d.strftime("%Y-%m-%d")
    
    async def get_day_ahead_prices(
        self,
        target_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get day-ahead market clearing prices (PTF - Piyasa Takas Fiyatı).
        
        Args:
            target_date: Date to fetch prices for (default: today)
            
        Returns:
            List of hourly prices with timestamp and price in TRY/MWh
        """
        if target_date is None:
            target_date = date.today()
        
        client = await self._get_client()
        
        params = {
            "startDate": self._format_date(target_date),
            "endDate": self._format_date(target_date),
        }
        
        try:
            response = await client.get(EPIAS_MCP_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            prices = []
            for item in data.get("body", {}).get("dayAheadMCPList", []):
                prices.append({
                    "timestamp": item.get("date"),
                    "price": Decimal(str(item.get("price", 0))),
                    "currency": "TRY",
                    "unit": "MWh",
                })
            
            logger.info(
                "Fetched day-ahead prices",
                date=self._format_date(target_date),
                count=len(prices),
            )
            
            return prices
            
        except httpx.HTTPError as e:
            logger.error("Failed to fetch day-ahead prices", error=str(e))
            return []
    
    async def get_hourly_price(
        self,
        target_datetime: datetime | None = None,
    ) -> Decimal | None:
        """
        Get price for a specific hour.
        
        Args:
            target_datetime: Datetime to get price for (default: now)
            
        Returns:
            Price in TRY/MWh or None if not found
        """
        if target_datetime is None:
            target_datetime = datetime.now()
        
        prices = await self.get_day_ahead_prices(target_datetime.date())
        
        target_hour = target_datetime.hour
        for price_data in prices:
            # Parse timestamp and check hour
            ts = price_data.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.hour == target_hour:
                        return price_data.get("price")
                except ValueError:
                    continue
        
        return None
    
    async def get_average_price(
        self,
        target_date: date | None = None,
    ) -> Decimal | None:
        """
        Get average price for a day.
        
        Args:
            target_date: Date to calculate average for
            
        Returns:
            Average price in TRY/MWh
        """
        prices = await self.get_day_ahead_prices(target_date)
        
        if not prices:
            return None
        
        total = sum(p.get("price", Decimal(0)) for p in prices)
        return total / len(prices)
    
    async def get_price_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """
        Get prices for a date range.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of daily price summaries
        """
        results = []
        current = start_date
        
        while current <= end_date:
            prices = await self.get_day_ahead_prices(current)
            
            if prices:
                price_values = [p.get("price", Decimal(0)) for p in prices]
                results.append({
                    "date": self._format_date(current),
                    "min_price": min(price_values),
                    "max_price": max(price_values),
                    "avg_price": sum(price_values) / len(price_values),
                    "hours": len(prices),
                })
            
            current += timedelta(days=1)
        
        return results
    
    async def get_real_time_consumption(self) -> dict[str, Any] | None:
        """
        Get real-time electricity consumption data for Turkey.
        
        Returns:
            Current consumption data
        """
        client = await self._get_client()
        
        try:
            response = await client.get(EPIAS_CONSUMPTION_URL)
            response.raise_for_status()
            data = response.json()
            
            consumption_list = data.get("body", {}).get("hourlyConsumptions", [])
            if consumption_list:
                latest = consumption_list[-1]
                return {
                    "timestamp": latest.get("date"),
                    "consumption": Decimal(str(latest.get("consumption", 0))),
                    "unit": "MWh",
                }
            
            return None
            
        except httpx.HTTPError as e:
            logger.error("Failed to fetch consumption data", error=str(e))
            return None
    
    async def calculate_cost(
        self,
        consumption_kwh: float,
        target_datetime: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Calculate electricity cost for given consumption.
        
        Args:
            consumption_kwh: Consumption in kWh
            target_datetime: Time for price lookup
            
        Returns:
            Cost calculation details
        """
        price = await self.get_hourly_price(target_datetime)
        
        if price is None:
            return {
                "consumption_kwh": consumption_kwh,
                "price_per_mwh": None,
                "cost": None,
                "error": "Price not available",
            }
        
        # Convert MWh price to kWh
        price_per_kwh = price / 1000
        cost = Decimal(str(consumption_kwh)) * price_per_kwh
        
        return {
            "consumption_kwh": consumption_kwh,
            "price_per_mwh": float(price),
            "price_per_kwh": float(price_per_kwh),
            "cost": float(cost),
            "currency": "TRY",
        }


# Singleton instance
_epias_service: EPIASService | None = None


def get_epias_service() -> EPIASService:
    """Get or create EPİAŞ service singleton."""
    global _epias_service
    if _epias_service is None:
        _epias_service = EPIASService()
    return _epias_service
