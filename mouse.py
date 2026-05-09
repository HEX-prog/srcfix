import threading
import serial
from serial.tools import list_ports
import time
import random

makcu = None
makcu_lock = threading.Lock()
button_states = {i: False for i in range(5)}
button_states_lock = threading.Lock()
is_connected = False
last_value = 0

SUPPORTED_DEVICES = [
    ("1A86:55D3", "MAKCU"),
    ("1A86:5523", "CH343"),
    ("1A86:7523", "CH340"),
    ("1A86:5740", "CH347"),
    ("10C4:EA60", "CP2102"),
]
BAUD_RATES = [4_000_000, 2_000_000, 115_200]
BAUD_CHANGE_COMMAND = bytearray([0xDE, 0xAD, 0x05, 0x00, 0xA5, 0x00, 0x09, 0x3D, 0x00])

def find_com_ports():
    found = []
    for port in list_ports.comports():
        hwid = port.hwid.upper()
        desc = port.description.upper()
        for vidpid, name in SUPPORTED_DEVICES:
            if vidpid in hwid or name.upper() in desc:
                found.append((port.device, name))
                break
    return found

def km_version_ok(ser):
    try:
        ser.reset_input_buffer()
        ser.write(b"km.version()\r")
        ser.flush()
        time.sleep(0.1)
        resp = b""
        start = time.time()
        while time.time() - start < 0.3:
            if ser.in_waiting:
                resp += ser.read(ser.in_waiting)
                if b"km.MAKCU" in resp or b"MAKCU" in resp:
                    return True
            time.sleep(0.01)
        return False
    except Exception as e:
        print(f"[WARN] km_version_ok: {e}")
        return False

def connect_to_makcu():
    global makcu, is_connected
    ports = find_com_ports()
    if not ports:
        print("[ERROR] No supported serial devices found.")
        return False

    for port_name, dev_name in ports:
        if dev_name == "MAKCU":
            for baud in BAUD_RATES:
                print(f"[INFO] Probing MAKCU {port_name} @ {baud} with km.version()...")
                ser = None
                try:
                    ser = serial.Serial(port_name, baud, timeout=0.3)
                    time.sleep(0.1)
                    if km_version_ok(ser):
                        if baud == 115_200:
                            print("[INFO] MAKCU responded at 115200, sending 4M handshake...")
                            ser.write(BAUD_CHANGE_COMMAND)
                            ser.flush()
                            ser.close()
                            time.sleep(0.15)
                            # --- Always cleanup before opening new connection! ---
                            ser4m = None
                            try:
                                ser4m = serial.Serial(port_name, 4_000_000, timeout=0.3)
                                time.sleep(0.1)
                                if km_version_ok(ser4m):
                                    print(f"[INFO] MAKCU handshake successful, switching to 4M on {port_name}.")
                                    ser4m.close()
                                    time.sleep(0.1)
                                    makcu = serial.Serial(port_name, 4_000_000, timeout=0.1)
                                    with makcu_lock:
                                        makcu.write(b"km.buttons(1)\r")
                                        makcu.flush()
                                    is_connected = True
                                    return True
                                else:
                                    print("[WARN] 4M handshake failed, staying at 115200.")
                                    ser4m.close()
                                    time.sleep(0.1)
                                    makcu = serial.Serial(port_name, 115_200, timeout=0.1)
                                    with makcu_lock:
                                        makcu.write(b"km.buttons(1)\r")
                                        makcu.flush()
                                    is_connected = True
                                    return True
                            except Exception as e:
                                print(f"[WARN] Could not switch to 4M: {e}")
                                if ser4m:
                                    try:
                                        ser4m.close()
                                    except:
                                        pass
                                time.sleep(0.1)
                                makcu = serial.Serial(port_name, 115_200, timeout=0.1)
                                with makcu_lock:
                                    makcu.write(b"km.buttons(1)\r")
                                    makcu.flush()
                                is_connected = True
                                return True
                        else:
                            print(f"[INFO] MAKCU responded at {baud}, using it.")
                            ser.close()
                            time.sleep(0.1)
                            makcu = serial.Serial(port_name, baud, timeout=0.1)
                            with makcu_lock:
                                makcu.write(b"km.buttons(1)\r")
                                makcu.flush()
                            is_connected = True
                            return True
                    ser.close()
                    time.sleep(0.1)
                except Exception as e:
                    print(f"[WARN] Failed MAKCU@{baud}: {e}")
                    if ser:
                        try:
                            ser.close()
                        except:
                            pass
                        time.sleep(0.1)
                    if makcu and makcu.is_open:
                        makcu.close()
                    makcu = None
                    is_connected = False
        else:
            for baud in BAUD_RATES:
                print(f"[INFO] Trying {dev_name} {port_name} @ {baud} ...")
                ser = None
                try:
                    ser = serial.Serial(port_name, baud, timeout=0.1)
                    with makcu_lock:
                        ser.write(b"km.buttons(1)\r")
                        ser.flush()
                    ser.close()
                    time.sleep(0.1)
                    makcu = serial.Serial(port_name, baud, timeout=0.1)
                    is_connected = True
                    print(f"[INFO] Connected to {dev_name} on {port_name} at {baud} baud.")
                    return True
                except Exception as e:
                    print(f"[WARN] Failed {dev_name}@{baud}: {e}")
                    if ser:
                        try:
                            ser.close()
                        except:
                            pass
                        time.sleep(0.1)
                    if makcu and makcu.is_open:
                        makcu.close()
                    makcu = None
                    is_connected = False

    print("[ERROR] Could not connect to any supported device.")
    return False


