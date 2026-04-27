"""BLE interface for the Concept2 PM5."""
from __future__ import annotations
from typing import Callable, Optional
from bleak import BleakClient, BleakScanner

FORCE_CURVE_CHAR = "CE06003D-43E5-11E4-916C-0800200C9A66"
STROKE_DATA_CHAR = "CE060035-43E5-11E4-916C-0800200C9A66"
HR_CHAR          = "CE06003B-43E5-11E4-916C-0800200C9A66"

ForcePacketCB = Callable[[int, list[float]], None]
StrokeDataCB  = Callable[[dict], None]
HrCB          = Callable[[int], None]


class PM5BLE:
    def __init__(self) -> None:
        self._client: Optional[BleakClient] = None
        self._on_force:  Optional[ForcePacketCB] = None
        self._on_stroke: Optional[StrokeDataCB]  = None
        self._on_hr:     Optional[HrCB]          = None

    def set_callbacks(
        self,
        on_force:  ForcePacketCB = None,
        on_stroke: StrokeDataCB  = None,
        on_hr:     HrCB          = None,
    ) -> None:
        self._on_force  = on_force
        self._on_stroke = on_stroke
        self._on_hr     = on_hr

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def scan(self, timeout: float = 10.0) -> list[dict]:
        devices = await BleakScanner.discover(timeout=timeout)
        return [
            {"name": d.name, "address": d.address}
            for d in devices
            if d.name and "PM5" in d.name
        ]

    async def connect(self, address: str) -> bool:
        try:
            self._client = BleakClient(address)
            await self._client.connect()
            await self._client.start_notify(FORCE_CURVE_CHAR, self._handle_force)
            await self._client.start_notify(STROKE_DATA_CHAR, self._handle_stroke)
            try:
                await self._client.start_notify(HR_CHAR, self._handle_hr)
            except Exception:
                pass  # HR belt not paired — non-fatal
            return True
        except Exception as exc:
            print(f"[PM5BLE] connect error: {exc}")
            self._client = None
            return False

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            for char in [FORCE_CURVE_CHAR, STROKE_DATA_CHAR, HR_CHAR]:
                try:
                    await self._client.stop_notify(char)
                except Exception:
                    pass
            await self._client.disconnect()
        self._client = None

    # ---------------------------------------------------------------- handlers
    def _handle_force(self, _, data: bytearray) -> None:
        if len(data) < 4 or self._on_force is None:
            return
        seq    = data[1]
        values = [
            float(int.from_bytes(data[i:i + 2], "little"))
            for i in range(2, len(data) - 1, 2)
        ]
        self._on_force(seq, values)

    def _handle_stroke(self, _, data: bytearray) -> None:
        if len(data) < 20 or self._on_stroke is None:
            return
        self._on_stroke({
            "elapsed_time": int.from_bytes(data[0:3], "little") * 0.01,
            "distance":     int.from_bytes(data[3:6], "little") * 0.1,
            "drive_length": data[6] * 0.01,
            "stroke_count": int.from_bytes(data[18:20], "little"),
        })

    def _handle_hr(self, _, data: bytearray) -> None:
        if self._on_hr is None or len(data) < 2:
            return
        flags = data[0]
        hr = int.from_bytes(data[1:3], "little") if (flags & 1) else data[1]
        if hr > 0:
            self._on_hr(hr)
