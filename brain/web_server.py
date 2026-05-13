import asyncio
import logging
from brain.pi5.web_ui_backend.main import app
from brain.pi5.web_ui_backend import core as backend_core

from uvicorn import Config, Server

class WebServer:
    def __init__(self, host="0.0.0.0", port=8000, command_queue: asyncio.Queue = None, settings_path: str = None, state_manager=None):
        self.host = host
        self.port = port
        self.command_queue = command_queue
        self.state_manager = state_manager
        
        # Inject the queue into the backend module
        if command_queue:
            backend_core.set_command_queue(command_queue)
            logging.info("Injected command queue into Web UI backend.")

        if settings_path:
            backend_core.set_settings_path(settings_path)
            logging.info(f"Overrode Web UI settings path to: {settings_path}")

        if state_manager:
            backend_core.set_state_manager(state_manager)
            logging.info("Injected state manager into Web UI backend.")

        self.config = Config(app=app, host=self.host, port=self.port, log_level="warning", access_log=False)
        self.server = Server(config=self.config)

    async def serve(self):
        logging.info(f"Starting Web Server at http://{self.host}:{self.port}")
        await self.server.serve()
