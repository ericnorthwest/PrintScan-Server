import unittest

from printscan_server.services.sane import (
    SaneError,
    build_scan_arguments,
    list_scanners,
    parse_scanner_options,
)


class ScannerOptionTests(unittest.TestCase):
    def test_parses_modes_source_and_resolution_range(self):
        output = """
  --mode Color|Gray|Lineart [Gray]
  --resolution 75..600dpi (in steps of 75) [300]
  --source Flatbed|ADF [Flatbed]
  --brightness -100..100 (in steps of 1) [0]
"""
        options = parse_scanner_options(output)
        self.assertEqual(options["mode"]["values"], ["Color", "Gray", "Lineart"])
        self.assertEqual(options["mode"]["default"], "Gray")
        self.assertEqual(options["source"]["values"], ["Flatbed", "ADF"])
        self.assertEqual(options["resolution"]["minimum"], 75)
        self.assertEqual(options["resolution"]["maximum"], 600)
        self.assertEqual(options["resolution"]["step"], 75)
        self.assertEqual(options["resolution"]["default"], 300)
        self.assertNotIn("brightness", options)

    def test_parses_fixed_resolution_choices(self):
        options = parse_scanner_options("  --resolution 75|100|150|300|600dpi [300]\n")
        self.assertEqual(options["resolution"]["values"], [75, 100, 150, 300, 600])
        self.assertEqual(options["resolution"]["default"], 300)

    def test_builds_only_validated_scan_arguments(self):
        options = {
            "mode": {"type": "choices", "values": ["Color", "Gray"], "default": "Gray"},
            "resolution": {
                "type": "range", "minimum": 75, "maximum": 600,
                "step": 75, "default": 300,
            },
            "source": {"type": "choices", "values": ["Flatbed"], "default": "Flatbed"},
        }
        args = build_scan_arguments(
            "xerox_mfp:libusb:001:002",
            options,
            {"mode": "Color", "resolution": 600, "source": "Flatbed"},
        )
        self.assertEqual(
            args,
            [
                "--device-name", "xerox_mfp:libusb:001:002",
                "--format=pnm",
                "--mode", "Color",
                "--resolution", "600",
                "--source", "Flatbed",
            ],
        )

    def test_rejects_resolution_outside_backend_range(self):
        options = {
            "resolution": {
                "type": "range", "minimum": 75, "maximum": 600,
                "step": 75, "default": 300,
            }
        }
        with self.assertRaises(SaneError):
            build_scan_arguments("scanner", options, {"resolution": 1200})

    def test_rejects_invented_mode(self):
        options = {"mode": {"type": "choices", "values": ["Gray"], "default": "Gray"}}
        with self.assertRaises(SaneError):
            build_scan_arguments("scanner", options, {"mode": "Color"})


class ScannerDiscoveryTests(unittest.TestCase):
    def test_parses_device_names(self):
        output = (
            "device 'xerox_mfp:libusb:001:002' is a SAMSUNG ORION multi-function peripheral\n"
            "device 'genesys:libusb:003:004' is a USB flatbed scanner\n"
        )
        from unittest.mock import patch
        from types import SimpleNamespace

        with patch("printscan_server.services.sane._run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=output, stderr="")
            result = list_scanners("scanimage")
        self.assertTrue(result["available"])
        self.assertEqual(
            [item["name"] for item in result["scanners"]],
            ["xerox_mfp:libusb:001:002", "genesys:libusb:003:004"],
        )

    def test_no_device_returns_clear_note(self):
        from unittest.mock import patch
        from types import SimpleNamespace

        with patch("printscan_server.services.sane._run") as run:
            run.return_value = SimpleNamespace(
                returncode=0, stdout="", stderr="No scanners were identified."
            )
            result = list_scanners("scanimage")
        self.assertFalse(result["available"])
        self.assertIn("PRINTSCAN_SCANIMAGE_BIN", result["note"])


if __name__ == "__main__":
    unittest.main()
