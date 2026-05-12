"""Centralized configuration — reads .env, fails loudly if vars are missing."""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Read an env var or crash at startup with a clear error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Astra DB (vector knowledge base)
ASTRA_DB_ENDPOINT = _require("ASTRA_DB_ENDPOINT")
ASTRA_DB_TOKEN = _require("ASTRA_DB_TOKEN")

# IBM Cloud IAM (shared auth for all IBM services)
IBM_CLOUD_API_KEY = _require("IBM_CLOUD_API_KEY")

# watsonx Orchestrate
WXO_URL = _require("WXO_URL")
WXO_AGENT_ID = _require("WXO_AGENT_ID")
WXO_ENV_ID = _require("WXO_ENV_ID")
WXO_INSTANCE_ID = _require("WXO_INSTANCE_ID")

# Jira integration (optional — set all four to enable)
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")  # e.g. https://yourorg.atlassian.net
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")  # e.g. FEEDBACK

JIRA_ENABLED = all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY])
