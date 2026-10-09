import signal
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from urllib.request import urlopen

from werkzeug.serving import make_server
from PiWiFiSetup import PiWiFiSetup as setup


class ShutdownTests(unittest.TestCase):
    def test_save_response_finishes_before_server_returns(self):
        server = make_server('127.0.0.1', 0, setup.app)
        responses = []
        errors = []

        def save():
            try:
                data = urlencode({'ssid': 'Test WiFi', 'wifi_key': 'secret'}).encode()
                with urlopen('http://127.0.0.1:%d/save_credentials' % server.server_port,
                             data=data, timeout=5) as response:
                    responses.append((response.status, response.read()))
            except Exception as error:
                errors.append(error)
                setup.app.shutdown_requested = True

        with patch.object(setup, 'make_server', return_value=server), \
                patch.object(setup, 'create_wpa_supplicant') as write:
            client = threading.Thread(target=save)
            client.start()
            setup.run_setup_server()
            client.join(timeout=6)
            write.assert_called_once_with('Test WiFi', 'secret')
        self.assertFalse(client.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(responses[0][0], 200)
        self.assertIn(b'Test WiFi', responses[0][1])
        self.assertEqual(server.fileno(), -1)

    def test_failed_save_keeps_server_running(self):
        setup.app.shutdown_requested = False
        with patch.object(setup, 'create_wpa_supplicant', side_effect=OSError('write failed')), \
                patch.dict(setup.app.config, TESTING=True):
            with self.assertRaises(OSError):
                setup.app.test_client().post('/save_credentials',
                                            data={'ssid': 'Test', 'wifi_key': 'secret'})
        self.assertFalse(setup.app.shutdown_requested)

    def test_stop_signals_return_and_restore_handlers(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=signum):
                previous = signal.getsignal(signum)
                server = Mock()
                server.handle_request.side_effect = lambda: signal.getsignal(signum)(signum, None)
                context = Mock()
                context.__enter__ = Mock(return_value=server)
                context.__exit__ = Mock(return_value=False)
                with patch.object(setup, 'make_server', return_value=context):
                    setup.run_setup_server()
                self.assertIs(signal.getsignal(signum), previous)
                context.__exit__.assert_called_once()

    def test_main_restores_wlan_on_return_and_server_errors(self):
        for error in (None, RuntimeError('server failed'), KeyboardInterrupt()):
            with self.subTest(error=error):
                hostapd = Mock()
                config_file = Mock()
                dnsmasq = Mock()

                def start_hostapd():
                    setup.app.hostapd = hostapd
                    setup.app.hostapd_conf = config_file

                with patch.object(setup, 'config_file_hash', return_value={'interface': 'wlan0'}), \
                        patch.object(setup, 'start_hostapd', side_effect=start_hostapd), \
                        patch.object(setup.time, 'sleep'), \
                        patch.object(setup, 'Thread'), \
                        patch.object(setup.subprocess, 'Popen', return_value=dnsmasq), \
                        patch.object(setup.subprocess, 'call', return_value=1), \
                        patch.object(setup.subprocess, 'check_call') as command, \
                        patch.object(setup, 'run_setup_server', side_effect=error):
                    if error is None:
                        setup.main()
                    else:
                        with self.assertRaises(type(error)):
                            setup.main()
                    hostapd.terminate.assert_called_once()
                    config_file.close.assert_called_once()
                    dnsmasq.terminate.assert_called_once()
                    command.assert_any_call(['ip', 'address', 'del', '10.0.0.1/24', 'dev', 'wlan0'])
                    command.assert_any_call(['systemctl', 'restart', 'wpa_supplicant.service'])


if __name__ == '__main__':
    unittest.main()
