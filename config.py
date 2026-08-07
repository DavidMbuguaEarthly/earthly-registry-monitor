"""
Configuration for the Earthly registry monitor.

Edit PROJECTS to add/remove projects from the watchlist.
Secrets like SLACK_WEBHOOK_URL come from the .env file.

NOTE (Aug 2026): Verra migrated to an S&P Global / Platts backend. We now call
a JSON API instead of scraping HTML. The API rate-limits hard (HTTP 429), so
delays between projects are deliberately generous.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECTS = [
    {"id": 2250, "name": "Delta Blue Carbon - 1", "country": "Pakistan"},
    {"id": 3346, "name": "Indo-Gangetic Plains Regenerative Agriculture", "country": "India"},
    {"id": 3368, "name": "Orizon CarbonCrop Rewards Programme", "country": "Multiple"},
    {"id": 1764, "name": "Mangrove Restoration - Ayeyarwady Delta", "country": "Myanmar"},
    {"id": 4646, "name": "Agroforestry - Mount Kenya", "country": "Kenya"},
    {"id": 2339, "name": "Agroforestry - smallholder farmers (TIST Uganda)", "country": "Uganda"},
    {"id": 674, "name": "Peatland protection - Rimba Raya", "country": "Indonesia"},
    {"id": 4201, "name": "Improved Cropland Management", "country": "Lithuania"},
    {"id": 4022, "name": "Regenerative Farming Practices", "country": "United Kingdom"},
    {"id": 1201, "name": "The Gola REDD Project", "country": "Sierra Leone"},
    {"id": 1960, "name": "Northern Great Plains Regenerative Grazing", "country": "USA"},
    {"id": 2609, "name": "Kuamut Rainforest Conservation Project", "country": "Malaysia"},
    {"id": 1055, "name": "Reforesting Degraded Lands in Chile (Mycorrhizal Inoculation)", "country": "Chile"},
    {"id": 1318, "name": "Livelihoods' Mangrove Restoration Grouped Project", "country": "Senegal"},
    {"id": 1571, "name": "Manoa REDD+ Project", "country": "Brazil"},
    {"id": 576, "name": "Restoration & Reforestation - Caceres and Cravo Norte", "country": "Colombia"},
    {"id": 3660, "name": "Papariko - Mangrove Restoration", "country": "Kenya"},
]

# New S&P/Platts JSON API endpoint (replaces the old APX projectDetail HTML page)
API_URL_TEMPLATE = (
    "https://prod-us.api.platts.com/ci-raas-prod/br-reg/rest/"
    "public-report-manager/getProjectById/{project_id}/Markit"
)

# Headers the API requires (captured from the registry frontend). The Appkey
# is a public, frontend-embedded key that ships in the public site's JavaScript
# - it is not a user secret, so it lives in config rather than .env.
API_APPKEY = "wOKHFGuxKApQaujPSKgF"
API_STANDARD_ID = "150000000000001"

PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "monitor.db"
LOG_PATH = PROJECT_ROOT / "alerts.log"

# Rate-limit handling. Confirmed limits from response headers:
#   X-Ratelimit-Limit-Second: 10  |  -Minute: 50  |  -Day: 100001
# Our one-request-per-project pattern is well within this, so modest delays
# suffice. A full 17-project run takes ~2-3 min.
DELAY_BETWEEN_PROJECTS_S = 3       # pause between each project fetch
MAX_RETRIES = 6                   # per-project retry attempts on 429/errors
BASE_BACKOFF_S = 10               # base wait for backoff between retries

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")