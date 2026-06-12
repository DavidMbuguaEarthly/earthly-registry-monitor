"""
Configuration for the Earthly registry monitor.

Edit PROJECTS to add/remove projects from the watchlist.
Secrets like SLACK_WEBHOOK_URL come from the .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECTS = [
    # --- Original 9 ---
    {"id": 2250, "name": "Delta Blue Carbon - 1", "country": "Pakistan"},
    {"id": 3346, "name": "Indo-Gangetic Plains Regenerative Agriculture", "country": "India"},
    {"id": 3368, "name": "Orizon CarbonCrop Rewards Programme", "country": "Multiple"},
    {"id": 1764, "name": "Mangrove Restoration - Ayeyarwady Delta", "country": "Myanmar"},
    {"id": 4646, "name": "Agroforestry - Mount Kenya", "country": "Kenya"},
    {"id": 2339, "name": "Agroforestry - smallholder farmers (TIST Uganda)", "country": "Uganda"},
    {"id": 674, "name": "Peatland protection - Rimba Raya", "country": "Indonesia"},
    {"id": 4201, "name": "Improved Cropland Management", "country": "Lithuania"},
    {"id": 4022, "name": "Regenerative Farming Practices", "country": "United Kingdom"},

    # --- Added batch 2 ---
    {"id": 1201, "name": "The Gola REDD Project", "country": "Sierra Leone"},
    {"id": 1960, "name": "Northern Great Plains Regenerative Grazing", "country": "USA"},
    {"id": 2609, "name": "Kuamut Rainforest Conservation Project", "country": "Malaysia"},
    {"id": 1055, "name": "Reforesting Degraded Lands in Chile (Mycorrhizal Inoculation)", "country": "Chile"},
    {"id": 1318, "name": "Livelihoods' Mangrove Restoration Grouped Project", "country": "Senegal"},
    {"id": 1571, "name": "Manoa REDD+ Project", "country": "Brazil"},
    {"id": 576, "name": "Restoration & Reforestation - Caceres and Cravo Norte", "country": "Colombia"},
    {"id": 3660, "name": "Papariko - Mangrove Restoration", "country": "Kenya"},
]

REGISTRY_URL_TEMPLATE = "https://registry.verra.org/app/projectDetail/VCS/{project_id}"

PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "monitor.db"
LOG_PATH = PROJECT_ROOT / "alerts.log"

PAGE_LOAD_TIMEOUT_MS = 60_000
LAZY_CONTENT_WAIT_MS = 4_000
DELAY_BETWEEN_PROJECTS_MS = 2_000

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")