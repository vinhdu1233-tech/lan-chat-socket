import json
import queue
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