def count_bits(n: int) -> int:
    return bin(n).count("1")

def listen_makcu():
    global last_value
    # start from a clean state
    last_value = 0
    with button_states_lock:
        for i in range(5):
            button_states[i] = False

    while is_connected:
        try:
            b = makcu.read(1)  # blocking read (uses port timeout)
            if not b:
                continue

            v = b[0]

            # Ignore echoed ASCII (including CR/LF). Only 0..31 are valid masks.
            if v in (0x0A, 0x0D) or v > 31:
                continue

            # v is a 5-bit mask (bit0..bit4). Update only changed bits.
            changed = last_value ^ v
            if changed:
                with button_states_lock:
                    for i in range(5):
                        m = 1 << i
                        if changed & m:
                            button_states[i] = bool(v & m)
                last_value = v

        except serial.SerialException as e:
            print(f"[ERROR] Listener serial exception: {e}")
            break
        except Exception as e:
            # swallow transient errors but keep running
            print(f"[WARN] Listener error: {e}")
            time.sleep(0.001)

    # ensure clean state on exit
    with button_states_lock:
        for i in range(5):
            button_states[i] = False
    last_value = 0

def is_button_pressed(idx: int) -> bool:
    with button_states_lock:
        return button_states.get(idx, False)

def test_move():
    if is_connected:
        with makcu_lock:
            makcu.write(b"km.move(100,100)\r")
            makcu.flush()

# --------------------------------------------------------------------
# Button Lock / Masking helpers
# --------------------------------------------------------------------

# Index mapping: 0=L, 1=R, 2=M, 3=S4, 4=S5
_LOCK_CMD_BY_IDX = {
    0: "lock_ml",
    1: "lock_mr",
    2: "lock_mm",
    3: "lock_ms1",
    4: "lock_ms2",
}

# Legacy single-lock state (kept for compatibility) and new multi-lock state
_mask_applied_idx = None
_mask_applied_indices = set()

def _send_cmd_no_wait(cmd: str):
    """Send 'km.<cmd>\\r' without waiting for response (listener ignores ASCII)."""
    if not is_connected:
        return
    with makcu_lock:
        makcu.write(f"km.{cmd}\r".encode("ascii", "ignore"))
        makcu.flush()

def lock_button_idx(idx: int):
    """Lock a single button by index (0..4)."""
    cmd = _LOCK_CMD_BY_IDX.get(idx)
    if cmd is None:
        return
    _send_cmd_no_wait(f"{cmd}(1)")

def unlock_button_idx(idx: int):
    """Unlock a single button by index (0..4)."""
    cmd = _LOCK_CMD_BY_IDX.get(idx)
    if cmd is None:
        return
    _send_cmd_no_wait(f"{cmd}(0)")

def unlock_all_locks():
    """Best-effort unlock of all lockable buttons."""
    for i in range(5):
        unlock_button_idx(i)

