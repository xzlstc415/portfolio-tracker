from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    stocks = relationship(
        "StockRecord", back_populates="portfolio", cascade="all, delete-orphan"
    )


class StockRecord(Base):
    __tablename__ = "stock_records"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String, nullable=False)
    market = Column(String, nullable=False)  # "us", "hk", "cn"
    company_name = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    price_change_pct = Column(Float, nullable=True)
    last_updated = Column(DateTime, nullable=True)

    portfolio = relationship("Portfolio", back_populates="stocks")
