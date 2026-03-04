from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Portfolio, StockRecord
from ..schemas import StockLookupResponse, StockRecordCreate, StockRecordResponse
from ..services.stock_data import lookup_ticker, refresh_prices

router = APIRouter(tags=["stocks"])


def _stock_to_response(s: StockRecord) -> StockRecordResponse:
    price = s.current_price or s.buy_price
    market_value = round(price * s.quantity, 2)
    profit_loss = round((price - s.buy_price) * s.quantity, 2)
    return StockRecordResponse(
        id=s.id,
        portfolio_id=s.portfolio_id,
        ticker=s.ticker,
        market=s.market,
        company_name=s.company_name,
        quantity=s.quantity,
        buy_price=s.buy_price,
        current_price=s.current_price,
        price_change_pct=s.price_change_pct,
        last_updated=s.last_updated,
        market_value=market_value,
        profit_loss=profit_loss,
    )


@router.get(
    "/api/portfolios/{portfolio_id}/stocks",
    response_model=list[StockRecordResponse],
)
def list_stocks(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return [_stock_to_response(s) for s in portfolio.stocks]


@router.post(
    "/api/portfolios/{portfolio_id}/stocks",
    response_model=StockRecordResponse,
    status_code=201,
)
def add_stock(
    portfolio_id: int,
    data: StockRecordCreate,
    db: Session = Depends(get_db),
):
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    record = StockRecord(
        portfolio_id=portfolio_id,
        ticker=data.ticker,
        market=data.market,
        company_name=data.company_name,
        quantity=data.quantity,
        buy_price=data.buy_price,
        current_price=data.current_price or data.buy_price,
        last_updated=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _stock_to_response(record)


@router.delete("/api/stocks/{stock_id}", status_code=204)
def delete_stock(stock_id: int, db: Session = Depends(get_db)):
    record = db.query(StockRecord).filter(StockRecord.id == stock_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Stock record not found")
    db.delete(record)
    db.commit()


@router.get("/api/stocks/lookup", response_model=StockLookupResponse)
async def lookup_stock(
    ticker: str = Query(..., min_length=1),
    market: str = Query(..., pattern="^(us|hk|cn)$"),
):
    result = await lookup_ticker(ticker, market)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker '{ticker}' not found in {market.upper()} market",
        )
    return StockLookupResponse(**result)


@router.post("/api/stocks/refresh")
async def refresh_all_stocks(db: Session = Depends(get_db)):
    all_records = db.query(StockRecord).all()
    if not all_records:
        return {"updated": 0}

    records_input = [
        {"ticker": r.ticker, "market": r.market} for r in all_records
    ]
    updated_data = await refresh_prices(records_input)

    count = 0
    now = datetime.now(timezone.utc)
    for record in all_records:
        key = f"{record.market}:{record.ticker}"
        if key in updated_data:
            record.current_price = updated_data[key]["current_price"]
            record.price_change_pct = updated_data[key]["price_change_pct"]
            record.last_updated = now
            count += 1

    db.commit()
    return {"updated": count}