def mask_manager_tick_multi(selected_indices, aimbot_running: bool):
    """Manage locks for *multiple* indices at once."""
    global _mask_applied_indices

    if not is_connected:
        # device not connected -> clear any state
        if _mask_applied_indices:
            try:
                unlock_all_locks()
            except Exception:
                pass
        _mask_applied_indices = set()
        return

    # normalize selection
    desired = set()
    if selected_indices:
        for i in selected_indices:
            if isinstance(i, int) and 0 <= i <= 4:
                desired.add(i)

    if not aimbot_running:
        # unlock everything we think is applied
        for i in list(_mask_applied_indices):
            unlock_button_idx(i)
        _mask_applied_indices = set()
        return

    # Unlock no-longer-desired
    for i in list(_mask_applied_indices - desired):
        unlock_button_idx(i)
    # Lock newly desired
    for i in list(desired - _mask_applied_indices):
        lock_button_idx(i)
    _mask_applied_indices = desired

def mask_manager_tick(selected_idx: int, aimbot_running: bool):
    """Backward-compatible single-index manager (wraps multi)."""
    idxs = [] if selected_idx is None else [selected_idx]
    mask_manager_tick_multi(idxs, aimbot_running)

class Mouse:
    _instance = None
    _listener = None
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_inited"):
            if not connect_to_makcu():
                print("[ERROR] Mouse init failed to connect.")
            else:
                Mouse._listener = threading.Thread(target=listen_makcu, daemon=True)
                Mouse._listener.start()

            self._click_lock = threading.Lock()
            self._click_inflight = False
            self._click_timer = None

            self._inited = True

    def move(self, x: float, y: float):
        if not is_connected:
            return
        dx, dy = int(x), int(y)
        with makcu_lock:
            makcu.write(f"km.move({dx},{dy})\r".encode())
            makcu.flush()

    def move_bezier(self, x: float, y: float, segments: int, ctrl_x: float, ctrl_y: float):
        if not is_connected:
            return
        with makcu_lock:
            cmd = f"km.move({int(x)},{int(y)},{int(segments)},{int(ctrl_x)},{int(ctrl_y)})\r"
            makcu.write(cmd.encode())
            makcu.flush()

    def _release_click(self):
        global is_connected
        try:
            if is_connected:
                with makcu_lock:
                    makcu.write(b"km.left(0)\r")
                    makcu.flush()
        finally:
            with self._click_lock:
                self._click_inflight = False
                self._click_timer = None

    def click(self):
        if not is_connected:
            return

        with self._click_lock:
            if self._click_inflight:
                return  # already clicking, ignore

            self._click_inflight = True
            with makcu_lock:
                makcu.write(b"km.left(1)\r")
                makcu.flush()

            delay = random.uniform(0.075, 0.125)
            self._click_timer = threading.Timer(delay, self._release_click)
            self._click_timer.daemon = True
            self._click_timer.start()

    def left_press(self):
        if not is_connected:
            return
        with makcu_lock:
            makcu.write(b"km.left(1)\r")
            makcu.flush()

    def left_release(self):
        if not is_connected:
            return
        with makcu_lock:
            makcu.write(b"km.left(0)\r")
            makcu.flush()

    @staticmethod
    def mask_manager_tick(selected_idx: int, aimbot_running: bool):
        """Static wrapper so callers can do: Mouse.mask_manager_tick(idx, running)."""
        mask_manager_tick(selected_idx, aimbot_running)
        
    @staticmethod
    def mask_manager_tick_multi(selected_indices, aimbot_running: bool):
        """Static wrapper for the multi-index manager."""
        mask_manager_tick_multi(selected_indices, aimbot_running)

    @staticmethod
    def cleanup():
        global is_connected, makcu, _mask_applied_idx, _mask_applied_indices
        # cancel any pending click release
        inst = Mouse._instance
        if inst is not None:
            with getattr(inst, "_click_lock", threading.Lock()):
                if getattr(inst, "_click_timer", None):
                    try:
                        inst._click_timer.cancel()
                    except Exception:
                        pass
                    inst._click_timer = None
                inst._click_inflight = False

        # Always release any locks before closing port
        try:
            unlock_all_locks()
        except Exception:
            pass
        _mask_applied_idx = None
        _mask_applied_indices = set()

        is_connected = False
        if makcu and makcu.is_open:
            makcu.close()
        Mouse._instance = None
        Mouse._listener = None
        print("[INFO] Mouse serial cleaned up.")
