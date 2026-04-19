# LEAP + PMCC Advisor (Polygon / Massive API)

This module gives you:

1. **LEAP selector** for an equity (default `INTC`) based on live option chain + greeks.
2. **JSON position storage** for LEAPs you've already bought.
3. **Covered-call guidance** (poor-man's covered call) weekly/monthly based on risk profile.
4. **Dashboard UI** with Streamlit.

## Setup

```bash
pip install -r requirements.txt
```

Set API key (or paste in sidebar in app):

```bash
export POLYGON_API_KEY="YOUR_KEY"
```

On Windows PowerShell:

```powershell
$env:POLYGON_API_KEY="YOUR_KEY"
```

## Run

```bash
streamlit run src/leaps_app/app.py
```

For your requested folder, point **Positions JSON Path** in the sidebar to:

`C:\Users\vaibhav\OneDrive\Documents\LEAPS\leap_positions.json`

The app will create/update that file.

## JSON format

Saved entries look like:

```json
[
  {
    "underlying": "INTC",
    "option_ticker": "O:INTC270115C00025000",
    "expiration": "2027-01-15",
    "strike": 25.0,
    "entry_price": 7.5,
    "contracts": 1
  }
]
```

## API rate limit handling

`PolygonClient` enforces a **sliding window limiter** at `5 requests / minute` and also retries on HTTP `429`.
