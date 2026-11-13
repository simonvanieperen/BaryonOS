#!/usr/bin/env python3
"""Native two-app focus/drag/compositor recovery with disposable media only.

Serial snapshots are observations, not pixel or storage substitutes. This
runner independently checks screenshots, protected chrome and final disk bytes.
"""
from __future__ import annotations
import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid

from common import BUILD, ROOT, TARGET, environment, firmware, qemu_accel, qemu_machine, sha256, source_hash
from build_users import inspect_user
from run_fpu import private_path, publish, publish_json, load_json
from run_graphics import QmpPipe, ppm
from run_system import check_esp, check_image
from run_materiaal_probe import disk_oracle, TEXT, TEXT_SUM
import volume_disk
import window_library

FEATURE = "native-window-session-probe"
HIDPI_FEATURE = "native-window-session-hidpi-probe"
ROUTE_FEATURE = "native-session-route"
NAMES = {"window-init", "window-compositor", "materiaal-app", "calculator-app",
         "keyring-service", "volume-service", "input-source", "input-policy"}
SERIAL_LIMIT = 4 * 1024 * 1024
BODY = (28, 114, 880, 510)
FIXTURE_PHASES = ("initial", "editor", "dirty", "saved", "list", "reopened",
                  "read-tool", "read-tool-blocked", "write-tool-restored",
                  "document-menu", "document-menu-next", "document-menu-read",
                  "document-menu-blocked", "document-menu-cancelled", "document-menu-write",
                  "document-menu-mouse", "document-menu-mouse-cancelled",
                  "document-menu-high-contrast", "document-menu-contrast-restored",
                  "reopened-window-restored",
                  "dirty-focus-lost", "dirty-rebound", "dirty-recovered")
CLIPBOARD_PHASES = ("clipboard-copied", "clipboard-numeric", "clipboard-back",
                    "clipboard-empty", "clipboard-recovered-empty")
CALCULATOR_CLIPBOARD_PHASES = ("clipboard-unsupported", "clipboard-pasted", "clipboard-calculator-copied",
                              "calculator-high-contrast", "calculator-contrast-restored")
CALCULATOR_BODY = (932, 140, 320, 484)
SWITCHER_MAX_PIXELS = 1_400_000
WINDOW_MOVE_OFFSETS = {
    "move-open": (0, 0), "move-coarse": (16, 16), "move-fine": (17, 15),
    "move-committed": (17, 15), "move-cancel-open": (17, 15),
    "move-cancel-step": (1, 15), "move-cancelled": (17, 15), "move-arranged": (0, 0),
}
WORKSPACE_REGIONS = {
    # Exact shell regions only. Existing unmasked full-app oracles stay mandatory.
    # Header rows follow main's 44-pixel trusted shell header.
    "focus-material": ((0, 0, 1280, 44), (920, 90, 344, 550), (0, 650, 1280, 70)),
    "focus-calculator": ((0, 0, 1280, 44), (16, 64, 904, 576), (0, 650, 1280, 70)),
    "work": ((0, 0, 1280, 44), (0, 650, 1280, 70)),
    "search": ((382, 96, 516, 232),),
    "selected": ((0, 0, 1280, 114), (0, 114, 28, 510), (908, 114, 372, 26),
                 (908, 140, 24, 484), (1252, 140, 28, 484), (0, 624, 1280, 96)),
    "window-menu": ((844, 120, 284, 168),),
    "window-menu-next": ((844, 120, 284, 168),),
    "window-minimized": ((16, 64, 904, 576), (0, 650, 1280, 70)),
    "window-empty": ((0, 44, 1280, 676),),
    "window-restored": ((0, 650, 1280, 70),),
    "notice-copied": ((820, 64, 424, 216),),
    "notice-dismissed": ((820, 64, 424, 216),),
    "notice-empty-mouse": ((820, 64, 424, 216),),
    "notice-closed": ((0, 0, 1280, 44), (800, 44, 464, 256)),
}
HIDPI_WORKSPACE_REGIONS = {
    "focus-material": ((0, 0, 1920, 88), (1200, 180, 688, 740), (0, 940, 1920, 140)),
    "focus-calculator": ((0, 0, 1920, 88), (32, 128, 1168, 792), (0, 940, 1920, 140)),
    "work": ((0, 0, 1920, 88), (0, 940, 1920, 140)),
    "search": ((444, 192, 1032, 464),),
    "selected": ((0, 0, 1920, 228), (0, 228, 56, 660), (1176, 228, 744, 52),
                 (1176, 280, 48, 608), (1864, 280, 56, 608), (0, 888, 1920, 192)),
    "window-menu": ((1048, 240, 568, 336),),
    "window-menu-next": ((1048, 240, 568, 336),),
    "window-minimized": ((32, 128, 1168, 792), (0, 940, 1920, 140)),
    "window-empty": ((0, 88, 1920, 992),),
    "window-restored": ((0, 940, 1920, 140),),
    "notice-copied": ((1000, 128, 848, 432),),
    "notice-dismissed": ((1000, 128, 848, 432),),
    "notice-empty-mouse": ((1000, 128, 848, 432),),
    "notice-closed": ((0, 0, 1920, 88), (960, 88, 928, 512)),
}


def profile_geometry(scale: int) -> tuple:
    if scale == 1:
        return (1280, 720, BODY, CALCULATOR_BODY)
    if scale == 2:
        return (1920, 1080, (56, 228, 1120, 660), (1224, 280, 640, 608))
    raise ValueError("Only the native 100% and 200% profiles are supported")


def workspace_regions(scale: int) -> dict:
    profile_geometry(scale)
    return WORKSPACE_REGIONS if scale == 1 else HIDPI_WORKSPACE_REGIONS


def full_scale200_gate(scale: int, workspace: bool, diagnostic: bool, switcher: bool) -> bool:
    """Accept 200% only for the complete workspace gate, never a part gate."""
    return scale == 2 and workspace and not diagnostic and not switcher


def switcher_geometry(scale: int) -> tuple:
    """Return supported viewport and app rectangles for a scale."""
    if scale == 1:
        return (1280, 720, BODY, CALCULATOR_BODY, (330, 214, 620, 292))
    if scale == 2:
        return (1920, 1080, (56, 228, 1120, 660), (1224, 280, 640, 608), (340, 248, 1240, 584))
    raise ValueError("Only 100% and 200% switcher profiles are supported")


def switcher_matches(raw: bytes, expected: bytes, scale: int) -> bool:
    """Compare full native switcher overlay pixels with the host oracle."""
    width, height, _, _, bounds = switcher_geometry(scale)
    return (ppm(raw)[:2] == (width, height) and ppm(expected)[:2] == bounds[2:]
            and crop(raw, bounds) == ppm(expected)[2])


def consecutive_image_matcher():
    """Return a predicate that accepts two consecutive identical images."""
    previous = [None]

    def matches(image: bytes) -> bool:
        """Record one full image and compare it with the preceding capture."""
        stable = previous[0] is not None and image == previous[0]
        previous[0] = image
        return stable

    return matches


def switcher_key_edge(control, move, current, physical: str, down: bool, scale: int):
    """Bind a key edge to an acknowledged marker and two pointer events."""
    width, _, _, _, _ = switcher_geometry(scale)
    y = 50 * scale
    start = current()
    if (start.get("POINTER_X"), start.get("POINTER_Y")) != (width - 20, y):
        move(width - 20, y)
        start = current()
    # This one-event pointer marker is ordered after earlier input. Its exact
    # counter delta prevents a delayed earlier increment from masking a lost key.
    move(width - 22, y)
    marker = current()
    if (marker.get("INPUT") != start.get("INPUT", -2) + 1
            or (marker.get("POINTER_X"), marker.get("POINTER_Y")) != (width - 22, y)):
        raise ValueError("Missing ordered switcher input marker")
    before = marker["INPUT"]
    control.command("input-send-event", {"events": [
        {"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": physical}}}]})
    # Main's probe samples pointer changes, but does not publish every isolated
    # key edge. Two acknowledged header moves form an ordered input barrier.
    move(width - 21, y)
    move(width - 20, y)
    after = current()
    if (after["INPUT"] != before + 3
            or (after["POINTER_X"], after["POINTER_Y"]) != (width - 20, y)):
        raise ValueError("Missing ordered switcher input barrier")


def generate_switcher_fixture(directory: Path, image: bytes, scale: int) -> dict:
    """Generate a host oracle from complete native application backing."""
    width, height, body, calc, _ = switcher_geometry(scale)
    if ppm(image)[:2] != (width, height):
        raise ValueError("Wrong native backing capture dimensions")
    backing = array("I", [0]) * SWITCHER_MAX_PIXELS
    if backing.itemsize != 4:
        raise ValueError("Host cannot encode 32-bit backing")
    offset = 0
    for rectangle in (body, calc):
        pixels = crop(image, rectangle)
        for at in range(0, len(pixels), 3):
            backing[offset + at // 3] = int.from_bytes(pixels[at:at + 3], "big")
        offset += rectangle[2] * rectangle[3]
    if sys.byteorder != "little":
        backing.byteswap()
    publish(directory / "backing.bin", backing.tobytes())
    env = environment()
    env.update(CARGO_TARGET_DIR=str(private_path(TARGET / "window-switcher-fixture")),
               OS_SWITCHER_FIXTURE_DIRECTORY=str(directory), OS_SWITCHER_FIXTURE_SCALE=str(scale))
    command = ["cargo", "+1.90.0", "test", "--offline", "--locked", "--manifest-path",
               str(ROOT / "sdk/examples/window-session/Cargo.toml"), "--test", "switcher_native_fixture"]
    with (directory / "switcher-generator.log").open("xb") as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                timeout=180, check=False)
    if result.returncode:
        raise ValueError("Native-backing host oracle failed: " + str(directory))
    paths = [directory / "backing.bin", directory / "switcher-generator.log",
             directory / "switcher-0.ppm", directory / "switcher-1.ppm"]
    return dict(directory=directory, frames={index: (directory / f"switcher-{index}.ppm").read_bytes()
                                            for index in (0, 1)},
                metadata=dict(kind="host shell reference using captured native app backing; not native execution",
                              source_sha256=source_hash(), generator_commands=[command], generator_exit=0,
                              native_backing_capture_sha256=hashlib.sha256(image).hexdigest(),
                              files_sha256={path.name: sha256(path) for path in paths}))
SNAPSHOT_FIELDS = {
    "MATERIAL": {"PID", "SERVICE_GENERATION", "SURFACE_EPOCH", "INPUT_EPOCH", "READY", "GEN", "FRAMES",
                 "SAVE_ACKS", "REVISION", "SAVED_BYTES", "SAVED_SUM", "SCREEN", "DIRTY", "DRAFT_BYTES", "DRAFT_SUM", "OBJECT", "SCALE", "ERRORS", "PROBES"},
    "CALCULATOR": {"PID", "SERVICE_GENERATION", "SURFACE_EPOCH", "INPUT_EPOCH", "READY", "GEN", "FRAMES",
                   "EVALUATIONS", "FAILURES", "EXPRESSION_BYTES", "EXPRESSION_SUM", "CURRENT", "CARET", "ACTIVE", "SCALE", "ERRORS", "ANSWER_LOW", "ANSWER_HIGH", "HAS_ANSWER", "PROBES"},
    "COMPOSITOR": {"GENERATION", "PID", "COMMITS", "INPUT", "REJECTED", "FOCUSED", "MOVES", "SWITCHES", "MATERIAL", "CALCULATOR", "FATAL", "POINTER_X", "POINTER_Y", "BUTTONS", "SHELL", "SHELL_READY"},
}


