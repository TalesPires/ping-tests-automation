import paramiko
import re
import time
import logging
from socket import timeout as SocketTimeout
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class SSHClient:
    def __init__(self):
        # Inicialização da conexão SSH com configurações vindas do arquivo .env
        self.ssh_config = {
            'hostname': settings.SSH_HOST,
            'username': settings.SSH_USER,
            'password': settings.SSH_PASSWORD,
            'port': settings.SSH_PORT,
            'timeout': getattr(settings, 'SSH_TIMEOUT', 30)
        }

    def _read_until(self, channel, end_marker, timeout=60):
        """Enhanced read with buffer flushing and pattern matching"""
        start_time = time.time()
        output = ""
        pattern = re.compile(end_marker)
        
        while time.time() - start_time < timeout:
            if channel.recv_ready():
                # Read larger chunks and handle continuation
                chunk = channel.recv(65535).decode('utf-8', errors='ignore')
                output += chunk
                if pattern.search(output):
                    return output
            time.sleep(1)
        
        # Final attempt to read remaining data
        if channel.recv_ready():
            output += channel.recv(65535).decode('utf-8', errors='ignore')
        
        return output

    def _parse_packet_loss(self, stats_text):
        """More resilient packet loss parsing"""
        match = re.search(r'(\d+\.?\d*)%\s*(packet\s+loss|loss rate)', stats_text, re.IGNORECASE)
        if not match:
            raise ValueError(f"Packet loss not found in: {stats_text[:200]}...")
        
        # Extract the first group and convert it to a float for comparison
        try:
            packet_loss = float(match.group(1))
        except ValueError:
            raise ValueError(f"Invalid packet loss value: {match.group(1)}")

        # Return appropriate enum based on packet loss percentage
        if packet_loss == 0.0:
            return 'SF'
        elif packet_loss == 100.0:
            return 'FT'
        else:
            return 'FP'

    def _connect_ssh(self):
        """SSH connection with retries"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(**self.ssh_config)
                return ssh
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return None

    def run_test(self, telnet_host, telnet_port, ping_destination, sw_name, repeat=2):
        results = []
        ssh = None
        channel = None

        try:
            # Connection setup with increased timeouts
            ssh = self._connect_ssh()
            if not ssh:
                raise ConnectionError("SSH connection failed after retries")

            channel = ssh.invoke_shell()
            time.sleep(2)  # Extended shell initialization

            self._execute_telnet_login(channel, telnet_host, telnet_port, sw_name)

            for _ in range(repeat):
                result = self._execute_ping_test(channel, telnet_host, telnet_port, ping_destination, sw_name)
                results.append(result)

        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            if ssh: ssh.close()
            return results

        finally:
            self._cleanup_connections(channel, ssh)

        if repeat == 1:
            return results[0] if results else None  # Return single dict
        return results  # Return list only for repeat > 1

    def _execute_telnet_login(self, channel, telnet_host, telnet_port, sw_name):
        """Modular telnet login with pattern flexibility"""
        login_sequence = [
            (f"telnet {telnet_host} {telnet_port}\n", r"[Uu]sername:", 30),
            (f"{settings.TELNET_USER}\n", r"[Pp]assword:", 30),
            (f"{settings.TELNET_PASSWORD}\n", rf"<{sw_name}>", 40)
        ]

        for command, pattern, timeout in login_sequence:
            channel.send(command)
            self._read_until(channel, pattern, timeout)

    def _execute_ping_test(self, channel, telnet_host, telnet_port, ping_destination, sw_name):
        """Execute and monitor a single ping test"""
        result = self._initialize_result(telnet_host, telnet_port, ping_destination, sw_name)
        
        try:
            channel.send(f"ping -c 1000 {ping_destination}\n")
            result['start_time'] = timezone.localtime()
            output = self._read_until(channel, rf"<{sw_name}>", timeout=418)  
            
            stats_match = re.search(
                rf"(-+ {re.escape(ping_destination)} ping statistics -+.*?)<{sw_name}>",
                output,
                re.DOTALL
            )

            if stats_match:
                self._handle_successful_test(result, stats_match)
            else:
                channel.send("\003\n")
                time.sleep(2)  # Wait for command to take effect
                
                # Read any remaining output after aborting
                error_output = channel.recv(65535).decode("utf-8", errors="ignore")
                
                stats_match = re.search(
                    rf"(-+ {re.escape(ping_destination)} ping statistics -+.*?)<{sw_name}>",
                    error_output,
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


    def _extract_statistics(self, output):
        """Flexible statistics extraction from partial output"""
        stats_section = re.search(
            r'(.*ping statistics.*\n(?:.*\n)*?\d+ packets? transmitted.*)',
            output,
            re.IGNORECASE | re.DOTALL
        )
        return stats_section.group(1).strip() if stats_section else "No statistics found"

    def _handle_test_error(self, result, error):
        result['error'] = str(error)
        logger.error(f"Test error: {str(error)}")

    def _cleanup_connections(self, channel, ssh):
        try:
            if channel:
                channel.send("exit\n")
                time.sleep(0.5)
                if not channel.closed:
                    channel.close()
        except Exception as e:
            logger.debug(f"Channel cleanup warning: {str(e)}")

        try:
            if ssh:
                ssh.close()
        except Exception as e:
            logger.debug(f"SSH cleanup warning: {str(e)}")