"""Main entry point for the Voicera LiveKit Voice Agent worker.

Starts BOTH:
  1. The FastAPI helper server (port 7860) — for /outbound/call/, SIP management, /health
  2. The LiveKit Agents worker process — listens for rooms and handles calls

Run:
    python main.py start          # production
    python main.py dev            # dev mode (auto-reload)
    python main.py connect <room> # connect to a specific room
"""

import multiprocessing
import sys

from livekit.agents import WorkerOptions, cli

from api.agent import entrypoint, prewarm


def run_fastapi_server():
    """Start the FastAPI helper server in a separate process."""
    from api.server import run_server

    run_server(host="0.0.0.0", port=7860, log_level="info")


if __name__ == "__main__":
    # Start the FastAPI server in a background process so both
    # the HTTP API and the LiveKit Worker run in the same container.
    server_proc = multiprocessing.Process(
        target=run_fastapi_server,
        daemon=True,
        name="fastapi-server",
    )
    server_proc.start()

    # Run the LiveKit Worker (this blocks until the worker exits).
    # agent_name MUST match the RoomAgentDispatch name on dispatch rules
    # so LiveKit knows to route inbound SIP calls to this worker.
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="voicera-agent",
        )
    )

    # If the worker exits, also kill the FastAPI server.
    server_proc.terminate()
    server_proc.join()
    sys.exit(0)
