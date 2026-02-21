"""Static data loader for screening tools.

Loads question bank and job profiles from JSON files at import time.
These are small datasets (<100KB) kept in-memory for fast tool lookups.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

_DATA_DIR = Path(__file__).parent


def _load_json(filename: str) -> List[Dict[str, Any]]:
    """Load a JSON file from the tool_data directory."""
    filepath = _DATA_DIR / filename
    try:
        with open(filepath) as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} entries from {filename}")
        return data
    except FileNotFoundError:
        logger.error(f"Data file not found: {filepath}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return []


QUESTION_BANK: List[Dict[str, Any]] = _load_json("question_bank.json")
JOB_PROFILES: List[Dict[str, Any]] = _load_json("job_profiles.json")
