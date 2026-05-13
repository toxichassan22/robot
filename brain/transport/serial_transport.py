from __future__ import annotations

import asyncio
import logging
import time

import serial
import serial.tools.list_ports

from brain.transport.transport_base import Transport


class SerialTransport(Transport):
    def __init__(self, port: str, baud: int = 115200):
        self.port = port
        self.baud = baud
        self.ser: serial.Serial | None = None
        self._rx_queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False
        self._reader_task: asyncio.Task | None = None
        # Reconnection state
        self._reconnect_delay = 0.5       # initial delay in seconds
        self._reconnect_delay_max = 10.0  # max delay between retries
        self._reconnect_attempts = 0
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self.ser is not None and self.ser.is_open

    async def open(self) -> None:
        if self._running:
            return
        
        # Auto-detect if port is not specified or "auto"
        if not self.port or self.port.lower() == "auto":
            detected = self._detect_port()
            if detected:
                logging.info(f"Auto-detected serial port: {detected}")
                self.port = detected
            else:
                logging.warning("No serial port detected or specified. Serial transport will fail to open.")
        
        await self._open_port()

    async def _open_port(self) -> None:
        """Attempt to open the serial port. Raises on first open failure, reconnects silently."""
        try:
            logging.info(f"Opening serial port {self.port} at {self.baud} baud...")
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self._running = True
            self._is_connected = True
            self._reconnect_attempts = 0
            self._reconnect_delay = 0.5
            self._reader_task = asyncio.create_task(self._reader_loop())
            logging.info("Serial port opened successfully.")
        except serial.SerialException as e:
            self._is_connected = False
            logging.error(f"Failed to open serial port {self.port}: {e}")
            raise

    def _detect_port(self) -> str | None:
        ports = serial.tools.list_ports.comports()
        for p in ports:
            # Common USB-Serial chips (CH340, CP210x, FTDI)
            if "USB" in p.description or "CP210" in p.description or "CH340" in p.description:
                return p.device
        return None

    async def close(self) -> None:
        self._running = False
        self._is_connected = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
            
        if self.ser and self.ser.is_open:
            self.ser.close()
            logging.info("Serial port closed.")

    async def _reconnect(self) -> bool:
        """
        Attempt to reconnect with exponential backoff.
        Returns True if reconnected, False if giving up for now.
        """
        self._is_connected = False
        self._reconnect_attempts += 1
        delay = min(self._reconnect_delay * (2 ** (self._reconnect_attempts - 1)), self._reconnect_delay_max)
        logging.warning(f"Serial disconnected. Reconnect attempt #{self._reconnect_attempts} in {delay:.1f}s...")

        # Close existing port if still open
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        await asyncio.sleep(delay)

        # Re-detect port in case USB was re-plugged
        if not self.port or self.port.lower() == "auto":
            detected = self._detect_port()
            if detected:
                self.port = detected
            else:
                logging.warning("No serial port detected during reconnect.")
                return False

        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self._is_connected = True
            self._reconnect_attempts = 0
            self._reconnect_delay = 0.5
            logging.info(f"Serial port reconnected successfully on {self.port}.")
            return True
        except serial.SerialException as e:
            logging.error(f"Reconnect failed: {e}")
            return False

    async def write_line(self, line: str) -> None:
        if not self.is_connected:
            logging.warning("Attempted to write to closed serial port. Attempting reconnect...")
            if not await self._reconnect():
                return

        try:
            data = (line.strip() + "\n").encode("utf-8")
            await asyncio.to_thread(self.ser.write, data)
        except serial.SerialException as e:
            logging.error(f"Serial write error: {e}")
            self._is_connected = False
            # Try reconnect once and retry the write
            if await self._reconnect():
                try:
                    data = (line.strip() + "\n").encode("utf-8")
                    await asyncio.to_thread(self.ser.write, data)
                except Exception as retry_err:
                    logging.error(f"Serial write retry failed: {retry_err}")

    async def read_line(self, timeout_s: float | None) -> str | None:
        try:
            if timeout_s is None:
                return await self._rx_queue.get()
            return await asyncio.wait_for(self._rx_queue.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    async def health_check(self) -> bool:
        """
        Send a simple ping to the ESP32 and expect a 'pong' response.
        Returns True if healthy, False otherwise.
        """
        if not self.is_connected:
            return False
        try:
            import json as _json
            msg = _json.dumps({"type": "ping", "ts_ms": int(time.time() * 1000)})
            await self.write_line(msg)
            response = await self.read_line(timeout_s=2.0)
            if response:
                data = _json.loads(response)
                return data.get("type") == "pong"
        except Exception as e:
            logging.debug(f"Health check failed: {e}")
        return False

    async def _reader_loop(self) -> None:
        logging.debug("Serial reader loop started.")
        while self._running:
            if not self.ser or not self.ser.is_open:
                # Port lost — attempt reconnect
                if not await self._reconnect():
                    await asyncio.sleep(2.0)
                    continue

            try:
                # Run blocking read in thread
                line = await asyncio.to_thread(self.ser.readline)
                if line:
                    try:
                        decoded = line.decode("utf-8").strip()
                        if decoded:
                            await self._rx_queue.put(decoded)
                    except UnicodeDecodeError:
                        logging.warning(f"Serial decode error: {line}")
            except serial.SerialException as e:
                logging.error(f"Serial reader error (connection lost): {e}")
                self._is_connected = False
                # Will reconnect on next loop iteration
            except Exception as e:
                logging.error(f"Serial reader error: {e}")
                await asyncio.sleep(1)
        logging.debug("Serial reader loop ended.")