def generate_fixture(*, clipboard: bool = False, workspace: bool = False, scale: int = 1, library: bool = False) -> dict:
    if library and (clipboard or workspace or scale != 1):
        raise ValueError("Library and clipboard have separate complete oracles")
    directory = private_path(BUILD / ("window-fixture-" + uuid.uuid4().hex))
    directory.mkdir(parents=True)
    frozen = source_hash()
    env = environment()
    env["CARGO_TARGET_DIR"] = str(private_path(TARGET / "window-fixture"))
    env["OS_WINDOW_FIXTURE_DIRECTORY"] = str(directory)
    env["OS_WINDOW_SHELL_SCALE"] = str(scale)
    env["OS_WINDOW_SHELL_CLIPBOARD"] = "1" if clipboard else "0"
    width, height, body, calculator_body = profile_geometry(scale)
    command = ["cargo", "+1.90.0", "test", "--offline", "--locked", "--manifest-path",
               str(ROOT / "ui/native/Cargo.toml"), "--test",
               "library_native_fixture" if library else "window_native_fixture", "--", "--nocapture"]
    commands = [command]
    if clipboard:
        commands.append(["cargo", "+1.90.0", "test", "--offline", "--locked", "--manifest-path",
                         str(ROOT / "sdk/examples/calculator/Cargo.toml"), "--test",
                         "clipboard_native_fixture", "--", "--nocapture"])
    if workspace:
        commands.append(["cargo", "+1.90.0", "test", "--offline", "--locked", "--manifest-path",
                         str(ROOT / "sdk/examples/window-session/Cargo.toml"), "--test",
                         "workspace_native_fixture", "--", "--nocapture"])
    with (directory / "generator.log").open("xb") as log:
        for generated in commands:
            result = subprocess.run(generated, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=False)
            if result.returncode:
                break
    if result.returncode or source_hash() != frozen:
        raise ValueError("Host fixture failed or source changed: " + str(directory))
    hashes, frames = {}, {}
    for size in ("880x510", "1120x660"):
        for phase in (window_library.PHASES if library else FIXTURE_PHASES) + (CLIPBOARD_PHASES if clipboard else ()):
            path = private_path(directory / f"{size}-{phase}.ppm", regular=True)
            if path.stat().st_size > 3 * 1120 * 660 + 128:
                raise ValueError("Oversized oracle")
            raw = path.read_bytes()
            if ppm(raw)[:2] != tuple(map(int, size.split("x"))):
                raise ValueError("Wrong host oracle dimensions")
            hashes[path.name] = sha256(path)
            if size == f"{body[2]}x{body[3]}":
                frames[phase] = raw
    if clipboard:
        for size in ("320x484", "640x608"):
            for phase in CALCULATOR_CLIPBOARD_PHASES:
                path = private_path(directory / f"calculator-{size}-{phase}.ppm", regular=True)
                if path.stat().st_size > 3 * 640 * 608 + 128:
                    raise ValueError("Oversized calculator oracle")
                raw = path.read_bytes()
                if ppm(raw)[:2] != tuple(map(int, size.split("x"))):
                    raise ValueError("Wrong calculator oracle dimensions")
                hashes[path.name] = sha256(path)
                if size == f"{calculator_body[2]}x{calculator_body[3]}":
                    frames[phase] = raw
    if workspace:
        for phase in (*workspace_regions(scale), *WINDOW_MOVE_OFFSETS):
            path = private_path(directory / f"workspace-{phase}.ppm", regular=True)
            raw = path.read_bytes()
            if ppm(raw)[:2] != (width, height):
                raise ValueError("Wrong shell oracle dimensions")
            hashes[path.name] = sha256(path)
            frames["workspace-" + phase] = raw
    metadata = dict(kind="host-rendered real Controller/Frame oracle; not native execution",
                    source_sha256=frozen, source_fingerprint_version=3, generator_command=command,
                    generator_commands=commands, clipboard_oracles=clipboard, library_oracles=library,
                    workspace_regions=workspace_regions(scale) if workspace else {},
                    window_move_offsets=WINDOW_MOVE_OFFSETS if workspace else {},
                    scale=scale, viewport=[width, height],
                    generator_exit=result.returncode, files_sha256=hashes)
    publish_json(directory / "fixture.json", metadata)
    return dict(directory=directory, metadata=metadata, frames=frames)


def crop(raw: bytes, rectangle: tuple) -> bytes:
    width, height, pixels = ppm(raw)
    x, y, w, h = rectangle
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > width or y + h > height:
        raise ValueError("Crop exceeds actual framebuffer")
    return b"".join(pixels[((y + row) * width + x) * 3:((y + row) * width + x + w) * 3] for row in range(h))


def workspace_matches(raw: bytes, expected: bytes, phase: str, scale: int = 1) -> bool:
    size = profile_geometry(scale)[:2]
    if ppm(raw)[:2] != size or ppm(expected)[:2] != size:
        return False
    return all(crop(raw, r) == crop(expected, r) for r in workspace_regions(scale)[phase])

def notification_closed_matches(raw: bytes, shell: bytes, before: bytes, scale: int) -> bool:
    size = profile_geometry(scale)[:2]
    if any(ppm(image)[:2] != size for image in (raw, shell, before)):
        return False
    header, restored = workspace_regions(scale)["notice-closed"]
    # App pixels under this panel come from the verified real pre-open frame,
    # not from a shell fixture with zero-filled app backing.
    return crop(raw, header) == crop(shell, header) and crop(raw, restored) == crop(before, restored)

def notification_overlap_point(scale: int) -> tuple:
    width, _, _, calculator = profile_geometry(scale)
    point = (width - 180 * scale, 180 * scale)
    x, y, w, h = calculator
    if not (x <= point[0] < x + w and y <= point[1] < y + h):
        raise ValueError("Notification isolation probe does not overlap a real app")
    return point


def material_matches(raw: bytes, expected: bytes, body: tuple = BODY) -> bool:
    return ppm(expected)[:2] == body[2:] and crop(raw, body) == ppm(expected)[2]


def calculator_matches(raw: bytes, expected: bytes, body: tuple = CALCULATOR_BODY) -> bool:
    return ppm(expected)[:2] == body[2:] and crop(raw, body) == ppm(expected)[2]

def window_move_matches(raw: bytes, shell: bytes, app: bytes, phase: str, scale: int) -> bool:
    width, height, body, _ = profile_geometry(scale)
    dx, dy = WINDOW_MOVE_OFFSETS[phase]
    moved = (body[0] + dx * scale, body[1] + dy * scale, *body[2:])
    return (ppm(raw)[:2] == (width, height) and ppm(shell)[:2] == (width, height)
            and material_matches(raw, app, moved) and not changed_outside(shell, raw, moved))


def calculator_recall_matches(state: dict, baseline: dict, expression: bytes,
                              current: bool, evaluations: int, answer: int) -> bool:
    expected = {"EXPRESSION_BYTES": len(expression), "EXPRESSION_SUM": volume_disk.fnv(expression),
                "CARET": len(expression), "CURRENT": int(current), "EVALUATIONS": evaluations,
                "FAILURES": 0, "ERRORS": 0, "HAS_ANSWER": 1, "READY": 1, "ACTIVE": 1,
                "ANSWER_LOW": answer, "ANSWER_HIGH": 0}
    expected.update({name: baseline[name] for name in
                     ("PID", "SERVICE_GENERATION", "SURFACE_EPOCH", "INPUT_EPOCH", "PROBES", "SCALE")})
    return all(state.get(name) == value for name, value in expected.items())


def calculator_undo_matches(state: dict, baseline: dict, expression: bytes, current: bool,
                            evaluations: int) -> bool:
    expected = {"EXPRESSION_BYTES": len(expression), "EXPRESSION_SUM": volume_disk.fnv(expression),
                "CARET": len(expression), "CURRENT": int(current), "EVALUATIONS": evaluations,
                "FAILURES": 0, "ERRORS": 0, "HAS_ANSWER": 1,
                "ANSWER_LOW": 5_000_000_000, "ANSWER_HIGH": 0, "READY": 1, "ACTIVE": 1}
    expected.update({name: baseline[name] for name in
                     ("PID", "SERVICE_GENERATION", "SURFACE_EPOCH", "INPUT_EPOCH", "PROBES", "SCALE")})
    return all(state.get(name) == value for name, value in expected.items())


def calculator_result_matches(state: dict, baseline: dict, expression: bytes,
                               evaluations: int, answer: int) -> bool:
    expected = {"EXPRESSION_BYTES": len(expression), "EXPRESSION_SUM": volume_disk.fnv(expression),
                "CARET": len(expression), "CURRENT": 1, "EVALUATIONS": evaluations,
                "FAILURES": 0, "ERRORS": 0, "HAS_ANSWER": 1, "READY": 1, "ACTIVE": 1,
                "ANSWER_LOW": answer, "ANSWER_HIGH": 0}
    expected.update({name: baseline[name] for name in
                     ("PID", "SERVICE_GENERATION", "SURFACE_EPOCH", "INPUT_EPOCH", "PROBES", "SCALE")})
    return all(state.get(name) == value for name, value in expected.items())


def oracle_matches(raw: bytes, expected: bytes, name: str, scale: int = 1) -> bool:
    _, _, body, calculator_body = profile_geometry(scale)
    if name in CALCULATOR_CLIPBOARD_PHASES:
        return calculator_matches(raw, expected, calculator_body)
    return material_matches(raw, expected, body)


def changed_outside(before: bytes, after: bytes, rectangle: tuple) -> bool:
    width, height, old = ppm(before)
    w2, h2, new = ppm(after)
    if (width, height) != (w2, h2):
        raise ValueError("Framebuffer geometry changed")
    crop(before, rectangle)  # Validate bounds before indexing.
    x, y, w, h = rectangle
    for row in range(height):
        start, end = row * width * 3, (row + 1) * width * 3
        if y <= row < y + h:
            left, right = start + x * 3, start + (x + w) * 3
            if old[start:left] != new[start:left] or old[right:end] != new[right:end]:
                return True
        elif old[start:end] != new[start:end]:
            return True
    return False


def serial(path: Path) -> bytes:
    if not path.exists():
        return b""
    path = private_path(path, regular=True)
    if path.stat().st_size > SERIAL_LIMIT:
        raise ValueError("Oversized native serial")
    raw = path.read_bytes()
    raw.decode("utf-8", "strict")
    if b"WINDOW:FAIL:" in raw or b"PANIC" in raw or b"\0" in raw:
        raise ValueError("Native guest failed")
    return raw


def snapshots(raw: bytes, role: str) -> list[dict]:
    if role not in SNAPSHOT_FIELDS:
        raise ValueError("Unknown native role")
    prefix = f"WINDOW:{role}:"
    result = []
    for match in re.finditer(re.escape(prefix + "SNAPSHOT:BEGIN\n") + r"(.*?)" +
                             re.escape(prefix + "SNAPSHOT:END\n"), raw.decode("utf-8", "strict"), re.S):
        current = {}
        for line in match[1].splitlines():
            field = re.fullmatch(re.escape(prefix) + r"([A-Z_]+):([0-9]{20})", line)
            if field is None or field[1] in current or int(field[2]) > (1 << 64) - 1:
                raise ValueError("Malformed/duplicate native app snapshot")
            current[field[1]] = int(field[2])
        valid = (current.get("GENERATION", 0) > 0 and current.get("PID", 0) > 0 and current.get("FATAL") == 0) if role == "COMPOSITOR" else (current.get("READY") == 1 and current.get("GEN", 0) > 0)
        if set(current) != SNAPSHOT_FIELDS[role] or not valid:
            raise ValueError("Unready native app snapshot")
        result.append(current)
    return result


def numbers(raw: bytes, name: str) -> list[int]:
    return [int(m[1]) for m in re.finditer(rb"(?:^|\n)" + re.escape(name.encode()) + rb":([0-9]{20})\n", raw)]


def app_input_progress(raw: bytes) -> dict:
    progress = {}
    for role in ("MATERIAL", "CALCULATOR"):
        progress[role] = {}
        for field in ("KEYS", "INPUT_ACKS"):
            values = numbers(raw, f"WINDOW:{role}:{field}")
            if not values:
                raise ValueError(f"Missing native input progress: {role}:{field}")
            progress[role][field] = values[-1]
    return progress


def notification_resync_matches(before: dict, after: dict, *, alt_open: bool = False) -> bool:
    for role in ("MATERIAL", "CALCULATOR"):
        keys = after[role]["KEYS"] - before[role]["KEYS"]
        allowed_keys = (0, 1) if alt_open and role == "MATERIAL" else (0,)
        # Opening cancels each queue once; the preceding Alt press may already
        # have been acknowledged or be superseded by that cancellation.
        if keys not in allowed_keys or after[role]["INPUT_ACKS"] - before[role]["INPUT_ACKS"] != keys + 1:
            return False
    return True


