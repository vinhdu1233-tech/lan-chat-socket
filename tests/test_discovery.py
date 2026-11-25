import json
import queue
import socket
import time
import unittest

from discovery import DiscoveryService


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.service = DiscoveryService("local", "Tu", 5001)
        self.packet = dict(type="HELLO", peer_id="bob", name="Bob",
                           tcp_port=5002, status="online")

    def observe(self, now=0, **changes):
        data = json.dumps({**self.packet, **changes}).encode()
        self.service._observe(data, "192.0.2.2", now)

    def test_refresh_then_expire_once(self):
        self.observe()
        self.observe(3)
        self.assertIn("joined", self.service.events.get_nowait())
        self.service._expire(12.99)
        self.assertEqual(self.service.get_peers()[0].last_seen, 3)
        self.service._expire(13)
        self.service._expire(14)
        self.assertEqual(self.service.get_peers(), [])
        self.assertIn("offline", self.service.events.get_nowait())
        self.assertRaises(queue.Empty, self.service.events.get_nowait)

    def test_duplicate_names_status_and_observed_address(self):
        self.observe()
        self.observe(peer_id="other")
        self.observe(5, status="away", host="ignored", tcp_port=5005)
        peers = self.service.get_peers()
        self.assertEqual(len(peers), 2)
        self.assertEqual((peers[0].host, peers[0].tcp_port, peers[0].status),
                         ("192.0.2.2", 5005, "away"))
        self.service.events.get_nowait()
        self.service.events.get_nowait()
        self.assertIn("away", self.service.events.get_nowait())

    def test_ignore_self_or_malformed_input_then_accept_valid(self):
        self.observe(peer_id="local")
        for change in ({"type": "OTHER"}, {"name": "\ud800"}, {"name": 3},
                       {"tcp_port": True}, {"tcp_port": 65536}, {"status": {}},
                       {"peer_id": ""}):
            self.observe(**change)
        for data in (b"\xff", b"[]", b'{"type":"HELLO"}', b"[" * 1100, b"z" * 4097):
            self.service._observe(data, "127.0.0.1", 0)
        self.assertEqual(self.service.get_peers(), [])
        self.assertTrue(self.service.events.empty())
        self.observe()
        self.assertEqual(len(self.service.get_peers()), 1)

    def test_invalid_local_status(self):
        with self.assertRaises(ValueError):
            self.service.set_status("busy")

    def test_incompatible_version_ignored_and_version_1_accepted(self):
        self.observe(version=2)
        self.observe(version="1")
        self.assertEqual(self.service.get_peers(), [])
        self.observe(version=1)
        self.assertEqual(len(self.service.get_peers()), 1)

    def test_real_udp_socket_announce_receive_status_and_stop(self):
        receiver_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(receiver_sock.close)
        receiver_sock.bind(("127.0.0.1", 0))
        receiver_sock.settimeout(3.0)
        receiver_port = receiver_sock.getsockname()[1]

        service = DiscoveryService(
            "alice-udp",
            "Alice",
            5101,
            udp_port=0,
            broadcast="127.0.0.1",
            bind_host="127.0.0.1",
            target_port=receiver_port,
        )
        service.start()
        self.addCleanup(service.stop)

        with self.assertRaises(RuntimeError):
            service.start()

        # Verify initial real UDP announcement arrives with version=1 & status=online.
        raw, _ = receiver_sock.recvfrom(4096)
        pkt = json.loads(raw.decode("utf-8"))
        self.assertEqual(pkt["type"], "HELLO")
        self.assertEqual(pkt["version"], 1)
        self.assertEqual(pkt["peer_id"], "alice-udp")
        self.assertEqual(pkt["tcp_port"], 5101)
        self.assertEqual(pkt["status"], "online")

        # Verify set_status("away") triggers an immediate UDP re-broadcast.
        service.set_status("away")
        deadline = time.monotonic() + 3.0
        saw_away = False
        while time.monotonic() < deadline:
            raw, _ = receiver_sock.recvfrom(4096)
            if json.loads(raw.decode("utf-8")).get("status") == "away":
                saw_away = True
                break
        self.assertTrue(saw_away)

        # Verify _listen receives a real UDP packet from another peer.
        bob_pkt = json.dumps(
            {
                "type": "HELLO",
                "version": 1,
                "peer_id": "bob-udp",
                "name": "Bob",
                "tcp_port": 5102,
                "status": "online",
            }
        ).encode("utf-8")
        receiver_sock.sendto(bob_pkt, ("127.0.0.1", service.udp_port))

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not service.get_peers():
            time.sleep(0.01)
        peers = service.get_peers()
        self.assertEqual(len(peers), 1)
        self.assertEqual(peers[0].peer_id, "bob-udp")
        self.assertEqual(peers[0].host, "127.0.0.1")
        self.assertEqual(peers[0].tcp_port, 5102)

        service.stop()
        self.assertEqual(service.get_peers(), [])
        self.assertIsNone(service._socket)
