import unittest
from unittest.mock import patch

from printscan_server.services.cups import CommandResult
from printscan_server.services.sane import list_scanners


class ScannerDiscoveryTests(unittest.TestCase):
    @patch("printscan_server.services.sane._run")
    def test_parses_backtick_device_name(self, run):
        run.return_value = CommandResult(
            0,
            "device `xerox_mfp:libusb:001:002' is a SAMSUNG ORION multi-function peripheral\n",
            "",
        )
        result = list_scanners("/usr/bin/scanimage")
        self.assertTrue(result["available"])
        self.assertEqual(len(result["scanners"]), 1)
        self.assertEqual(result["scanners"][0]["name"], "xerox_mfp:libusb:001:002")
        self.assertIn("SAMSUNG ORION", result["scanners"][0]["model"])
        self.assertIsNone(result["note"])

    @patch("printscan_server.services.sane._run")
    def test_no_scanner_returns_actionable_note(self, run):
        run.return_value = CommandResult(0, "", "No scanners were identified.")
        result = list_scanners("/usr/bin/scanimage")
        self.assertFalse(result["available"])
        self.assertEqual(result["scanners"], [])
        self.assertIn("PRINTSCAN_SCANIMAGE_BIN", result["note"])
        self.assertIn("usblp", result["note"])


if __name__ == "__main__":
    unittest.main()