def validate_build(frozen: str, feature: str = FEATURE, scale: int = 1) -> dict:
    switcher_geometry(scale)
    manifest = load_json(private_path(BUILD / "manifest.json", regular=True))
    expected_feature = FEATURE if scale == 1 else "native-window-session-hidpi-probe"
    if feature == "native-session-route":
        if scale != 1:
            raise ValueError("The public session route requires the 100% profile")
        loader = "desktop-mode"
    else:
        if feature != expected_feature:
            raise ValueError("Window feature does not match the requested scale")
        loader = "desktop-mode" if scale == 1 else "desktop-hidpi"
    if (manifest.get("kernel_feature") != feature or manifest.get("loader_feature") != loader
            or manifest.get("source_sha256") != frozen or manifest.get("source_fingerprint_version") != 3):
        raise ValueError("Build the unchanged native window probe first")
    check_esp(BUILD / "esp", manifest)
    apps = manifest.get("materiaal", {}).get("apps", [])
    if len(apps) != len(NAMES) or {a["name"] for a in apps} != NAMES:
        raise ValueError("Wrong native app set")
    kernel = private_path(BUILD / "esp/kernel.elf", regular=True).read_bytes()
    for app in apps:
        path = private_path(BUILD / "users/materiaal" / (app["name"] + ".elf"), regular=True)
        if app != {"name": app["name"], "sha256": sha256(path), "elf": inspect_user(path)} or path.read_bytes() not in kernel:
            raise ValueError("Native app identity/embedding differs")
    return manifest


# Harness deadlines, not latency budgets. 1800 s is the preregistered bound of
# the 1280x720 route (docs/implementation/NATIVE-CLIPBOARD.md). The 200% route
# renders four times the pixels and needs about 1480 s on fast and about 2150 s
# on slower standard hosted runners (ADR-WINDOW-SCALE2-DEADLINE-20261112).
MAX_TIMEOUT_BY_SCALE = {1: 1800, 2: 2700}


