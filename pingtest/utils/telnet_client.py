import re
import time
import logging
import telnetlib
from socket import timeout as SocketTimeout
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class TelnetClient:
    def __init__(self):
        # Telnet configuration from settings
        self.telnet_config = {
            'user': settings.TELNET_USER,
            'password': settings.TELNET_PASSWORD,
            'timeout': getattr(settings, 'TELNET_TIMEOUT', 30)
        }

    def _telnet_read_until(self, tn, end_marker, timeout=60):
        """Read from Telnet connection until regex marker is found"""
        start_time = time.time()
        output = ""
        pattern = re.compile(end_marker)
        
        while time.time() - start_time < timeout:
            try:
                chunk = tn.read_very_eager().decode('utf-8', errors='ignore')
            except EOFError:
                logger.error("Connection closed by remote host")
                break
                
            output += chunk
            if pattern.search(output):
                return output
            time.sleep(0.5)
        
        # Final read attempt
        try:
            output += tn.read_very_eager().decode('utf-8', errors='ignore')
        except EOFError:
            pass
            
        return output

    def _parse_packet_loss(self, stats_text):
        """Resilient packet loss parsing (same as original)"""
        match = re.search(r'(\d+\.?\d*)%\s*(packet\s+loss|loss rate)', stats_text, re.IGNORECASE)
        if not match:
            raise ValueError(f"Packet loss not found in: {stats_text[:200]}...")
        
        try:
            packet_loss = float(match.group(1))
        except ValueError:
            raise ValueError(f"Invalid packet loss value: {match.group(1)}")

        if packet_loss == 0.0:
            return 'SF'
        elif packet_loss == 100.0:
            return 'FT'
        else:
            return 'FP'

    def _connect_telnet(self, host, port):
        """Establish Telnet connection with retries"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                tn = telnetlib.Telnet(host, port, timeout=self.telnet_config['timeout'])
                return tn
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return None

    def run_test(self, telnet_host, telnet_port, ping_destination, sw_name, repeat=2):
        results = []
        tn = None

        try:
            # Establish direct Telnet connection
            tn = self._connect_telnet(telnet_host, telnet_port)
            if not tn:
                raise ConnectionError("Telnet connection failed after retries")

            # Perform login sequence
            self._execute_telnet_login(tn, telnet_host, telnet_port, sw_name)

            # Execute ping tests
            for _ in range(repeat):
                result = self._execute_ping_test(tn, telnet_host, telnet_port, ping_destination, sw_name)
                results.append(result)

        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            if tn: tn.close()
            return results

        finally:
            if tn:
                tn.close()

        if repeat == 1:
            return results[0] if results else None
        return results

    def _execute_telnet_login(self, tn, telnet_host, telnet_port, sw_name):
        """Direct Telnet login sequence"""
        # Wait for username prompt
        tn.read_until(b"Username:", timeout=30)
        tn.write(f"{self.telnet_config['user']}\n".encode('utf-8'))
        
        # Wait for password prompt
        tn.read_until(b"Password:", timeout=30)
        tn.write(f"{self.telnet_config['password']}\n".encode('utf-8'))
        
        # Wait for device prompt
        self._telnet_read_until(tn, rf"<{sw_name}>", timeout=40)

    def _execute_ping_test(self, tn, telnet_host, telnet_port, ping_destination, sw_name):
        """Execute and monitor a single ping test"""
        result = self._initialize_result(telnet_host, telnet_port, ping_destination, sw_name)
        
        try:
            # Send ping command
            tn.write(f"ping -c 1000 {ping_destination}\n".encode('utf-8'))
            result['start_time'] = timezone.localtime()
            
            # Read output until prompt appears
            output = self._telnet_read_until(tn, rf"<{sw_name}>", timeout=418)
            
            # Extract statistics
            stats_match = re.search(
                rf"(-+ {re.escape(ping_destination)} ping statistics -+.*?)<{sw_name}>",
                output,
                re.DOTALL
            )

            if stats_match:
                self._handle_successful_test(result, stats_match)
            else:
                # Send Ctrl+C to abort hanging ping
                tn.write(b"\003\n")
                time.sleep(2)
                
                output += tn.read_very_eager().decode('utf-8', errors='ignore')
                
                # Retry statistics extraction
                stats_match = re.search(
                    rf"(-+ {re.escape(ping_destination)} ping statistics -+.*?)<{sw_name}>",
                    output,
                    re.DOTALL
                )
                
                if stats_match:
                    self._handle_successful_test(result, stats_match)
                else:
                    result['error'] = "Ping statistics not found after aborting."

        except Exception as e:
            self._handle_test_error(result, e)
            
        finally:
            result['end_time'] = timezone.localtime()

        return result

    def _initialize_result(self, telnet_host, telnet_port, ping_destination, sw_name):
        return {
            'telnet_host': str(telnet_host),
            'telnet_port': int(telnet_port),
            'ping_destination': str(ping_destination),
            'sw_name': str(sw_name),
            'start_time': None,
            'end_time': None,
            'success': 'FT',
            'statistics': '',
            'error': ''
        }

    def _handle_successful_test(self, result, stats_match):
        stats_text = stats_match.group(1).strip()
        result.update({
            'success': self._parse_packet_loss(stats_text),
            'statistics': stats_text
        })

    def _handle_test_error(self, result, error):
        result['error'] = str(error)
        logger.error(f"Test error: {str(error)}")