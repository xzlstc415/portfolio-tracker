from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Portfolio
from ..schemas import PortfolioCreate, PortfolioResponse

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


@router.get("", response_model=list[PortfolioResponse])
def list_portfolios(db: Session = Depends(get_db)):
    portfolios = db.query(Portfolio).order_by(Portfolio.created_at.desc()).all()
    result = []
    for p in portfolios:
        total_value = sum(
            (s.current_price or s.buy_price) * s.quantity for s in p.stocks
        )
        total_cost = sum(s.buy_price * s.quantity for s in p.stocks)
        result.append(
            PortfolioResponse(
                id=p.id,
                name=p.name,
                created_at=p.created_at,
                total_value=round(total_value, 2),
                total_cost=round(total_cost, 2),
            )
        )
    return result


@router.post("", response_model=PortfolioResponse, status_code=201)
def create_portfolio(data: PortfolioCreate, db: Session = Depends(get_db)):
    portfolio = Portfolio(name=data.name)
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        created_at=portfolio.created_at,
    )


@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    db.delete(portfolio)
    db.commit()
