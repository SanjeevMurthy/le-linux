# Cheatsheet 06: Networking (TCP/IP, DNS, Netfilter)

> Quick reference for senior SRE/Cloud Engineer interviews and production work.
> Full notes: [Networking](../06-networking/networking.md)

---

## Socket and Connection Analysis (ss)

```bash
ss -tlnp                              # TCP listening sockets with PIDs
ss -tanp                              # All TCP connections (all states)
ss -s                                 # Summary: total, established, TIME_WAIT
ss -ti state established              # Per-connection TCP internals (cwnd, rtt)
ss -tanp state time-wait | wc -l      # Count TIME_WAIT
ss -tanp state close-wait             # Find connection leaks (app bug)
ss -tnp dst 10.0.0.0/8               # Filter by destination network
ss -tnp sport = :443                  # Filter by local port
ss -m                                 # Show socket memory usage
```

## IP, Routing, and Neighbors

```bash
ip -br addr show                      # Brief interface list (name, state, IPs)
ip -s link show eth0                  # Interface stats (bytes, errors, drops)
ip route show                         # Routing table
ip route get 8.8.8.8                  # Route lookup for specific destination
ip neigh show                         # ARP / neighbor cache
ip neigh flush dev eth0               # Clear ARP cache
ip rule show                          # Policy routing rules
ip netns list                         # Network namespaces
ip netns exec <ns> <cmd>              # Run command in namespace
nsenter --net=/proc/<pid>/ns/net bash  # Enter container network namespace
```

## Packet Capture (tcpdump)

```bash
tcpdump -i eth0 -nn -c 100                            # 100 packets, numeric
tcpdump -i any port 53 -nn                             # DNS traffic
tcpdump -i eth0 'tcp[tcpflags] & tcp-syn != 0'        # SYN packets only
tcpdump -i eth0 'tcp[tcpflags] & tcp-rst != 0'        # RST packets (rejects)
tcpdump -i eth0 host 10.0.0.5 -w /tmp/cap.pcap -s0    # Full capture to file
tcpdump -r /tmp/cap.pcap -A                            # Read pcap, show ASCII
```

## DNS Debugging

```bash
dig example.com                       # A record lookup
dig +trace example.com                # Full delegation chain from root
dig @8.8.8.8 example.com A           # Query specific resolver
dig +short example.com AAAA          # IPv6, short output
dig -x 8.8.8.8                       # Reverse DNS (PTR)
getent hosts example.com              # Test full NSS path (what apps see)
resolvectl status                     # systemd-resolved per-link status
resolvectl flush-caches               # Flush resolved cache
cat /etc/resolv.conf                  # Resolver config
cat /etc/nsswitch.conf                # Name service switch order
```

## Netfilter / Firewall

```bash
iptables -L -v -n --line-numbers      # List filter rules with counters
iptables -t nat -L -v -n              # NAT rules
iptables -t raw -L -v -n              # Raw table (conntrack bypass)
nft list ruleset                      # All nftables rules
nft monitor trace                     # Live packet tracing
```

## Connection Tracking (conntrack)

```bash
conntrack -L                          # List all tracked flows
conntrack -C                          # Count entries
conntrack -S                          # Per-CPU stats (watch for drops!)
conntrack -E                          # Real-time events
conntrack -D -s 10.0.0.5             # Delete entries for source IP
cat /proc/sys/net/netfilter/nf_conntrack_count  # Current entries
cat /proc/sys/net/netfilter/nf_conntrack_max    # Maximum
```

## NIC and Hardware (ethtool)

```bash
ethtool eth0                          # Link status, speed, duplex
ethtool -S eth0                       # NIC stats (rx_drops, tx_errors)
ethtool -k eth0                       # Offload features (tso, gro, checksum)
ethtool -g eth0                       # Ring buffer sizes
ethtool -G eth0 rx 4096              # Increase RX ring buffer
ethtool -l eth0                       # Number of RX/TX queues
```

## Network Statistics

```bash
nstat -sz                             # All SNMP/extended stats
nstat -sz | grep -i retrans           # TCP retransmissions
nstat TcpExtListenOverflows           # Listen backlog overflows (critical!)
nstat TcpExtListenDrops               # Connections dropped at listen
cat /proc/net/sockstat                # Socket allocation summary
cat /proc/net/snmp                    # Protocol-level counters
```

