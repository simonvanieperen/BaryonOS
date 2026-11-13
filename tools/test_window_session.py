"""Adversarial host checks for the native runner, never OS execution."""
from pathlib import Path
import re
import unittest
import subprocess
import sys
from unittest.mock import Mock
import run_window_session as window


def block(role="MATERIAL", **values):
    fields={key:0 for key in window.SNAPSHOT_FIELDS[role]}
    fields.update(READY=1, GEN=2, PID=4, SERVICE_GENERATION=1, SURFACE_EPOCH=9, INPUT_EPOCH=8)
    fields.update(values)
    prefix="WINDOW:"+role+":"
    body="".join(prefix+key+f":{value:020}\n" for key,value in fields.items())
    return (prefix+"SNAPSHOT:BEGIN\n"+body+prefix+"SNAPSHOT:END\n").encode()


def image(width,height,color):
    return f"P6\n{width} {height}\n255\n".encode()+bytes(color)*(width*height)


class WindowRunnerTests(unittest.TestCase):
    def test_switcher_key_edge_observes_real_ordered_pointer_barrier_not_unsampled_key_counter(self):
        for scale in (1, 2):
            width = window.switcher_geometry(scale)[0]
            for lost_key in (False, True):
                state = {"INPUT": 10, "POINTER_X": width - 20, "POINTER_Y": 50 * scale}
                control = Mock()
                def command(name, arguments):
                    self.assertEqual(name, "input-send-event")
                    self.assertEqual(arguments["events"][0]["data"]["key"]["data"], "alt")
                    if not lost_key:
                        state["INPUT"] += 1
                control.command.side_effect = command
                moves = []
                def move(x, y):
                    moves.append((x, y))
                    state.update(INPUT=state["INPUT"] + 1, POINTER_X=x, POINTER_Y=y)
                if lost_key:
                    with self.assertRaisesRegex(ValueError, "ordered switcher input barrier"):
                        window.switcher_key_edge(control, move, lambda: dict(state), "alt", True, scale)
                else:
                    window.switcher_key_edge(control, move, lambda: dict(state), "alt", True, scale)
                self.assertEqual(moves, [(width-22, 50*scale), (width-21, 50*scale),
                                         (width-20, 50*scale)])
                control.command.assert_called_once()

    def test_switcher_key_edge_rejects_lost_key_despite_late_prior_input(self):
        state = {"INPUT": 10, "POINTER_X": 1260, "POINTER_Y": 50}
        control = Mock()

        def move(x, y):
            if x == 1258:
                state["INPUT"] += 1  # Delayed increment from the preceding event.
            state.update(INPUT=state["INPUT"] + 1, POINTER_X=x, POINTER_Y=y)

        with self.assertRaisesRegex(ValueError, "ordered switcher input marker"):
            window.switcher_key_edge(control, move, lambda: dict(state), "alt", True, 1)
        control.command.assert_not_called()

    def test_switcher_work_capture_requires_two_identical_full_images(self):
        matches = window.consecutive_image_matcher()
        self.assertFalse(matches(b"partial"))
        self.assertFalse(matches(b"complete"))
        self.assertTrue(matches(b"complete"))
        self.assertFalse(matches(b"changed"))

    def test_switcher_profiles_compare_all_overlay_pixels_without_masks(self):
        for scale in (1, 2):
            width, height, body, calc, bounds = window.switcher_geometry(scale)
            raw = image(width, height, (4, 5, 6))
            expected = image(*bounds[2:], (4, 5, 6))
            self.assertTrue(window.switcher_matches(raw, expected, scale))
            header = len(raw) - width * height * 3
            x, y, w, h = bounds
            for px, py in ((x, y), (x+w-1, y+h-1), (x+w//2, y+h//2),
                           (x+32*scale, y+64*scale)):
                changed = bytearray(raw)
                changed[header+(py*width+px)*3] ^= 1
                self.assertFalse(window.switcher_matches(bytes(changed), expected, scale))
            for rect in (body, calc, bounds):
                window.crop(raw, rect)
            self.assertFalse(window.switcher_matches(raw, image(1, 1, (4, 5, 6)), scale))
        for scale in (-1, 0, 3):
            with self.assertRaises(ValueError):
                window.switcher_geometry(scale)

    def test_switcher_part_gate_cannot_claim_old_session_or_diagnostic_acceptance(self):
        for flags in ({"smoke": True}, {"recovery_handshake": True}, {"clipboard": True}):
            with self.assertRaises(ValueError):
                window.run(timeout=30, bios_rom=None, vga_rom=None, switcher=True, **flags)
        with self.assertRaises(ValueError):
            window.run(timeout=30, bios_rom=None, vga_rom=None, scale=2)
        result = subprocess.run([sys.executable, window.__file__, "--help"],
                                capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--switcher", result.stdout)
        self.assertIn("200%", result.stdout)

    def test_harness_deadline_is_bounded_per_scale(self):
        # Scale 1 keeps the preregistered 1800 s; only scale 2 may use up to 2700 s.
        with self.assertRaisesRegex(ValueError, r"30\.\.1800 seconds at scale 1"):
            window.run(timeout=1801, bios_rom=None, vga_rom=None, clipboard=True, workspace=True)
        with self.assertRaisesRegex(ValueError, r"30\.\.2700 seconds at scale 2"):
            window.run(timeout=2701, bios_rom=None, vga_rom=None, clipboard=True,
                       workspace=True, scale=2)
        with self.assertRaisesRegex(ValueError, r"30\.\.1800 seconds at scale 3"):
            window.run(timeout=2700, bios_rom=None, vga_rom=None, scale=3)
        # 2700 s passes the deadline check at scale 2 and reaches the next guard.
        with self.assertRaisesRegex(ValueError, "require the full native gate"):
            window.run(timeout=2700, bios_rom=None, vga_rom=None, smoke=True,
                       clipboard=True, scale=2)

    def test_scale200_evidence_requires_the_complete_workspace_gate(self):
        self.assertTrue(window.full_scale200_gate(2, True, False, False))
        for arguments in (
            (1, True, False, False),
            (2, False, False, True),
            (2, False, False, False),
            (2, True, True, False),
            (2, True, False, True),
        ):
            self.assertFalse(window.full_scale200_gate(*arguments))

    def test_calculator_recall_is_not_a_combined_diagnostic_or_storage_gate(self):
        for flag in ("smoke", "recovery_handshake", "clipboard"):
            with self.assertRaises(ValueError):
                window.run(timeout=30, bios_rom=None, vga_rom=None,
                           calculator_recall=True, **{flag: True})

    def test_calculator_recall_requires_exact_draft_result_counts_and_original_binding(self):
        baseline = dict(window.snapshots(block("CALCULATOR"), "CALCULATOR")[0])
        state = dict(baseline, EXPRESSION_BYTES=3, EXPRESSION_SUM=window.volume_disk.fnv(b"9/2"),
                     CARET=3, CURRENT=0, EVALUATIONS=2, FAILURES=0, ERRORS=0, HAS_ANSWER=1,
                     ANSWER_LOW=20_000_000_000, ANSWER_HIGH=0, ACTIVE=1)
        self.assertTrue(window.calculator_recall_matches(state, baseline, b"9/2", False, 2, 20_000_000_000))
        for field in state:
            if field not in ("GEN", "FRAMES"):
                damaged = dict(state)
                damaged[field] += 1
                self.assertFalse(window.calculator_recall_matches(damaged, baseline, b"9/2", False, 2, 20_000_000_000), field)

    def test_calculator_undo_is_never_a_combined_diagnostic_or_storage_gate(self):
        for flag in ("smoke", "recovery_handshake", "clipboard"):
            with self.assertRaises(ValueError):
                window.run(timeout=30, bios_rom=None, vga_rom=None,
                           calculator_undo=True, **{flag: True})

    def test_calculator_undo_requires_exact_formula_stale_result_and_original_binding(self):
        baseline = dict(window.snapshots(block("CALCULATOR"), "CALCULATOR")[0])
        state = dict(baseline, EXPRESSION_BYTES=3, EXPRESSION_SUM=window.volume_disk.fnv(b"2+3"),
                     CARET=3, CURRENT=0, EVALUATIONS=1, FAILURES=0, ERRORS=0, HAS_ANSWER=1,
                     ANSWER_LOW=5_000_000_000, ANSWER_HIGH=0, ACTIVE=1)
        self.assertTrue(window.calculator_undo_matches(state, baseline, b"2+3", False, 1))
        for field in state:
            if field not in ("GEN", "FRAMES"):
                damaged = dict(state)
                damaged[field] += 1
                self.assertFalse(window.calculator_undo_matches(damaged, baseline, b"2+3", False, 1), field)

    def test_result_transfer_cannot_be_combined_with_other_gate_modes(self):
        for flag in ("smoke", "recovery_handshake", "clipboard"):
            with self.assertRaises(ValueError):
                window.run(timeout=30, bios_rom=None, vga_rom=None,
                           calculator_result=True, **{flag: True})

    def test_result_transfer_requires_actual_answer_expression_and_original_binding(self):
        baseline = dict(window.snapshots(block("CALCULATOR"), "CALCULATOR")[0])
        state = dict(baseline, EXPRESSION_BYTES=3, EXPRESSION_SUM=window.volume_disk.fnv(b"7/2"),
                     CARET=3, CURRENT=1, EVALUATIONS=1, FAILURES=0, ERRORS=0, HAS_ANSWER=1,
                     ANSWER_LOW=3_500_000_000, ANSWER_HIGH=0, ACTIVE=1)
        self.assertTrue(window.calculator_result_matches(state, baseline, b"7/2", 1, 3_500_000_000))
        for field in state:
            if field not in ("GEN", "FRAMES"):
                damaged = dict(state)
                damaged[field] += 1
                self.assertFalse(window.calculator_result_matches(damaged, baseline, b"7/2", 1, 3_500_000_000), field)

    def test_calculator_interaction_gates_are_mutually_exclusive_and_separate_from_main_gates(self):
        modes = ("calculator_recall", "calculator_undo", "calculator_result")
        for mode in modes:
            for other in modes + ("session_route", "library"):
                if other != mode:
                    with self.assertRaisesRegex(ValueError, "separate"):
                        window.run(timeout=30, bios_rom=None, vga_rom=None, **{mode: True, other: True})

    def test_clipboard_oracle_checks_calculator_body_without_internal_masks(self):
        raw = image(1280, 720, (1, 2, 3))
        expected = image(320, 484, (1, 2, 3))
        self.assertTrue(window.oracle_matches(raw, expected, "clipboard-pasted"))
        for x, y in ((932, 140), (1251, 623), (950, 300)):
            changed = bytearray(raw)
            offset = len(raw) - 1280 * 720 * 3 + (y * 1280 + x) * 3
            changed[offset] ^= 1
            self.assertFalse(window.oracle_matches(bytes(changed), expected, "clipboard-pasted"))

    def test_clipboard_cannot_be_combined_with_diagnostic_only_success(self):
        for flags in ({"smoke": True}, {"recovery_handshake": True}):
            with self.assertRaises(ValueError):
                window.run(timeout=30, bios_rom=None, vga_rom=None, clipboard=True, **flags)

    def test_library_cannot_reuse_an_unvalidated_or_different_mode(self):
        for flags in ({"smoke": True}, {"recovery_handshake": True},
                      {"clipboard": True}, {"session_route": True},
                      {"workspace": True}, {"scale": 2}):
            with self.assertRaises(ValueError):
                window.run(timeout=30, bios_rom=None, vga_rom=None, library=True, **flags)
        with self.assertRaises(ValueError):
            window.run(timeout=30, bios_rom=None, vga_rom=None, library_parent="unvalidated")
        # The public session route is a separate 100% keyboard gate as well.
        for flags in ({"workspace": True}, {"scale": 2}):
            with self.assertRaises(ValueError):
                window.run(timeout=30, bios_rom=None, vga_rom=None, session_route=True, **flags)

    def test_hidpi_and_route_builds_require_their_own_loader(self):
        self.assertEqual(window.HIDPI_FEATURE, "native-window-session-hidpi-probe")
        self.assertEqual(window.ROUTE_FEATURE, "native-session-route")
        import build  # tools/ is already on sys.path for run_window_session
        self.assertLessEqual({window.FEATURE, window.HIDPI_FEATURE, window.ROUTE_FEATURE}, set(build.WINDOW_FEATURES))

    def test_compositor_snapshot_requires_main_shell_counters(self):
        self.assertLessEqual({"SHELL", "SHELL_READY", "INPUT"}, window.SNAPSHOT_FIELDS["COMPOSITOR"])

    def test_kernel_activity_samples_each_compositor_counter_once(self):
        source = (Path(__file__).resolve().parents[1] / "kernel/src/m2/m3/window_session.rs").read_text()
        activity = re.search(r"let activity = \[(.*?)\];", source, re.DOTALL)
        self.assertIsNotNone(activity)
        offsets = [int(value) for value in re.findall(r"word\(s, COMP, (\d+)\)", activity.group(1))]
        expected = {424, 432, 440, 448, 456, 496, 504, 512, 520, 528}
        self.assertEqual(set(offsets), expected)
        self.assertEqual(len(offsets), len(expected))

    def test_exact_snapshot_rejects_missing_duplicate_or_oversized_fields(self):
        raw=block()
        self.assertEqual(window.snapshots(raw,"MATERIAL")[0]["PID"],4)
        for bad in (raw.replace(b"WINDOW:MATERIAL:PID:00000000000000000004\n",b""),
                    raw.replace(b"SNAPSHOT:END",b"PID:00000000000000000004\nWINDOW:MATERIAL:SNAPSHOT:END"),
                    raw.replace(b"00000000000000000004",b"99999999999999999999")):
            with self.assertRaises(ValueError):window.snapshots(bad,"MATERIAL")

    def test_unready_or_injected_snapshot_cannot_pass(self):
        with self.assertRaises(ValueError):window.snapshots(block(READY=0),"MATERIAL")
        with self.assertRaises(ValueError):window.snapshots(block()+b"\xff","MATERIAL")
        with self.assertRaises(ValueError):window.snapshots(block(),"UNKNOWN")

    def test_partial_record_does_not_certify_a_frame(self):
        raw=block()
        self.assertEqual(window.snapshots(raw[:-1],"MATERIAL"),[])
        self.assertEqual(window.snapshots(raw[:raw.index(b"SNAPSHOT:END")],"MATERIAL"),[])

    def test_whole_body_oracle_compares_every_pixel_without_masks(self):
        raw=image(1280,720,(1,2,3))
        expected=image(880,510,(1,2,3))
        self.assertTrue(window.material_matches(raw,expected))
        for x,y in ((28,114),(907,623),(100,200)):
            damaged=bytearray(raw)
            header=len(raw)-1280*720*3
            damaged[header+(y*1280+x)*3]^=1
            self.assertFalse(window.material_matches(bytes(damaged),expected))

    def test_crop_rejects_crossing_framebuffer_or_invalid_geometry(self):
        raw=image(32,8,(0,0,0))
        for rectangle in ((-1,0,1,1),(31,0,2,1),(0,7,1,2),(0,0,0,1)):
            with self.assertRaises(ValueError):window.crop(raw,rectangle)

    def test_surface_boundary_check_includes_system_and_other_app(self):
        raw=image(1280,720,(1,2,3))
        header=len(raw)-1280*720*3
        for x,y,expected in ((28,114,False),(907,623,False),(27,114,True),(908,623,True),(950,300,True),(50,30,True)):
            changed=bytearray(raw);changed[header+(y*1280+x)*3]^=1
            self.assertEqual(window.changed_outside(raw,bytes(changed),window.BODY),expected)

    def test_repeated_numeric_records_keep_order_and_require_canonical_width(self):
        raw=b"WINDOW:RESTARTS:00000000000000000001\nother\nWINDOW:RESTARTS:00000000000000000002\n"
        self.assertEqual(window.numbers(raw,"WINDOW:RESTARTS"),[1,2])
        self.assertEqual(window.numbers(b"WINDOW:RESTARTS:1\n","WINDOW:RESTARTS"),[])

    def test_compositor_requires_complete_current_frame_and_input_observations(self):
        prefix="WINDOW:COMPOSITOR:"
        fields={name:0 for name in window.SNAPSHOT_FIELDS["COMPOSITOR"]}
        fields.update(GENERATION=2,PID=9,MATERIAL=12,CALCULATOR=8,POINTER_X=1260,POINTER_Y=50)
        raw=(prefix+"SNAPSHOT:BEGIN\n"+"".join(prefix+name+f":{value:020}\n" for name,value in fields.items())+prefix+"SNAPSHOT:END\n").encode()
        self.assertEqual(window.snapshots(raw,"COMPOSITOR")[-1]["MATERIAL"],12)
        self.assertEqual(window.snapshots(raw[:-1],"COMPOSITOR"),[])
        for bad in (raw.replace(b"WINDOW:COMPOSITOR:PID:00000000000000000009\n",b""),
                    raw.replace(b"WINDOW:COMPOSITOR:FATAL:00000000000000000000",b"WINDOW:COMPOSITOR:FATAL:00000000000000000001")):
            with self.assertRaises(ValueError):window.snapshots(bad,"COMPOSITOR")


if __name__=="__main__":unittest.main()
