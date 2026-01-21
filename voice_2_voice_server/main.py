"""Main entry point for the Vobiz Telephony Server."""

import uvicorn
from api.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")

