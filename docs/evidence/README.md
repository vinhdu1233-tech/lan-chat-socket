# Wireshark evidence — 27 November 2026

Two original screenshots were supplied by the project leader from a real capture on one MacBook. The PNG files are prepared locally; this text records the observed values, not a substitute for uploading the original images.

## W1 — UDP broadcast (Wi-Fi en0)
Display filter: `udp.port == 9999`. Source IPv4: `172.20.10.3`; destination: `255.255.255.255`; both UDP ports: 9999. Frame 5019 contains 133 bytes of application payload (JSON HELLO, version 1, peer ID, name Alice, TCP port 5001, status online). Frames 4616, 4677 and 4810 occur at 144.362, 147.363 and 150.369 seconds, consistent with the periodic 3-second presence broadcasts. The destination is the IPv4 broadcast address, so discovery does not require a central server.

Expected image filename: `01_UDP_Broadcast.png`.

## W2 — TCP three-way handshake (loopback lo0)
Display filter: `frame.number >= 50 && frame.number <= 52`. Both IP addresses are `172.20.10.3` because the two peers ran on the same computer. The initiator uses ephemeral TCP port 58205; the listener is on port 5002.

| Frame | Ports | Flags | Relative Seq / Ack |
|---|---|---|---|
| 50 | 58205 → 5002 | SYN | 0 / 0 |
| 51 | 5002 → 58205 | SYN, ACK | 0 / 1 |
| 52 | 58205 → 5002 | ACK | 1 / 1 |

The first segment requests a TCP connection; the second acknowledges it and synchronizes the listener sequence; the final ACK completes the transport handshake. The application HELLO/HELLO_ACK exchange is separate from these packets.

Expected image filename: `02_TCP_Three_Way_Handshake.png`.

## Scope
Both mandatory packet types were observed. These captures are local-machine evidence, not a completed two-computer LAN test. The optional FILE_OFFER capture is not required by the assignment. Do not upload unfiltered packet captures to a public repository.
