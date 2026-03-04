# Stock Portfolio Tracker

A local web-based stock portfolio tracker with multi-market support (CN/US/HK) powered by akshare.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Then open http://localhost:8000 in your browser.

## Features

- Create and delete portfolios
- Add stock records with automatic ticker lookup (company name + current price)
- Multi-market support: Chinese A-shares, US stocks, Hong Kong stocks
- Auto-refresh prices every 30 seconds
