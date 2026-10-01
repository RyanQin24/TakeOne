"""Read-only diagnosis of the actual COM8/COM9 replies; no register writes."""
import json
import multiprocessing as mp
import time
from pathlib import Path


def capture(args):
    from scservo_sdk import PacketHandler, PortHandler
    from takeone.cart.runtime import host_timing_priority

    name, ids, timeout = args
    port, packet = PortHandler(name), PacketHandler(0)
    result = dict(port=name, serial_read_timeout_s=timeout, cycles=[], errors=[])
    with host_timing_priority():
        if not port.openPort():
            raise RuntimeError(name + " failed to open")
        try:
            port.ser.timeout = timeout
            port.getCurrentTime = lambda: time.perf_counter() * 1000
            port.setPacketTimeout = lambda length: port.setPacketTimeoutMillis(25)
            time.sleep(0.05)
            result["torque"] = {i: packet.read1ByteTxRx(port, i, 40) for i in ids}
            if any(tuple(v) != (0, 0, 0) for v in result["torque"].values()):
                raise RuntimeError(name + " torque-off readback not confirmed")
            original_rx = packet.rxPacket
            def traced_rx(p):
                raw, status = original_rx(p)
                if status:
                    result["errors"].append(dict(time_s=time.perf_counter(), status=status, packet_hex=bytes(raw).hex()))
                return raw, status
            packet.rxPacket = traced_rx
            epoch = time.perf_counter()
            for tick in range(100):
                time.sleep(max(0, epoch + tick * 0.04 - time.perf_counter()))
                start = time.perf_counter()
                reads = []
                for motor_id in ids:
                    begin = time.perf_counter()
                    block, status, error = packet.readTxRx(port, motor_id, 40, 31)
                    reads.append(dict(id=motor_id, duration_s=time.perf_counter()-begin, status=status, error=error, bytes=len(block)))
                result["cycles"].append(dict(start_s=start, duration_s=time.perf_counter()-start, reads=reads))
        finally:
            port.closePort()
    return result


if __name__ == "__main__":
    records = []
    for timeout in (0, 0.001):
        with mp.get_context("spawn").Pool(2) as pool:
            for report in pool.map(capture, [("COM9", [1,2,3,4,6], timeout), ("COM8", [1,2,3,4,5], timeout)]):
                records.append(report)
                durations = sorted(c["duration_s"] for c in report["cycles"])
                print(json.dumps(dict(port=report["port"], timeout_s=timeout, read_errors=len(report["errors"]), max_cycle_s=max(durations), p99_cycle_s=durations[98])), flush=True)
    Path(__file__).with_suffix(".json").write_text(json.dumps(records, indent=2), encoding="utf-8")
