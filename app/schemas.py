from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PortfolioCreate(BaseModel):
    name: str


class PortfolioResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    total_value: float = 0.0
    total_cost: float = 0.0

    model_config = {"from_attributes": True}


class StockRecordCreate(BaseModel):
    ticker: str
    market: str  # "us", "hk", "cn"
    company_name: str
    quantity: float
    buy_price: float
    current_price: Optional[float] = None


class StockRecordResponse(BaseModel):
    id: int
    portfolio_id: int
    ticker: str
    market: str
    company_name: str
    quantity: float
    buy_price: float
    current_price: Optional[float] = None
    price_change_pct: Optional[float] = None
    last_updated: Optional[datetime] = None
    market_value: float = 0.0
    profit_loss: float = 0.0

    model_config = {"from_attributes": True}


class StockLookupResponse(BaseModel):
    ticker: str
    market: str
    company_name: str
    current_price: float
    price_change_pct: Optional[float] = None
