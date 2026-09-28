import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bridge import dro_bridge


def port(device, description="", manufacturer="", product="", hwid=""):
    return SimpleNamespace(
        device=device,
        description=description,
        manufacturer=manufacturer,
        product=product,
        hwid=hwid,
    )


class PortSelectionTests(unittest.TestCase):
    def test_explicit_port_does_not_enumerate(self):
        self.assertEqual(dro_bridge.find_port("COM7", []), "COM7")

    def test_prefers_named_dro_among_other_serial_ports(self):
        ports = [
            port("COM2", description="Bluetooth link"),
            port("COM7", product="HEIDENHAIN DRO"),
        ]
        self.assertEqual(dro_bridge.find_port("auto", ports), "COM7")

    def test_uses_only_available_port_without_metadata(self):
        self.assertEqual(dro_bridge.find_port("auto", [port("/dev/cu.usbmodem12101")]), "/dev/cu.usbmodem12101")

    def test_requires_explicit_choice_when_multiple_ports_match(self):
        ports = [port("COM7", product="HEIDENHAIN DRO"), port("COM8", product="ACU-RITE DRO")]
        with self.assertRaisesRegex(RuntimeError, "COM7, COM8"):
            dro_bridge.find_port("auto", ports)

    def test_reports_when_no_serial_ports_exist(self):
        with self.assertRaisesRegex(FileNotFoundError, "No serial ports found"):
            dro_bridge.find_port("auto", [])


class SerialConfigurationTests(unittest.TestCase):
    @patch("bridge.dro_bridge.serial.Serial")
    def test_opens_eight_n_one_without_flow_control(self, serial_constructor):
        dro_bridge.open_port("COM7", 115200)
        serial_constructor.assert_called_once_with(
            port="COM7",
            baudrate=115200,
            bytesize=dro_bridge.serial.EIGHTBITS,
            parity=dro_bridge.serial.PARITY_NONE,
            stopbits=dro_bridge.serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )


if __name__ == "__main__":
    unittest.main()
