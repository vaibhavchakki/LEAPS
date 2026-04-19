# LEAP + PMCC Advisor (Yahoo Finance)

This module provides:

1. LEAP selector for an equity (default `INTC`) using live Yahoo option chains.
2. JSON position storage for LEAPs you already bought.
3. Covered-call guidance (poor-man's covered call) weekly/monthly by risk profile.
4. Streamlit dashboard.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run src/leaps_app/app.py
```

Set **Positions JSON Path** to:

`C:\Users\vaibhav\OneDrive\Documents\LEAPS\leap_positions.json`

No API key is required for this Yahoo Finance setup.
