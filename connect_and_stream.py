import asyncio
import sys
from bleak import BleakClient, BleakScanner
from average_force_curve import add_stroke, generate_average_force_curve

FORCE_CURVE_CHAR = "CE06003D-43E5-11E4-916C-0800200C9A66"   # force plot packets

stroke_count = 0
force_buffer: list[float] = []   # samples for the stroke currently being received


def parse_force_packet(data: bytearray) -> tuple[int, list[float]]:
    """
    Packet layout: [0x69 type] [seq uint8] [uint16-LE values...]
    Returns (sequence_number, force_values).
    """
    seq = data[1]
    values = [
        float(int.from_bytes(data[i:i + 2], "little"))
        for i in range(2, len(data) - 1, 2)
    ]
    return seq, values


async def find_pm5() -> str | None:
    print("Scanning for PM5 (10 s)...")
    devices = await BleakScanner.discover(timeout=10)
    for d in devices:
        if d.name and "PM5" in d.name:
            print(f"Found: {d.name}  [{d.address}]")
            return d.address
    return None


def flush_stroke() -> None:
    global stroke_count, force_buffer
    if len(force_buffer) < 5:
        force_buffer = []
        return
    add_stroke(force_buffer)
    stroke_count += 1
    peak = max(force_buffer)
    print(f"Stroke {stroke_count:3d} | {len(force_buffer)} pts | peak = {peak:.0f} N")
    force_buffer = []


async def stream(address: str) -> None:
    global force_buffer

    def on_force_curve(_, data: bytearray) -> None:
        global force_buffer
        seq, values = parse_force_packet(data)

        if seq == 0:
            # New stroke starting — finalise the previous one
            flush_stroke()
            force_buffer = values
        else:
            # Continuation packet — first value repeats the last of the previous packet
            force_buffer.extend(values[1:])

    print(f"Connecting to {address} ...")
    async with BleakClient(address) as client:
        print("Connected. Row! Press Ctrl+C to stop and plot.\n")
        await client.start_notify(FORCE_CURVE_CHAR, on_force_curve)
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        flush_stroke()   # capture the last in-progress stroke
        await client.stop_notify(FORCE_CURVE_CHAR)

    if stroke_count == 0:
        print("\nNo strokes recorded.")
        return

    print(f"\n{stroke_count} strokes recorded. Generating average force curve...")
    generate_average_force_curve()


async def list_characteristics(address: str) -> None:
    async with BleakClient(address) as client:
        for service in client.services:
            print(f"\nService: {service.uuid}")
            for char in service.characteristics:
                print(f"  Char: {char.uuid}  props={char.properties}")


async def main() -> None:
    args = sys.argv[1:]

    if "--list" in args:
        args.remove("--list")
        address = args[0] if args else await find_pm5()
        if not address:
            print("PM5 not found.")
            return
        await list_characteristics(address)
        return

    address = args[0] if args else await find_pm5()
    if not address:
        print("PM5 not found. Make sure it is powered on and in range.")
        return

    await stream(address)


asyncio.run(main())