## Critical Sysctl Parameters

| Parameter | Default | Production | Purpose |
|---|---|---|---|
| `net.core.somaxconn` | 128 | 65535 | Listen backlog max |
| `net.ipv4.tcp_max_syn_backlog` | 128-1024 | 65535 | SYN queue depth |
| `net.ipv4.tcp_syncookies` | 1 | 1 | SYN flood protection |
| `net.ipv4.tcp_tw_reuse` | 0 | 1 | Reuse TIME_WAIT (outbound) |
| `net.ipv4.ip_local_port_range` | 32768 60999 | 1024 65535 | Ephemeral ports |
| `net.ipv4.tcp_fin_timeout` | 60 | 15-30 | FIN_WAIT_2 timeout |
| `net.ipv4.tcp_mtu_probing` | 0 | 1 | PMTUD black hole detection |
| `net.ipv4.tcp_congestion_control` | cubic | bbr | Congestion algo |
| `net.core.default_qdisc` | pfifo_fast | fq | Qdisc (BBR needs fq) |
| `net.core.rmem_max` | 212992 | 16777216 | Max socket recv buffer |
| `net.core.wmem_max` | 212992 | 16777216 | Max socket send buffer |
| `net.netfilter.nf_conntrack_max` | 65536 | 1048576+ | Conntrack table size |
| `net.netfilter.nf_conntrack_buckets` | varies | max/4 | Conntrack hash buckets |
| `net.ipv4.tcp_fastopen` | 0 | 3 | TCP Fast Open |

## TCP State Quick Reference

| State | Meaning | Action if Accumulating |
|---|---|---|
| `LISTEN` | Server waiting | Expected |
| `SYN_SENT` | Client SYN sent | Check connectivity |
| `SYN_RECV` | Server got SYN | SYN flood if many |
| `ESTABLISHED` | Active connection | Expected |
| `FIN_WAIT_1` | Sent FIN | Peer not responding |
| `FIN_WAIT_2` | FIN ACKed, waiting peer FIN | `tcp_fin_timeout` controls |
| `TIME_WAIT` | 60s cooldown (active closer) | `tcp_tw_reuse=1`, widen port range |
| `CLOSE_WAIT` | Received FIN, app not closed | **Application bug** -- fix code |
| `LAST_ACK` | Sent FIN, waiting ACK | Peer not ACKing |

## Key /proc/net Files

| File | Content |
|---|---|
| `/proc/net/tcp` | TCP sockets (hex: addr, port, state) |
| `/proc/net/udp` | UDP sockets |
| `/proc/net/sockstat` | Socket counts per protocol |
| `/proc/net/snmp` | SNMP MIB counters |
| `/proc/net/netstat` | Extended TCP stats |
| `/proc/net/nf_conntrack` | Conntrack entries |

## Emergency One-Liners

```bash
# Connection count by state
ss -tan | awk '{print $1}' | sort | uniq -c | sort -rn

# Top 10 IPs by connection count
ss -tan | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -rn | head -10

# Conntrack utilization
echo "$(cat /proc/sys/net/netfilter/nf_conntrack_count) / $(cat /proc/sys/net/netfilter/nf_conntrack_max)"

# Processes with most connections
ss -tanp | grep -oP 'pid=\d+' | sort | uniq -c | sort -rn | head

# Listen backlog overflow check
nstat TcpExtListenOverflows TcpExtListenDrops

# Live DNS query trace
tcpdump -i any port 53 -nn -l

# Container network namespace inspection
nsenter --net=/proc/$(docker inspect -f '{{.State.Pid}}' CONTAINER)/ns/net ss -tlnp
```

## Common Misconceptions

| Misconception | Reality |
|---|---|
| `tcp_fin_timeout` controls TIME_WAIT | Controls FIN_WAIT_2 only; TIME_WAIT is 60s hardcoded |
| `tcp_tw_recycle` fixes TIME_WAIT | Removed in 4.12; breaks behind NAT |
| Blocking all ICMP is secure | Breaks PMTUD, causes TCP hangs for large packets |
| `somaxconn` alone sets backlog | `min(app_backlog, somaxconn)` is the effective limit |
| CLOSE_WAIT is a kernel issue | Always an application bug (not calling `close()`) |