def run(*, timeout: int, bios_rom: Path, vga_rom: Path, smoke: bool = False,
        recovery_handshake: bool = False, clipboard: bool = False, workspace: bool = False,
        switcher: bool = False, scale: int = 1, session_route: bool = False,
        library: bool = False, library_parent: Path | None = None,
        calculator_recall: bool = False, calculator_undo: bool = False,
        calculator_result: bool = False) -> dict:
    limit = MAX_TIMEOUT_BY_SCALE.get(scale, MAX_TIMEOUT_BY_SCALE[1])
    if not 30 <= timeout <= limit:
        raise ValueError(f"Timeout must be bounded 30..{limit} seconds at scale {scale}")
    if smoke and recovery_handshake or (clipboard or workspace) and (smoke or recovery_handshake):
        raise ValueError("Clipboard/workspace require the full native gate; choose one diagnostic mode")
    if switcher and (smoke or recovery_handshake or clipboard or workspace) or scale != 1 and not (switcher or workspace):
        raise ValueError("Scale 2 requires the separate switcher or workspace native part gate")
    if session_route and (smoke or recovery_handshake or clipboard or workspace or switcher or library
                          or calculator_recall or calculator_undo or calculator_result):
        raise ValueError("The public session route is separate from the fault/clipboard gate")
    if library and (smoke or recovery_handshake or clipboard or workspace or session_route or switcher
                    or calculator_recall or calculator_undo or calculator_result) or library_parent is not None and not library:
        raise ValueError("Library requires its separate complete walkthrough")
    if calculator_recall and (smoke or recovery_handshake or clipboard or workspace or session_route or library or switcher
                              or calculator_undo or calculator_result):
        raise ValueError("Calculator recall is a separate interaction gate")
    if calculator_undo and (smoke or recovery_handshake or clipboard or workspace or session_route or library or switcher or calculator_recall or calculator_result):
        raise ValueError("Calculator undo is a separate interaction gate")
    if calculator_result and (smoke or recovery_handshake or clipboard or workspace or session_route or library or switcher
                              or calculator_recall or calculator_undo):
        raise ValueError("Calculator result transfer is a separate interaction gate")
    calculator = calculator_recall or calculator_undo or calculator_result
    width, height, body, calculator_body = profile_geometry(scale)
    switcher_bounds = switcher_geometry(scale)[4]
    feature = ("native-session-route" if session_route else
               "native-window-session-hidpi-probe" if scale == 2 else FEATURE)
    diagnostic = smoke or recovery_handshake or session_route or library
    private_path(BUILD)
    frozen = source_hash()
    manifest = validate_build(frozen, feature, scale)
    fixture = (generate_fixture(library=True) if library else
               None if diagnostic or switcher or calculator else
               generate_fixture(clipboard=clipboard, workspace=workspace, scale=scale))
    parent = window_library.cold_parent(library_parent, source=frozen, manifest=manifest) if library_parent is not None else None
    env = environment()
    qemu = Path(shutil.which("qemu-system-x86_64", path=env["PATH"]) or "missing")
    qemu_hash = sha256(qemu)
    code, variables = firmware()
    directory = private_path(BUILD / "run" / ("window-" + uuid.uuid4().hex))
    directory.mkdir(parents=True)
    shutil.copytree(BUILD / "esp", directory / "esp")
    check_esp(directory / "esp", manifest)
    for original, name, limit in ((code, "OVMF_CODE.fd", 16 << 20), (variables, "OVMF_VARS.template.fd", 16 << 20),
                                  (variables, "OVMF_VARS.fd", 16 << 20), (bios_rom, "bios-256k.bin", 1 << 20), (vga_rom, "VGA.rom", 1 << 20)):
        info = original.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= limit:
            raise ValueError("Invalid external firmware/ROM")
        publish(directory / name, original.read_bytes())
    if parent is None:
        volume_disk.create_image(directory / "volume.img", "empty")
    else:
        publish(directory / "volume.img", parent["image"])
    check_image(directory / "volume.img")
    immutable = {p.relative_to(directory).as_posix(): sha256(p) for p in directory.rglob("*")
                 if p.is_file() and p.name not in {"OVMF_VARS.fd", "volume.img"}}
    originals = {str(p): sha256(p) for p in (code, variables, bios_rom, vga_rom)}
    command = [str(qemu), "-L", ".", "-machine", qemu_machine(), "-accel", qemu_accel(), "-cpu", "qemu64", "-smp", "1", "-m", "256M",
               "-nodefaults", "-display", "none", "-monitor", "none", "-serial", "file:serial.txt", "-nic", "none", "-no-reboot",
               "-device", "VGA,vgamem_mb=16,romfile=VGA.rom", "-qmp", "stdio",
               "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
               "-drive", "if=pflash,unit=0,format=raw,readonly=on,file=OVMF_CODE.fd",
               "-drive", "if=pflash,unit=1,format=raw,file=OVMF_VARS.fd",
               "-drive", "if=virtio,index=0,format=raw,readonly=on,file=fat:esp",
               "-object", "rng-random,id=rng0,filename=/dev/urandom", "-device", "virtio-rng-pci,rng=rng0,id=rng,addr=0x6,disable-legacy=on,max-bytes=1048576,period=1000",
               "-drive", "if=none,id=volume,format=raw,cache=writeback,file=volume.img",
               "-device", "virtio-blk-pci,drive=volume,id=volblk,addr=0x5,disable-legacy=on,num-queues=1,queue-size=8,serial=NOS-SYSTEM-TEST"]
    if parent is not None and (parent["qemu_sha256"] != qemu_hash or parent["command"] != command):
        raise ValueError("Cold library emulator or configuration differs from parent")
    start = time.monotonic()
    deadline = start + timeout
    report = dict(schema_version=1, passed=False, native_gate=False, smoke_only=diagnostic and not library,
                  recovery_handshake_only=recovery_handshake, clipboard_requested=clipboard, clipboard_gate=False, source_sha256=frozen,
                  workspace_requested=workspace, workspace_gate=False,
                  document_tools_gate=False, document_menu_gate=False, pointer_leave_gate=False,
                  app_high_contrast_gate=False,
                  keyboard_window_move_gate=False,
                  notification_panel_gate=False,
                  window_states_gate=False,
                  source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  source_fingerprint_version=3, kernel_feature=manifest["kernel_feature"], manifest=manifest, command=command,
                  switcher_requested=switcher, switcher_gate=False, scale=scale, viewport=[width, height],
                  session_route_requested=session_route, session_route_gate=False,
                  library_requested=library, library_gate=False, library_cold=parent is not None,
                  library_parent=None if parent is None else {k: v for k, v in parent.items() if k != "image"},
                  native_scale200_gate=False, trusted_lock_gate=False, locked_f7_gate=False,
                  run_directory=str(directory), qemu_sha256=qemu_hash, immutable=immutable, phases={})
    if calculator_recall:
        report.update(calculator_recall_requested=True, calculator_recall_gate=False,
                      interaction_scope="Native calculator recall, unfinished draft restoration, app-body pixel roundtrips and clean exit; not recovery/storage/full window-session acceptance.")
    if calculator_undo:
        report.update(calculator_undo_requested=True, calculator_undo_gate=False,
                      interaction_scope="Native calculator undo/redo, app-body pixel roundtrips and clean exit; not recovery/storage/full window-session acceptance.")
    if calculator_result:
        report.update(calculator_result_requested=True, calculator_result_gate=False,
                      interaction_scope="Native current-result selection by keyboard/mouse and actual clipboard transfer into Material; save ACK and clean exit, not complete recovery/storage/window-session acceptance.")
    publish_json(directory / "result.json", report)
    report["boot_milestone_observations"] = {}
    def observed_serial():
        raw = serial(directory / "serial.txt")
        # First-observed host bounds, never invented guest phase durations.
        for label, marker in (
            ("firmware_exit", b"BOOT:EBS_OK\n"),
            ("kernel_entry", b"KERNEL:ENTRY\n"),
            ("kernel_memory_ready", b"KS-03:PASS\n"),
            ("process_manifest_ready", b"WINDOW:MANIFEST:PASS\n"),
            ("required_services_ready", b"WINDOW:INITMASK:00000000000000000031\n"),
            ("material_complete_frame", b"WINDOW:MATERIAL:READY:00000000000000000001\n"),
            ("calculator_complete_frame", b"WINDOW:CALCULATOR:READY:00000000000000000001\n"),
        ):
            if marker in raw and label not in report["boot_milestone_observations"]:
                report["boot_milestone_observations"][label] = {
                    "first_observed_seconds": time.monotonic() - start,
                    "scope": "host monotonic polling bound; not exact guest duration"}
        return raw
    process = control = None
    cpu_before = None
    try:
        with (directory / "stderr.txt").open("xb") as stderr:
            cpu_before = os.times() if os.name == "posix" else None
            process = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, bufsize=0)
            control = QmpPipe(process, deadline)

            implementation = Path(os.readlink(f"/proc/{process.pid}/exe"))
            implementation_hash = sha256(implementation)
            if parent is not None and parent["qemu_implementation_sha256"] != implementation_hash:
                raise ValueError("Cold library QEMU implementation differs from parent")
            report["qemu_implementation"] = {"path": str(implementation), "sha256": implementation_hash}
            captured = {}
            group_generation = [1]

            def comp(raw):
                values = snapshots(raw, "COMPOSITOR")
                return values[-1] if values else {}

            def observe(label, predicate, *, timeout_s=None):
                observation_deadline = deadline if timeout_s is None else min(deadline, time.monotonic() + timeout_s)
                while True:
                    raw = observed_serial()
                    if predicate(raw):
                        return raw
                    if process.poll() is not None or time.monotonic() >= observation_deadline:
                        raise TimeoutError("Native input acknowledgement missing: " + label)
                    time.sleep(0.02)

            action_started = [None]
            def wait(name, predicate, oracle=None, image_check=None):
                while True:
                    raw = observed_serial()
                    state = {role: snapshots(raw, role) for role in ("MATERIAL", "CALCULATOR")}
                    if predicate(raw, state):
                        path = private_path(directory / "candidate.ppm", regular=(directory / "candidate.ppm").exists())
                        control.command("screendump", {"filename": str(path)})
                        image = private_path(path, regular=True).read_bytes()
                        if ppm(image)[:2] != (width, height):
                            raise ValueError("Wrong actual GOP size")
                        if (oracle is not None and not oracle_matches(image, fixture["frames"][oracle], oracle, scale)) or (image_check is not None and not image_check(image)):
                            if time.monotonic() >= deadline:
                                raise TimeoutError("Native pixels differ from complete host oracle: " + name)
                            time.sleep(0.2)
                            continue
                        final_path = private_path(directory / (name + ".ppm"))
                        publish(final_path, image)
                        captured[name] = image
                        report["phases"][name] = {"seconds": time.monotonic() - start, "state": {r: s[-1] for r, s in state.items() if s}, "frame_sha256": sha256(final_path), "oracle": oracle}
                        if oracle is not None and action_started[0] is not None:
                            report["phases"][name]["last_input_to_verified_app_image_s"] = time.monotonic() - action_started[0]
                            report["phases"][name]["latency_scope"] = "Conservative host/QMP/observation/capture interval from last key chord to exact full app-body oracle; not whole-screen/guest/scanout latency or U02 budget acceptance."
                        print("WINDOW phase " + name + " " + str(round(time.monotonic() - start, 2)), flush=True)
                        return state
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise TimeoutError("Native phase did not complete: " + name)
                    time.sleep(0.05)

            def key(*keys):
                raw = observed_serial()
                current = comp(raw)
                if current.get("GENERATION") != group_generation[0]:
                    raise ValueError("Keyboard injection lacks a current compositor observation")
                role = "CALCULATOR" if current["FOCUSED"] == 1 else "MATERIAL"
                old_keys = numbers(raw, f"WINDOW:{role}:KEYS")[-1]
                old_acks = numbers(raw, f"WINDOW:{role}:INPUT_ACKS")[-1]
                action_started[0] = time.monotonic()
                control.command("send-key", {"keys": [{"type": "qcode", "data": k} for k in keys], "hold-time": 1})
                if keys == ("f6",):
                    observe("F6 focus", lambda raw: comp(raw).get("GENERATION") == group_generation[0] and comp(raw).get("FOCUSED") == 1-current["FOCUSED"])
                elif keys not in (("f10",), ("f12",)):
                    # The compositor consumes Delete itself; the four genuine
                    # modifier edges still reach the focused application.
                    count = 4 if keys == ("ctrl", "shift", "delete") else 2*len(keys)
                    observe("/".join(keys), lambda raw: numbers(raw, f"WINDOW:{role}:KEYS")[-1] >= old_keys+count and numbers(raw, f"WINDOW:{role}:INPUT_ACKS")[-1] >= old_acks+count)

            def shell_key(*keys):
                before = comp(serial(directory / "serial.txt"))
                # Observe the real press before releasing; never retry toggles.
                control.command("input-send-event", {"events": [
                    {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": k}}}
                    for k in keys]})
                observe("shell press " + "/".join(keys), lambda raw:
                        comp(raw).get("GENERATION") == group_generation[0] and
                        comp(raw).get("INPUT", 0) >= before["INPUT"] + len(keys), timeout_s=30)
                control.command("input-send-event", {"events": [
                    {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": k}}}
                    for k in reversed(keys)]})
                observe("shell release " + "/".join(keys), lambda raw:
                        comp(raw).get("GENERATION") == group_generation[0] and
                        comp(raw).get("INPUT", 0) >= before["INPUT"] + 2 * len(keys), timeout_s=30)

            def workspace_wait(phase):
                return wait("workspace-" + phase, lambda raw, s: all(s.values()),
                            image_check=lambda image: workspace_matches(
                                image, fixture["frames"]["workspace-" + phase], phase, scale))

            pointer = [0, 0]
            def move(x, y):
                while pointer != [x, y]:
                    changes = [max(-96, min(96, target - current)) for target, current in zip((x, y), pointer)]
                    events = [{"type": "rel", "data": {"axis": axis, "value": delta}} for axis, delta in zip(("x", "y"), changes) if delta]
                    control.command("input-send-event", {"events": events})
                    pointer[:] = [current + delta for current, delta in zip(pointer, changes)]
                    observe("pointer", lambda raw: comp(raw).get("GENERATION") == group_generation[0] and (comp(raw).get("POINTER_X"), comp(raw).get("POINTER_Y")) == tuple(pointer))

            def button(down):
                control.command("input-send-event", {"events": [{"type": "btn", "data": {"down": down, "button": "left"}}]})
                observe("mouse button", lambda raw: comp(raw).get("GENERATION") == group_generation[0] and comp(raw).get("BUTTONS") == int(down))

            def select_title(x, y, index):
                move(x, y); button(True); button(False)
                observe("mouse focus", lambda raw: comp(raw).get("GENERATION") == group_generation[0] and comp(raw).get("FOCUSED") == index)

            initial = None if recovery_handshake or session_route or library else wait("boot", lambda raw, s: all(s.values()) and 31 in numbers(raw, "WINDOW:INITMASK"))
            if library:
                observe("library app frames", lambda raw:
                    all(snapshots(raw, role) for role in ("MATERIAL", "CALCULATOR"))
                    and comp(raw).get("GENERATION") == 1)
                move(1260, 50)
                window_library.walkthrough(key=key, wait=wait, cold=parent is not None)
                key("f10")
            elif session_route:
                # These are real compositor/input states plus unmasked captured
                # frames. They do not certify a credential/keyring boundary or
                # the existing crash/storage/clipboard gate.
                def shell_page(name, page):
                    return wait(name, lambda raw, state: comp(raw).get("SHELL") == page
                                and comp(raw).get("SHELL_READY") == 1)

                def shell_key(*codes):
                    before = comp(observed_serial())["INPUT"]
                    control.command("send-key", {"keys": [{"type": "qcode", "data": k} for k in codes], "hold-time": 1})
                    observe("shell input ACK", lambda raw: comp(raw).get("INPUT", 0) > before)

                shell_page("lock", 0)
                observe("bounded app input counters", lambda raw: all(numbers(raw, f"WINDOW:{r}:KEYS") for r in ("MATERIAL", "CALCULATOR")))
                before = {r: numbers(observed_serial(), f"WINDOW:{r}:KEYS")[-1]
                          for r in ("MATERIAL", "CALCULATOR")}
                locked = comp(observed_serial())
                shell_key("f7")
                shell_page("lock-after-f7", 0)
                locked_after = observed_serial()
                if any(numbers(locked_after, f"WINDOW:{role}:KEYS")[-1] != count
                       for role, count in before.items()):
                    raise ValueError("Locked F7 leaked to an application")
                if any(comp(locked_after).get(field) != locked.get(field)
                       for field in ("FOCUSED", "MODE")):
                    raise ValueError("Locked F7 changed the covered workspace")
                report["locked_f7_gate"] = True
                shell_key("ret"); shell_page("users", 1)
                shell_key("tab"); shell_key("ret"); shell_page("personal-auth", 2)
                shell_key("ret"); shell_key("tab"); shell_key("ret")
                shell_key("tab"); shell_key("ret")
                shell_page("hardware-unavailable", 2)
                raw = observed_serial()
                after = {r: numbers(raw, f"WINDOW:{r}:KEYS")[-1] for r in before}
                if before != after:
                    raise ValueError("Trusted shell leaked authentication input into an app")
                shell_key("esc"); shell_page("lock-again", 0)
                shell_key("ret"); shell_page("users-again", 1)
                shell_key("ret"); shell_page("guest-auth", 2)
                unlock_started = time.monotonic()
                shell_key("ret"); shell_page("desktop", 4)
                report["guest_to_desktop_observed_s"] = time.monotonic() - unlock_started
                shell_key("f3"); shell_page("search", 5)
                for code in ("r", "e", "k"): shell_key(code)
                shell_key("ret"); shell_page("calculator", 4)
                if comp(observed_serial()).get("FOCUSED") != 1:
                    raise ValueError("Search did not activate the correct native app")
                shell_key("compose"); shell_page("session-menu", 8)
                shell_key("tab"); shell_key("tab"); shell_key("ret"); shell_page("settings", 6)
                shell_key("esc"); shell_page("desktop-again", 4)
                shell_key("meta_l", "l"); shell_page("covered", 0)
                shell_key("ret"); shell_page("users-return", 1)
                shell_key("ret"); shell_page("guest-return", 2)
                shell_key("ret"); shell_page("desktop-return", 4)
                shell_key("compose"); shell_page("shutdown-menu", 8)
                for _ in range(3): shell_key("tab")
                control.command("send-key", {"keys": [{"type": "qcode", "data": "ret"}], "hold-time": 1})
                report["blocked_app_keys_before"] = before
                report["blocked_app_keys_after"] = after
            elif recovery_handshake:
                # Exercise the actual busy-RPC cancellation/retire/rebind path
                # before waiting for full app paints. This never certifies
                # pixels, preserved work, persistence or the complete U01 gate.
                before = comp(observe("initial group", lambda raw:
                    31 in numbers(raw, "WINDOW:INITMASK") and
                    comp(raw).get("GENERATION") == 1 and comp(raw).get("COMMITS", 0) > 0))
                control.command("send-key", {"keys": [{"type": "qcode", "data": "f12"}], "hold-time": 1})
                raw = observe("actual fresh-group rebind", lambda raw:
                    1 in numbers(raw, "WINDOW:RECOVERIES") and
                    numbers(raw, "WINDOW:PRESENTATION_RETIRED") == [1] and
                    numbers(raw, "WINDOW:RESTART_GENERATION") == [2] and
                    comp(raw).get("GENERATION") == 2 and
                    comp(raw).get("PID") != before["PID"])
                if numbers(raw, "WINDOW:FAULT_SLOT") != [4] or numbers(raw, "WINDOW:FAULT_VECTOR") != [6]:
                    raise ValueError("Wrong actual handshake fault")
                report["handshake"] = {"before": before, "after": comp(raw),
                                       "seconds": time.monotonic() - start,
                                       "scope": "actual group rebind only; no full-frame, work, disk or cleanup acceptance"}
                control.command("quit")
            elif smoke:
                control.command("quit")
            elif switcher:
                def complete(raw, state):
                    """Require synchronized compositor and app generations."""
                    return (all(state.values()) and all(
                        comp(raw).get(role) == state[role][-1]["GEN"]
                        for role in ("MATERIAL", "CALCULATOR")))

                def progress(raw):
                    """Read app key and input acknowledgement counters."""
                    return {role: {field: numbers(raw, f"WINDOW:{role}:{field}")[-1]
                                   for field in ("KEYS", "INPUT_ACKS")}
                            for role in ("MATERIAL", "CALCULATOR")}

                def edge(physical, down):
                    """Inject an ordered physical key edge."""
                    switcher_key_edge(control, move, lambda: comp(serial(directory / "serial.txt")),
                                      physical, down, scale)

                def shell(physical):
                    """Inject the press and release of a shell-owned key."""
                    edge(physical, True)
                    edge(physical, False)

                def focus_cycle():
                    """Cycle focused apps and observe their input cancellations."""
                    raw = serial(directory / "serial.txt")
                    role = "CALCULATOR" if comp(raw)["FOCUSED"] else "MATERIAL"
                    before = progress(raw)[role]
                    key("f6")
                    observe("previous focus cancellation acknowledged", lambda raw:
                            progress(raw)[role]["KEYS"] == before["KEYS"]
                            and progress(raw)[role]["INPUT_ACKS"] == before["INPUT_ACKS"] + 1,
                            timeout_s=90)

                def open_switcher():
                    """Open Alt-Tab and await stable shell input ownership."""
                    raw = serial(directory / "serial.txt")
                    role = "CALCULATOR" if comp(raw)["FOCUSED"] else "MATERIAL"
                    before = progress(raw)[role]
                    edge("alt", True)
                    observe("Alt delivered before shell ownership", lambda raw:
                            all(progress(raw)[role][field] == count + 1 for field, count in before.items()),
                            timeout_s=90)
                    before = progress(serial(directory / "serial.txt"))
                    shell("tab")
                    observe("switcher opening cancellations", lambda raw:
                            all(progress(raw)[role]["KEYS"] == old["KEYS"]
                                and progress(raw)[role]["INPUT_ACKS"] == old["INPUT_ACKS"] + 1
                                for role, old in before.items()), timeout_s=90)
                    return progress(serial(directory / "serial.txt"))

                def same_models(state, baseline):
                    """Reject modifications to either app model during switching."""
                    fields = {"MATERIAL": ("PID", "DRAFT_BYTES", "DRAFT_SUM", "DIRTY", "SAVE_ACKS"),
                              "CALCULATOR": ("PID", "EXPRESSION_BYTES", "EXPRESSION_SUM",
                                             "EVALUATIONS", "FAILURES", "CARET", "CURRENT",
                                             "HAS_ANSWER", "ANSWER_LOW", "ANSWER_HIGH")}
                    return all(state[role][-1][field] == baseline[role][-1][field]
                               for role, names in fields.items() for field in names)

                move(width - 20, 50 * scale)
                wait("switcher-initial", complete)
                key("ret")
                wait("switcher-editor", lambda raw, s: complete(raw, s) and s["MATERIAL"][-1]["SCREEN"] == 2)
                for char in TEXT.decode():
                    key("spc" if char == " " else char)
                focus_cycle()
                for chord in (("2",), ("shift", "equal"), ("3",), ("ret",)):
                    key(*chord)
                focus_cycle()
                baseline = wait("switcher-work", lambda raw, s: complete(raw, s)
                                and comp(raw).get("SHELL_READY") == 1
                                and s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                                and s["MATERIAL"][-1]["DIRTY"] == 1
                                and s["CALCULATOR"][-1]["EVALUATIONS"] == 1
                                and s["CALCULATOR"][-1]["EXPRESSION_SUM"] == volume_disk.fnv(b"2+3")
                                and s["CALCULATOR"][-1]["ANSWER_LOW"] == 5_000_000_000,
                                image_check=consecutive_image_matcher())
                open_switcher()
                shell("esc")
                edge("alt", False)
                wait("switcher-ready", lambda raw, s: complete(raw, s) and same_models(s, baseline),
                     image_check=lambda image: image == captured["switcher-work"])
                fixture = generate_switcher_fixture(directory, captured["switcher-ready"], scale)

                def switcher_wait(name, selected, focused, ledger):
                    """Check model, focus, input counters and full overlay pixels."""
                    return wait(name, lambda raw, s: complete(raw, s)
                                and same_models(s, baseline) and comp(raw).get("FOCUSED") == focused
                                and progress(raw) == ledger,
                                image_check=lambda image: switcher_matches(image, fixture["frames"][selected], scale))

                ledger = open_switcher()
                switcher_wait("switcher-preview", 1, 0, ledger)
                for physical in ("x", "f6", "delete"):
                    shell(physical)
                switcher_wait("switcher-key-isolated", 1, 0, ledger)
                shell("tab")
                switcher_wait("switcher-cycle", 0, 0, ledger)
                shell("left")
                switcher_wait("switcher-reverse", 1, 0, ledger)
                shell("esc")
                edge("alt", False)
                wait("switcher-cancelled", lambda raw, s: same_models(s, baseline) and progress(raw) == ledger,
                     image_check=lambda image: image == captured["switcher-ready"])
                ledger = open_switcher()
                switcher_wait("switcher-commit-preview", 1, 0, ledger)
                edge("alt", False)
                ledger["MATERIAL"]["INPUT_ACKS"] += 1
                wait("switcher-committed", lambda raw, s: complete(raw, s) and same_models(s, baseline)
                     and comp(raw).get("FOCUSED") == 1 and progress(raw) == ledger)
                ledger = open_switcher()
                switcher_wait("switcher-mouse-preview", 0, 1, ledger)
                x, y, _, _ = switcher_bounds
                move(x + 32 * scale, y + 64 * scale)
                button(True)
                move(body[0] + 8 * scale, body[1] + 8 * scale)
                button(False)
                move(width - 20, 50 * scale)
                edge("alt", False)
                ledger["CALCULATOR"]["INPUT_ACKS"] += 1
                wait("switcher-mouse-committed", lambda raw, s: complete(raw, s) and same_models(s, baseline)
                     and comp(raw).get("FOCUSED") == 0 and progress(raw) == ledger,
                     image_check=lambda image: image == captured["switcher-ready"])
                ledger = open_switcher()
                switcher_wait("switcher-outside-preview", 1, 0, ledger)
                move(calculator_body[0] + calculator_body[2] - 4,
                     calculator_body[1] + calculator_body[3] - 4)
                button(True)
                button(False)
                move(width - 20, 50 * scale)
                edge("alt", False)
                wait("switcher-outside-cancelled", lambda raw, s: complete(raw, s)
                     and same_models(s, baseline) and comp(raw).get("FOCUSED") == 0 and progress(raw) == ledger,
                     image_check=lambda image: image == captured["switcher-ready"])
                key("z")
                ledger["MATERIAL"]["KEYS"] += 2
                ledger["MATERIAL"]["INPUT_ACKS"] += 2
                wait("switcher-real-input-restored", lambda raw, s: complete(raw, s) and progress(raw) == ledger
                     and s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(TEXT + b"z")
                     and s["MATERIAL"][-1]["DRAFT_BYTES"] == len(TEXT) + 1
                     and s["CALCULATOR"][-1]["EXPRESSION_SUM"] == volume_disk.fnv(b"2+3"))
                report["switcher_scope"] = "Live app previews, deferred focus, key/mouse isolation, cancel/commit and resumed real input; not the complete window-session/recovery/storage gate."
                key("ctrl", "s")
                wait("switcher-saved-for-cleanup", lambda raw, s: complete(raw, s)
                     and s["MATERIAL"][-1]["DIRTY"] == 0
                     and s["MATERIAL"][-1]["SAVE_ACKS"] == baseline["MATERIAL"][-1]["SAVE_ACKS"] + 1
                     and s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(TEXT + b"z"))
                key("f10")
            elif calculator_recall:
                move(1260, 50)
                key("f6")
                wait("recall-focused", lambda raw, s: s["CALCULATOR"] and
                     s["MATERIAL"] and s["MATERIAL"][-1]["GEN"] > initial["MATERIAL"][-1]["GEN"] and
                     comp(raw).get("FOCUSED") == 1 and
                     comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"] and
                     comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                baseline = snapshots(serial(directory / "serial.txt"), "CALCULATOR")[-1]

                def recall_wait(name, expression, current, evaluations, answer, same_as=None):
                    state = wait(name, lambda raw, s: s["CALCULATOR"] and
                                 calculator_recall_matches(s["CALCULATOR"][-1], baseline,
                                                           expression, current, evaluations, answer) and
                                 comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                    if name != "recall-first" and changed_outside(captured["recall-first"], captured[name], CALCULATOR_BODY):
                        raise ValueError("Recall paint escaped the calculator body")
                    if same_as is not None and crop(captured[name], CALCULATOR_BODY) != crop(captured[same_as], CALCULATOR_BODY):
                        raise ValueError("Complete recall/draft app pixels differ on roundtrip")
                    return state

                for chord in (("2",), ("shift", "equal"), ("3",), ("ret",)):
                    key(*chord)
                recall_wait("recall-first", b"2+3", True, 1, 5_000_000_000)
                for chord in (("esc",), ("4",), ("shift", "8"), ("5",), ("ret",)):
                    key(*chord)
                recall_wait("recall-second", b"4*5", True, 2, 20_000_000_000)
                for chord in (("esc",), ("9",), ("slash",), ("2",)):
                    key(*chord)
                recall_wait("recall-draft", b"9/2", False, 2, 20_000_000_000)
                for name, chord, expression, same_as in (
                    ("recall-latest", ("up",), b"4*5", None),
                    ("recall-oldest", ("up",), b"2+3", None),
                    ("recall-next", ("down",), b"4*5", "recall-latest"),
                    ("recall-own-draft", ("down",), b"9/2", "recall-draft"),
                ):
                    key(*chord)
                    recall_wait(name, expression, False, 2, 20_000_000_000, same_as)
                    if crop(captured[name], CALCULATOR_BODY) == crop(captured["recall-second"], CALCULATOR_BODY):
                        raise ValueError("Recall did not repaint formula/stale result")
                key("up")
                recall_wait("recall-edit-source", b"4*5", False, 2, 20_000_000_000, "recall-latest")
                key("backspace"); key("6")
                recall_wait("recall-edited", b"4*6", False, 2, 20_000_000_000)
                key("up")
                recall_wait("recall-after-edit", b"4*5", False, 2, 20_000_000_000, "recall-latest")
                key("down")
                recall_wait("recall-edited-draft", b"4*6", False, 2, 20_000_000_000, "recall-edited")
                key("ret")
                recall_wait("recall-explicit-evaluation", b"4*6", True, 3, 24_000_000_000)
                key("f10")
            elif calculator_undo:
                move(1260, 50)
                key("f6")
                # Like the recall gate: wait for Material's late focus-lost frame,
                # or later changed_outside checks may see that repaint.
                wait("undo-focused", lambda raw, s: s["CALCULATOR"] and
                     s["MATERIAL"] and s["MATERIAL"][-1]["GEN"] > initial["MATERIAL"][-1]["GEN"] and
                     comp(raw).get("FOCUSED") == 1 and
                     comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"] and
                     comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                for chord in (("2",), ("shift", "equal"), ("3",), ("ret",)):
                    key(*chord)
                calculated = wait("undo-calculated", lambda raw, s: s["CALCULATOR"] and
                                  s["CALCULATOR"][-1]["CURRENT"] == 1 and
                                  s["CALCULATOR"][-1]["EVALUATIONS"] == 1 and
                                  comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                baseline = calculated["CALCULATOR"][-1]
                if not calculator_undo_matches(baseline, baseline, b"2+3", True, 1):
                    raise ValueError("Calculator baseline differs from actual typed 2+3")
                for name, chord, expression, same_as in (
                    ("undo-deleted", ("backspace",), b"2+", None),
                    ("undo-restored", ("ctrl", "z"), b"2+3", None),
                    ("undo-redone", ("ctrl", "y"), b"2+", "undo-deleted"),
                    ("undo-restored-again", ("ctrl", "z"), b"2+3", "undo-restored"),
                    ("undo-shift-redone", ("ctrl", "shift", "z"), b"2+", "undo-deleted"),
                    ("undo-final-restored", ("ctrl", "z"), b"2+3", "undo-restored"),
                ):
                    key(*chord)
                    wait(name, lambda raw, s: s["CALCULATOR"] and
                         calculator_undo_matches(s["CALCULATOR"][-1], baseline, expression, False, 1) and
                         comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                    image = captured[name]
                    if changed_outside(captured["undo-calculated"], image, CALCULATOR_BODY):
                        raise ValueError("Undo paint escaped the calculator body")
                    if crop(image, CALCULATOR_BODY) == crop(captured["undo-calculated"], CALCULATOR_BODY):
                        raise ValueError("Undo did not repaint formula/stale result")
                    if same_as is not None and crop(image, CALCULATOR_BODY) != crop(captured[same_as], CALCULATOR_BODY):
                        raise ValueError("Complete undo/redo app pixels differ on roundtrip")
                key("ret")
                wait("undo-explicit-evaluation", lambda raw, s: s["CALCULATOR"] and
                     calculator_undo_matches(s["CALCULATOR"][-1], baseline, b"2+3", True, 2) and
                     comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                key("f10")
            elif calculator_result:
                move(1260, 50)
                key("f6")
                wait("result-focused", lambda raw, s: all(s.values()) and
                     s["MATERIAL"][-1]["GEN"] > initial["MATERIAL"][-1]["GEN"] and
                     comp(raw).get("FOCUSED") == 1 and
                     comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"] and
                     comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                baseline = snapshots(serial(directory / "serial.txt"), "CALCULATOR")[-1]

                def result_wait(name, expression, evaluations, answer, after=None):
                    return wait(name, lambda raw, s: s["CALCULATOR"] and
                                calculator_result_matches(s["CALCULATOR"][-1], baseline,
                                                          expression, evaluations, answer) and
                                (after is None or s["CALCULATOR"][-1]["GEN"] > after) and
                                comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])

                for chord in (("7",), ("slash",), ("2",), ("ret",)):
                    key(*chord)
                calculated = result_wait("result-calculated", b"7/2", 1, 3_500_000_000)
                key("ctrl", "r")
                selected = result_wait("result-key-selected", b"7/2", 1, 3_500_000_000,
                                       calculated["CALCULATOR"][-1]["GEN"])
                if crop(captured["result-key-selected"], CALCULATOR_BODY) == crop(captured["result-calculated"], CALCULATOR_BODY):
                    raise ValueError("Result selection has no native visual feedback")
                key("ctrl", "c")
                result_wait("result-key-copied", b"7/2", 1, 3_500_000_000,
                            selected["CALCULATOR"][-1]["GEN"])
                key("f6"); key("ret")
                wait("result-editor", lambda raw, s: s["MATERIAL"] and
                     s["MATERIAL"][-1]["SCREEN"] == 2 and
                     comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"])
                key("ctrl", "v")
                wait("result-pasted", lambda raw, s: s["MATERIAL"] and
                     s["MATERIAL"][-1]["DRAFT_BYTES"] == 3 and
                     s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(b"3,5") and
                     s["MATERIAL"][-1]["DIRTY"] == 1 and
                     comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"])
                key("f6"); key("ctrl", "a")
                for chord in (("1",), ("slash",), ("3",), ("ret",)):
                    key(*chord)
                rounded = result_wait("result-rounded", b"1/3", 2, 333_333_333)
                move(1100, 230); button(True); button(False); move(1260, 50)
                clicked = result_wait("result-mouse-selected", b"1/3", 2, 333_333_333,
                                      rounded["CALCULATOR"][-1]["GEN"])
                if crop(captured["result-mouse-selected"], CALCULATOR_BODY) == crop(captured["result-rounded"], CALCULATOR_BODY):
                    raise ValueError("Mouse result selection has no native visual feedback")
                key("ctrl", "c")
                result_wait("result-mouse-copied", b"1/3", 2, 333_333_333,
                            clicked["CALCULATOR"][-1]["GEN"])
                key("f6"); key("ctrl", "a"); key("ctrl", "v")
                pasted = wait("result-rounded-pasted", lambda raw, s: s["MATERIAL"] and
                              s["MATERIAL"][-1]["DRAFT_BYTES"] == 11 and
                              s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(b"0,333333333") and
                              s["MATERIAL"][-1]["DIRTY"] == 1 and
                              comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"])
                key("ctrl", "s")
                wait("result-saved-for-cleanup", lambda raw, s: s["MATERIAL"] and
                     s["MATERIAL"][-1]["SAVE_ACKS"] == pasted["MATERIAL"][-1]["SAVE_ACKS"] + 1 and
                     s["MATERIAL"][-1]["DIRTY"] == 0 and
                     s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(b"0,333333333") and
                     # The acknowledged save must carry the transferred bytes too.
                     s["MATERIAL"][-1]["SAVED_BYTES"] == 11 and
                     s["MATERIAL"][-1]["SAVED_SUM"] == volume_disk.fnv(b"0,333333333") and
                     comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"])
                key("f10")
            else:
                move(width - 20, 50 * scale)
                initial = wait("initial", lambda raw, s: all(s.values()), "initial")
                initial_comp = comp(observed_serial())
                if any(initial[r][-1]["PROBES"] != 3 for r in initial):
                    raise ValueError("Missing initial real CPL3 isolation refusals")
                if workspace:
                    before_keys = {r: numbers(serial(directory / "serial.txt"), f"WINDOW:{r}:KEYS")[-1] for r in initial}
                    shell_key("f7")
                    workspace_wait("focus-material")
                    after = serial(directory / "serial.txt")
                    if any(numbers(after, f"WINDOW:{r}:KEYS")[-1] != before_keys[r] for r in initial):
                        raise ValueError("Shell F7 leaked to an application")
                    key("f6")
                    workspace_wait("focus-calculator")
                    shell_key("f7")
                    workspace_wait("work")
                    shell_key("ctrl", "k")
                    for char in "finder":
                        shell_key(char)
                    workspace_wait("search")
                    shell_key("ret")
                    wait("workspace-selected", lambda raw, s: comp(raw).get("FOCUSED") == 0,
                         image_check=lambda image: material_matches(image, fixture["frames"]["initial"], body)
                         and workspace_matches(image, fixture["frames"]["workspace-selected"], "selected", scale))
                # Extra shell tasks deliberately change calculator focus/caret.
                # Start the unmodified whole-exterior app-isolation comparison
                # only after those tasks and their complete chrome repaint.
                paint_baseline = "workspace-selected" if workspace else "initial"
                report["paint_isolation_baseline"] = paint_baseline
                key("ret")
                wait("editor", lambda raw, s: s["MATERIAL"] and s["MATERIAL"][-1]["SCREEN"] == 2, "editor")
                for char in TEXT.decode():
                    key("spc" if char == " " else char)
                dirty = wait("dirty", lambda raw, s: s["MATERIAL"] and s["MATERIAL"][-1]["DIRTY"] == 1 and s["MATERIAL"][-1]["DRAFT_BYTES"] == len(TEXT) and s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM, "dirty")
                # Exact app bounds, without pixel masks: typing may only change
                # Material's assigned body, never the other app or system chrome.
                for phase in ("editor", "dirty"):
                    if changed_outside(captured[paint_baseline], captured[phase], body):
                        raise ValueError("App paint escaped its assigned body")
                key("f4")
                wait("read-tool", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                     and s["MATERIAL"][-1]["DIRTY"] == 1, "read-tool")
                for physical in ("x", "delete", "backspace"):
                    key(physical)
                wait("read-tool-blocked", lambda raw, s: s["MATERIAL"][-1]["DRAFT_BYTES"] == len(TEXT)
                     and s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                     and s["MATERIAL"][-1]["SAVE_ACKS"] == dirty["MATERIAL"][-1]["SAVE_ACKS"], "read-tool-blocked")
                key("f4")
                wait("write-tool-restored", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM,
                     "write-tool-restored")
                for phase in ("read-tool", "read-tool-blocked", "write-tool-restored"):
                    if changed_outside(captured["dirty"], captured[phase], body):
                        raise ValueError("Document tool changed pixels outside its assigned body")
                key("shift", "f10"); key("x")
                wait("document-menu", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM,
                     "document-menu")
                key("down")
                wait("document-menu-next", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM,
                     "document-menu-next")
                key("ret")
                wait("document-menu-read", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM,
                     "document-menu-read")
                for physical in ("x", "delete", "backspace"):
                    key(physical)
                wait("document-menu-blocked", lambda raw, s: s["MATERIAL"][-1]["DRAFT_BYTES"] == len(TEXT)
                     and s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                     and s["MATERIAL"][-1]["SAVE_ACKS"] == dirty["MATERIAL"][-1]["SAVE_ACKS"],
                     "document-menu-blocked")
                key("shift", "f10"); key("esc")
                wait("document-menu-cancelled", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM,
                     "document-menu-cancelled")
                key("f4")
                wait("document-menu-write", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM,
                     "document-menu-write")
                for phase in ("document-menu", "document-menu-next", "document-menu-read",
                              "document-menu-blocked", "document-menu-cancelled", "document-menu-write"):
                    if changed_outside(captured["dirty"], captured[phase], body):
                        raise ValueError("Document menu changed pixels outside its assigned body")
                if clipboard:
                    key("ctrl", "a"); key("ctrl", "c")
                    wait("clipboard-copied", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM, "clipboard-copied")
                    key("f6"); key("ctrl", "v")
                    wait("clipboard-rejected", lambda raw, s: s["CALCULATOR"][-1]["EXPRESSION_BYTES"] == 0 and s["CALCULATOR"][-1]["EVALUATIONS"] == 0, "clipboard-unsupported")
                    key("f6"); key("3"); key("ctrl", "a"); key("ctrl", "c")
                    wait("clipboard-numeric", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(b"3"), "clipboard-numeric")
                    if workspace:
                        before_panel_input = app_input_progress(serial(directory / "serial.txt"))
                        shell_key("alt", "n")
                        observe("notification Resync acknowledgements", lambda raw:
                                notification_resync_matches(before_panel_input, app_input_progress(raw), alt_open=True)
                                and snapshots(raw, "CALCULATOR")[-1]["ACTIVE"] == 0)
                        workspace_wait("notice-copied")
                        panel_raw = serial(directory / "serial.txt")
                        panel_input = app_input_progress(panel_raw)
                        panel_state = {role: {field: snapshots(panel_raw, role)[-1][field]
                                              for field in fields} for role, fields in (
                            ("MATERIAL", ("DRAFT_BYTES", "DRAFT_SUM", "DIRTY", "SAVE_ACKS")),
                            ("CALCULATOR", ("EXPRESSION_BYTES", "EXPRESSION_SUM", "EVALUATIONS",
                                            "FAILURES", "CARET", "ACTIVE")))}
                        move(*notification_overlap_point(scale))
                        button(True); button(False); move(width - 20, 50 * scale)
                        wait("workspace-notice-mouse-isolated", lambda raw, s: comp(raw).get("FOCUSED") == 0
                             and app_input_progress(raw) == panel_input
                             and all(s[role][-1][field] == value for role, fields in panel_state.items()
                                     for field, value in fields.items()),
                             image_check=lambda image: workspace_matches(
                                 image, fixture["frames"]["workspace-notice-copied"], "notice-copied", scale))
                        panel_keys = {role: numbers(serial(directory / "serial.txt"), f"WINDOW:{role}:KEYS")[-1]
                                      for role in ("MATERIAL", "CALCULATOR")}
                        shell_key("x"); shell_key("f6"); shell_key("ctrl", "shift", "delete")
                        shell_key("delete")
                        workspace_wait("notice-dismissed")
                        shell_key("ret")
                        if any(numbers(serial(directory / "serial.txt"), f"WINDOW:{role}:KEYS")[-1] != count
                               for role, count in panel_keys.items()):
                            raise ValueError("Notification panel leaked a key gesture into an app")
                        if app_input_progress(serial(directory / "serial.txt")) != panel_input:
                            raise ValueError("Notification panel forwarded input to an underlying app")
                        move(302 * scale, 2 * scale)
                        button(True); button(False); move(width - 20, 50 * scale)
                        observe("empty notification Resync acknowledgements", lambda raw:
                                notification_resync_matches(panel_input, app_input_progress(raw)))
                        panel_input = app_input_progress(serial(directory / "serial.txt"))
                        workspace_wait("notice-empty-mouse")
                        close_x = width - 72 * scale + 2 * scale
                        move(close_x, 70 * scale)
                        button(True); button(False); move(width - 20, 50 * scale)
                        wait("workspace-notice-closed", lambda raw, s: comp(raw).get("FOCUSED") == 0,
                             image_check=lambda image: notification_closed_matches(
                                 image, fixture["frames"]["workspace-notice-closed"],
                                 captured["clipboard-numeric"], scale))
                    key("f6"); key("ctrl", "v")
                    wait("clipboard-pasted", lambda raw, s: s["CALCULATOR"][-1]["EXPRESSION_BYTES"] == 1 and s["CALCULATOR"][-1]["EXPRESSION_SUM"] == volume_disk.fnv(b"3") and s["CALCULATOR"][-1]["EVALUATIONS"] == 0, "clipboard-pasted")
                    if workspace:
                        expected_input = {role: dict(progress) for role, progress in panel_input.items()}
                        expected_input["MATERIAL"]["INPUT_ACKS"] += 1  # F6 FocusLost.
                        expected_input["CALCULATOR"]["KEYS"] += 4
                        expected_input["CALCULATOR"]["INPUT_ACKS"] += 4  # Ctrl+V edges.
                        observe("post-panel focus cancellation", lambda raw:
                                numbers(raw, "WINDOW:MATERIAL:INPUT_ACKS")[-1]
                                >= expected_input["MATERIAL"]["INPUT_ACKS"])
                        if app_input_progress(serial(directory / "serial.txt")) != expected_input:
                            raise ValueError("Notification panel forwarded unexpected input to an app")
                    key("shift", "equal"); key("4"); key("ctrl", "a"); key("ctrl", "c")
                    wait("clipboard-calculator-copied", lambda raw, s: s["CALCULATOR"][-1]["EXPRESSION_SUM"] == volume_disk.fnv(b"3+4"), "clipboard-calculator-copied")
                    key("ctrl", "a"); key("backspace")
                    key("f6"); key("ctrl", "v")
                    wait("clipboard-back", lambda raw, s: s["MATERIAL"][-1]["DRAFT_BYTES"] == 3 and s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(b"3+4"), "clipboard-back")
                    key("ctrl", "shift", "delete"); key("ctrl", "v")
                    wait("clipboard-empty", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == volume_disk.fnv(b"3+4"), "clipboard-empty")
                    # Populate again before the genuine fault, then restore the
                    # original workload; recovery must clear even this text.
                    key("ctrl", "a"); key("ctrl", "c"); key("ctrl", "a")
                    for char in TEXT.decode():
                        key("spc" if char == " " else char)
                    wait("clipboard-reset", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM, "dirty")
                key("f6")
                for keys in (("2",), ("shift", "equal"), ("3",), ("ret",)):
                    key(*keys)
                calculated = wait("calculated", lambda raw, s: s["CALCULATOR"] and s["CALCULATOR"][-1].get("HAS_ANSWER") == 1 and s["CALCULATOR"][-1].get("ANSWER_LOW") == 5_000_000_000 and s["CALCULATOR"][-1].get("ANSWER_HIGH") == 0)
                calc = calculated["CALCULATOR"][-1]
                if any(calc[field] != value for field,value in {"EXPRESSION_BYTES":3,"EXPRESSION_SUM":volume_disk.fnv(b"2+3"),"EVALUATIONS":1,"CURRENT":1,"CARET":3,"FAILURES":0}.items()):
                    raise ValueError("Actual calculator model differs from typed 2+3")
                grab = (calculator_body[0] + 128 * scale, calculator_body[1] - 22 * scale)
                move(*grab); button(True); move(grab[0] - 160 * scale, grab[1] - 18 * scale); button(False)
                moved_body = (calculator_body[0] - 160 * scale, calculator_body[1] - 18 * scale,
                              calculator_body[2], calculator_body[3])
                wait("moved", lambda raw, s: comp(raw).get("MOVES", 0) > 0,
                     image_check=lambda raw: crop(captured["calculated"], calculator_body) == crop(raw, moved_body))
                if workspace:
                    shell_key("f8")
                    wait("workspace-arranged", lambda raw, s: comp(raw).get("FOCUSED") == 1,
                         image_check=lambda raw: crop(captured["calculated"], calculator_body) == crop(raw, calculator_body))
                key("f6")
                key("f12")
                recovered = wait("recovered", lambda raw, s: 1 in numbers(raw, "WINDOW:RECOVERIES") and all(s.values()) and all(s[r][-1]["SERVICE_GENERATION"] == 2 and s[r][-1]["PROBES"] == 10 for r in s) and comp(raw).get("GENERATION") == 2 and comp(raw).get("MATERIAL") == s["MATERIAL"][-1]["GEN"] and comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"])
                recovered_comp = comp(observed_serial())
                if recovered_comp["PID"] == initial_comp["PID"]:
                    raise ValueError("Recovery reused the compositor process")
                for field in ("PID", "DRAFT_BYTES", "DRAFT_SUM", "DIRTY", "SAVE_ACKS", "OBJECT"):
                    if recovered["MATERIAL"][-1][field] != dirty["MATERIAL"][-1][field]:
                        raise ValueError("Recovery changed actual unsaved work: " + field)
                for field in ("PID", "EXPRESSION_BYTES", "EXPRESSION_SUM", "ANSWER_LOW", "ANSWER_HIGH", "HAS_ANSWER", "EVALUATIONS", "CARET", "CURRENT", "FAILURES"):
                    if recovered["CALCULATOR"][-1][field] != calculated["CALCULATOR"][-1][field]:
                        raise ValueError("Recovery changed actual calculation: " + field)
                for role in recovered:
                    if any(recovered[role][-1][f] <= initial[role][-1][f] for f in ("SURFACE_EPOCH", "INPUT_EPOCH")):
                        raise ValueError("Recovery reused presentation epoch")
                    previous = dirty if role == "MATERIAL" else calculated
                    if recovered[role][-1]["FRAMES"] <= previous[role][-1]["FRAMES"]:
                        raise ValueError("Recovery did not complete a new app frame")
                group_generation[0] = 2
                pointer[:] = [0, 0]
                move(width - 20, 50 * scale)
                wait("rebound-editor", lambda raw, s: s["MATERIAL"][-1]["SERVICE_GENERATION"] == 2, "dirty-rebound")
                select_title(*grab, 1)
                move(width - 20, 50 * scale)
                key("ret")
                wait("calculator-restored", lambda raw, s: s["CALCULATOR"][-1]["EVALUATIONS"] == calculated["CALCULATOR"][-1]["EVALUATIONS"]+1 and s["CALCULATOR"][-1]["ANSWER_LOW"] == 5_000_000_000 and comp(raw).get("CALCULATOR") == s["CALCULATOR"][-1]["GEN"],
                     image_check=lambda raw: crop(captured["calculated"], calculator_body) == crop(raw, calculator_body))
                select_title(body[0] + 272 * scale, body[1] - 24 * scale, 0)
                move(width - 20, 50 * scale)
                key("right")
                wait("restored-editor", lambda raw, s: s["MATERIAL"][-1]["SERVICE_GENERATION"] == 2, "dirty-recovered")
                if clipboard:
                    key("ctrl", "v")
                    wait("clipboard-recovered-empty", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM, "clipboard-recovered-empty")
                key("ctrl", "s")
                wait("saved", lambda raw, s: s["MATERIAL"] and s["MATERIAL"][-1]["SAVE_ACKS"] == 1 and s["MATERIAL"][-1]["DIRTY"] == 0, "saved")
                key("esc")
                wait("list", lambda raw, s: s["MATERIAL"] and s["MATERIAL"][-1]["SCREEN"] == 1, "list")
                key("ctrl", "f"); key("ret")
                wait("reopened", lambda raw, s: s["MATERIAL"] and s["MATERIAL"][-1]["SCREEN"] == 2 and s["MATERIAL"][-1]["DIRTY"] == 0 and s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM, "reopened")
                if workspace:
                    shell_key("alt", "spc")
                    workspace_wait("window-menu")
                    shell_key("down")
                    workspace_wait("window-menu-next")
                    shell_key("esc")
                    # The trusted title affordance hides the window, not its
                    # process, document owner, surface geometry or revision.
                    move(body[0] + body[2] - 22 * scale, body[1] - 21 * scale)
                    button(True); button(False); move(width - 20, 50 * scale)
                    workspace_wait("window-minimized")
                    shell_key("alt", "f9")
                    workspace_wait("window-empty")
                    hidden_keys = {role: numbers(serial(directory / "serial.txt"), f"WINDOW:{role}:KEYS")[-1]
                                   for role in ("MATERIAL", "CALCULATOR")}
                    shell_key("x")
                    after = serial(directory / "serial.txt")
                    if any(numbers(after, f"WINDOW:{role}:KEYS")[-1] != count
                           for role, count in hidden_keys.items()):
                        raise ValueError("A minimized app received keyboard input")
                    # Main/#167 owns the first dock slot for Search; restore
                    # Material through its current second trusted slot.
                    move(240 * scale, height - 40 * scale)
                    button(True); button(False); move(width - 20, 50 * scale)
                    wait("window-restored", lambda raw, s: comp(raw).get("FOCUSED") == 0
                         and s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                         and s["MATERIAL"][-1]["SAVE_ACKS"] == 1
                         and s["MATERIAL"][-1]["DIRTY"] == 0,
                         "reopened-window-restored",
                         image_check=lambda image: workspace_matches(
                             image, fixture["frames"]["workspace-window-restored"], "window-restored", scale))
                    def move_wait(phase):
                        return wait("workspace-" + phase, lambda raw, s:
                                    comp(raw).get("FOCUSED") == 0
                                    and s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                                    and s["MATERIAL"][-1]["SAVE_ACKS"] == 1
                                    and s["MATERIAL"][-1]["DIRTY"] == 0,
                                    image_check=lambda image: window_move_matches(
                                        image, fixture["frames"]["workspace-" + phase],
                                        fixture["frames"]["reopened-window-restored"], phase, scale))
                    before_move = comp(serial(directory / "serial.txt"))["MOVES"]
                    shell_key("alt", "f7")
                    move_wait("move-open")
                    modal_keys = {role: numbers(serial(directory / "serial.txt"), f"WINDOW:{role}:KEYS")[-1]
                                  for role in ("MATERIAL", "CALCULATOR")}
                    shell_key("x"); shell_key("ctrl", "c"); shell_key("f6")
                    shell_key("right"); shell_key("down")
                    move_wait("move-coarse")
                    shell_key("shift", "right"); shell_key("shift", "up")
                    move_wait("move-fine")
                    if any(numbers(serial(directory / "serial.txt"), f"WINDOW:{role}:KEYS")[-1] != count
                           for role, count in modal_keys.items()):
                        raise ValueError("Keyboard window movement leaked input to an app")
                    shell_key("ret")
                    move_wait("move-committed")
                    shell_key("alt", "f7")
                    move_wait("move-cancel-open")
                    shell_key("left")
                    move_wait("move-cancel-step")
                    shell_key("esc")
                    move_wait("move-cancelled")
                    if captured["workspace-move-committed"] != captured["workspace-move-cancelled"]:
                        raise ValueError("Cancelled keyboard move did not restore the entire framebuffer")
                    if comp(serial(directory / "serial.txt"))["MOVES"] != before_move + 5:
                        raise ValueError("Keyboard movement did not use the real bounded window position")
                    shell_key("f8")
                    move_wait("move-arranged")
                    if captured["window-restored"] != captured["workspace-move-arranged"]:
                        raise ValueError("Arranging after keyboard movement changed the original framebuffer")
                    menu_button = (834, 90) if scale == 1 else (1028, 180)
                    move(body[0] + menu_button[0], body[1] + menu_button[1])
                    button(True); button(False); move(width - 20, 50 * scale)
                    wait("document-menu-mouse", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                         and s["MATERIAL"][-1]["SAVE_ACKS"] == 1, "document-menu-mouse")
                    key("ctrl", "alt", "h")
                    wait("document-menu-high-contrast", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                         and s["MATERIAL"][-1]["SAVE_ACKS"] == 1, "document-menu-high-contrast")
                    key("ctrl", "alt", "h")
                    wait("document-menu-contrast-restored", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM,
                         "document-menu-contrast-restored")
                    if captured["document-menu-mouse"] != captured["document-menu-contrast-restored"]:
                        raise ValueError("High contrast roundtrip changed the real menu or document")
                    key("esc")
                    wait("document-menu-mouse-cancelled", lambda raw, s: s["MATERIAL"][-1]["DRAFT_SUM"] == TEXT_SUM
                         and s["MATERIAL"][-1]["DIRTY"] == 0, "document-menu-mouse-cancelled")
                    for phase in ("document-menu-mouse", "document-menu-mouse-cancelled",
                                  "document-menu-high-contrast", "document-menu-contrast-restored"):
                        if changed_outside(captured["window-restored"], captured[phase], body):
                            raise ValueError("Mouse document menu changed pixels outside its assigned body")
                    if clipboard:
                        key("f6")
                        key("ctrl", "alt", "h")
                        wait("calculator-high-contrast", lambda raw, s: s["CALCULATOR"][-1]["ANSWER_LOW"] == 5_000_000_000
                             and s["CALCULATOR"][-1]["EVALUATIONS"] == 2, "calculator-high-contrast")
                        key("ctrl", "alt", "h")
                        wait("calculator-contrast-restored", lambda raw, s: s["CALCULATOR"][-1]["EVALUATIONS"] == 2,
                             "calculator-contrast-restored")
                        if crop(captured["calculated"], calculator_body) != crop(captured["calculator-contrast-restored"], calculator_body):
                            raise ValueError("Calculator contrast roundtrip changed the real calculation")
                        if changed_outside(captured["calculator-high-contrast"],
                                           captured["calculator-contrast-restored"], calculator_body):
                            raise ValueError("Calculator high contrast painted outside its assigned body")
                if workspace:
                    # Trusted lock above Veld: with a Veld overlay open, Super+L
                    # must win, and afterwards no Veld shortcut, app key or
                    # pointer may reach a window, an app or a Veld overlay.
                    before_panel = captured[next(reversed(captured))]
                    panel_title = (width - 444 * scale, 74 * scale, 210 * scale, 24 * scale)
                    panel_close = (width - 64 * scale, 76 * scale, 16 * scale, 16 * scale)
                    overlay_reference = fixture["frames"]["workspace-notice-copied"]
                    shell_key("alt", "n")
                    wait("lock-veld-overlay-open", lambda raw, s: all(s.values()),
                         image_check=lambda image: all(
                             crop(image, region) == crop(overlay_reference, region)
                             for region in (panel_title, panel_close))
                         and any(crop(image, region) != crop(before_panel, region)
                                 for region in (panel_title, panel_close)))
                    shell_key("meta_l", "l")
                    lock_shell = lambda raw: comp(raw).get("SHELL") == 0 and comp(raw).get("SHELL_READY") == 1
                    wait("lock-over-veld", lambda raw, s: lock_shell(raw))
                    locked_raw = observed_serial()
                    locked = comp(locked_raw)
                    locked_input = app_input_progress(locked_raw)

                    # F7 owns a Veld focus transition while uncovered. Prove it
                    # separately under lock so a later shortcut cannot mask it.
                    shell_key("f7")
                    wait("lock-f7-isolated", lambda raw, s: lock_shell(raw),
                         image_check=lambda image: image == captured["lock-over-veld"])
                    f7_raw = observed_serial()
                    f7_state = comp(f7_raw)
                    if (app_input_progress(f7_raw) != locked_input
                            or any(f7_state[field] != locked[field]
                                   for field in ("FOCUSED", "MOVES", "SWITCHES", "SHELL"))):
                        raise ValueError("F7 acted above the trusted shell")

                    # Alt+Space is probed separately below: Space also activates
                    # the trusted shell's own focused control.
                    for chord in (("alt", "n"), ("alt", "f7"), ("alt", "f9"),
                                  ("f8",), ("ctrl", "k"), ("shift", "f10"), ("x",)):
                        shell_key(*chord)
                    for target in ((302 * scale, 2 * scale),
                                   (body[0] + body[2] - 22 * scale, body[1] - 21 * scale),
                                   (calculator_body[0] + calculator_body[2] - 20 * scale,
                                    calculator_body[1] + 20 * scale)):
                        move(*target); button(True); button(False)
                    move(width - 20, 50 * scale)
                    wait("lock-veld-isolated", lambda raw, s: lock_shell(raw),
                         image_check=lambda image: image == captured["lock-over-veld"])
                    after_raw = observed_serial()
                    after = comp(after_raw)
                    if (app_input_progress(after_raw) != locked_input
                            or any(after[field] != locked[field]
                                   for field in ("FOCUSED", "MOVES", "SWITCHES", "SHELL"))):
                        raise ValueError("Workspace shortcut acted above the trusted shell")
                    shell_key("alt", "spc")
                    observe("lock Alt+Space stays with the shell", lambda raw: comp(raw).get("SHELL") == 1)
                    spaced_raw = observed_serial()
                    spaced = comp(spaced_raw)
                    if (app_input_progress(spaced_raw) != locked_input
                            or any(spaced[field] != locked[field]
                                   for field in ("FOCUSED", "MOVES", "SWITCHES"))):
                        raise ValueError("Workspace window menu acted above the trusted shell")
                    shell_key("ret")
                    observe("lock guest auth", lambda raw: comp(raw).get("SHELL") == 2)
                    shell_key("ret")
                    wait("lock-unlocked", lambda raw, s:
                         comp(raw).get("SHELL") == 4 and comp(raw).get("SHELL_READY") == 1)
                    report["trusted_lock_observation"] = {
                        "locked": locked,
                        "after_f7": f7_state,
                        "after_probes": after,
                        "after_alt_space": spaced,
                        "app_input": locked_input,
                    }
                    report["locked_f7_gate"] = True
                key("f10")
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            raw = observed_serial()
            report["raw_qemu_exit"] = process.returncode
            if library:
                if process.returncode != 33 or not raw.endswith(b"WINDOW:CLEANUP:PASS\nWINDOW:CASE:PASS\nM1:PASS\n"):
                    raise ValueError("Library did not shut down with verified cleanup")
                disk_path = private_path(directory / "volume.img", regular=True)
                report["disk_oracle"] = window_library.disk_oracle(disk_path.read_bytes())
                report["volume_sha256"] = sha256(disk_path)
                if parent is not None:
                    current_parent = window_library.cold_parent(library_parent, source=frozen, manifest=manifest)
                    if current_parent != parent or disk_path.read_bytes() != parent["image"]:
                        raise ValueError("Cold reopen changed the image or its parent evidence")
                report["library_gate"] = True
            elif session_route:
                if process.returncode != 33 or not raw.endswith(b"WINDOW:CLEANUP:PASS\nWINDOW:CASE:PASS\nM1:PASS\n"):
                    raise ValueError("Public session route did not shut down with verified cleanup")
                report["session_route_gate"] = True
            elif diagnostic:
                if process.returncode != 0:
                    raise ValueError("Smoke QEMU quit failed")
            else:
                if process.returncode != 33 or not raw.endswith(b"WINDOW:CLEANUP:PASS\nWINDOW:CASE:PASS\nM1:PASS\n"):
                    raise ValueError("Missing actual cleanup/normal exit")
                if switcher:
                    if numbers(raw, "WINDOW:FAULT_SLOT") or numbers(raw, "WINDOW:RESTARTS") != [0]:
                        raise ValueError("Unexpected fault/restart in switcher part gate")
                elif calculator:
                    if numbers(raw, "WINDOW:RESTARTS") not in ([], [0]) or numbers(raw, "WINDOW:FAULT_SLOT"):
                        raise ValueError("Unexpected fault during calculator interaction")
                else:
                    if numbers(raw, "WINDOW:FAULT_SLOT") != [4] or numbers(raw, "WINDOW:FAULT_VECTOR") != [6] or numbers(raw, "WINDOW:RESTARTS") != [1]:
                        raise ValueError("Wrong actual fault/restart")
                    report["disk_oracle"] = disk_oracle(private_path(directory / "volume.img", regular=True).read_bytes())
            current_manifest = validate_build(frozen, feature, scale)
            if source_hash() != frozen or current_manifest != manifest or sha256(qemu) != qemu_hash:
                raise ValueError("Source/build/QEMU changed during run")
            if {name: sha256(private_path(directory / name, regular=True)) for name in immutable} != immutable or {name: sha256(Path(name)) for name in originals} != originals:
                raise ValueError("Immutable inputs changed during run")
            if sha256(implementation) != implementation_hash:
                raise ValueError("QEMU implementation changed")
            for name, image in captured.items():
                if private_path(directory / (name + ".ppm"), regular=True).read_bytes() != image:
                    raise ValueError("Stored frame changed: " + name)
            if fixture is not None:
                for name, digest in fixture["metadata"]["files_sha256"].items():
                    if sha256(private_path(fixture["directory"] / name, regular=True)) != digest:
                        raise ValueError("Host oracle changed")
                report["oracle"] = fixture["metadata"]
            report.update(passed=True, native_gate=not diagnostic and not calculator and not switcher,
                          switcher_gate=switcher, clipboard_gate=clipboard and not diagnostic,
                          workspace_gate=workspace and not diagnostic,
                          document_tools_gate=workspace and not diagnostic,
                          document_menu_gate=workspace and not diagnostic,
                          pointer_leave_gate=workspace and not diagnostic,
                          app_high_contrast_gate=workspace and clipboard and not diagnostic,
                          keyboard_window_move_gate=workspace and not diagnostic,
                          notification_panel_gate=workspace and clipboard and not diagnostic,
                          window_states_gate=workspace and not diagnostic,
                          native_scale200_gate=full_scale200_gate(scale, workspace, diagnostic, switcher),
                          trusted_lock_gate=workspace and not diagnostic,
                          duration_s=time.monotonic() - start, serial_sha256=sha256(directory / "serial.txt"),
                          qmp_trace=control.trace)
            if calculator_recall:
                report["calculator_recall_gate"] = True
            if calculator_undo:
                report["calculator_undo_gate"] = True
            if calculator_result:
                report["calculator_result_gate"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if process is not None and process.poll() is None:
            # A guest FAIL marker can reach the serial file just before QEMU
            # completes its debug exit. Preserve that exit when available.
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                report["harness_terminated_process"] = True
                process.kill(); process.wait(timeout=5)
        if process is not None:
            report["raw_qemu_exit"] = process.returncode
            if cpu_before is not None:
                cpu_after = os.times()
                report["qemu_host_cpu"] = {
                    "user_seconds": cpu_after.children_user - cpu_before.children_user,
                    "system_seconds": cpu_after.children_system - cpu_before.children_system,
                    "scope": "POSIX reaped child CPU during this QEMU invocation; excludes host fixture generation, not guest CPU cycles or scanout latency"}
        report["duration_s"] = time.monotonic() - start
        if control is not None:
            report["qmp_trace"] = control.trace
            control.close()
        serial_path = directory / "serial.txt"
        if serial_path.exists() and serial_path.stat().st_size <= SERIAL_LIMIT:
            report["serial_sha256"] = sha256(private_path(serial_path, regular=True))
        if fixture is not None:
            report["oracle"] = fixture["metadata"]
        publish_json(directory / "result.json", report)
        publish_json(BUILD / "window-session-report.json", report)
    print(json.dumps({k: report.get(k) for k in ("passed", "native_gate", "error", "run_directory", "duration_s")}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--bios-rom", type=Path, required=True)
    parser.add_argument("--vga-rom", type=Path, required=True)
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--recovery-handshake-only", action="store_true")
    parser.add_argument("--clipboard", action="store_true", help="Include genuine bounded clipboard exchange, clear and post-fault empty checks")
    parser.add_argument("--workspace", action="store_true", help="Include actual work/focus, search, window and notification interactions with exact shell regions")
    parser.add_argument("--switcher", action="store_true", help="Separate window-switcher interaction/pixel part gate, not full session acceptance")
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1, help="Native profile: 1=100%%, 2=200%% for workspace or switcher part gates")
    parser.add_argument("--session-route", action="store_true", help="Check the separate public VM compositor session route; no authentication/security-gate claim")
    parser.add_argument("--library", action="store_true", help="Native naming, collections and history; separate from the full compositor/clipboard gate")
    parser.add_argument("--library-cold-parent", type=Path, help="Copy only a validated successful library run's disposable image for cold reopening")
    parser.add_argument("--calculator-recall", action="store_true", help="Only recall/draft restoration, native pixel roundtrips and normal cleanup")
    parser.add_argument("--calculator-undo", action="store_true", help="Only the calculator undo/redo interaction, pixel roundtrips and normal cleanup")
    parser.add_argument("--calculator-result", action="store_true", help="Only explicit current-result selection and clipboard transfer to Material")
    args = parser.parse_args()
    raise SystemExit(0 if run(timeout=args.timeout, bios_rom=args.bios_rom, vga_rom=args.vga_rom,
                            smoke=args.smoke_only, recovery_handshake=args.recovery_handshake_only,
                            clipboard=args.clipboard, workspace=args.workspace,
                            switcher=args.switcher, scale=args.scale,
                            session_route=args.session_route,
                            library=args.library, library_parent=args.library_cold_parent,
                            calculator_recall=args.calculator_recall, calculator_undo=args.calculator_undo,
                            calculator_result=args.calculator_result)["passed"] else 1)
