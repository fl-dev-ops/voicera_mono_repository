"""Main entry point for the Voicera LiveKit Voice Agent worker.

This is a pure LiveKit worker that handles inbound and outbound SIP calls.
Telephony management (SIP trunks, dispatch rules, outbound calls) has been
moved to the backend.

Run:
    python main.py start          # production
    python main.py dev            # dev mode (auto-reload)
    python main.py connect <room> # connect to a specific room
"""

import os
from livekit.agents import WorkerOptions, cli

from api.agent import entrypoint, prewarm

# Agent name for dispatch - must match the LiveKit dispatch rule configuration
# This should be the same as LIVEKIT_AGENT_NAME in the backend
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "voicera-agent")


if __name__ == "__main__":
    # Run the LiveKit Worker (this blocks until the worker exits).
    # agent_name MUST match the RoomAgentDispatch name on dispatch rules
    # so LiveKit knows to route inbound SIP calls to this worker.
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=AGENT_NAME,
        )
    )
