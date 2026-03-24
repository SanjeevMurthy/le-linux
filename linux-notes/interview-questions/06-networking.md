# Interview Questions 06: Networking (TCP/IP, DNS, Netfilter)

> FAANG / Staff+ SRE interview preparation. All answers structured with bullets/numbered lists.
> Full notes: [Networking](../06-networking/networking.md)

---

## Q1: Walk through the complete lifecycle of a TCP connection, including all state transitions. What happens at each stage in the kernel?

1. **CLOSED to SYN_SENT (client):** `connect()` triggers kernel to allocate `struct sock`, select ephemeral port from `ip_local_port_range`, construct SYN with randomized ISN, transmit via `tcp_v4_connect()`
2. **LISTEN to SYN_RCVD (server):** Incoming SYN arrives at `tcp_v4_rcv()`, kernel creates lightweight `request_sock` (mini-socket). Sends SYN+ACK. With SYN cookies, no state stored at all.
3. **SYN_SENT to ESTABLISHED (client):** Client validates SYN+ACK sequence numbers, sends ACK, socket enters ESTABLISHED, added to established hash table
4. **SYN_RCVD to ESTABLISHED (server):** Final ACK received, `request_sock` promoted to full `struct sock`, placed on accept queue. `accept()` returns new fd.
5. **Data transfer (ESTABLISHED):** `sendmsg()` copies to socket send buffer. TCP sends segments governed by Nagle, congestion window (cubic/bbr), sliding window flow control.
6. **Active close (initiator):** `close()` sends FIN (FIN_WAIT_1). Receives ACK (FIN_WAIT_2). Receives peer FIN, sends ACK (TIME_WAIT, 60s).
7. **Passive close (receiver):** Receives FIN, sends ACK (CLOSE_WAIT). App calls `close()`, kernel sends FIN (LAST_ACK). Receives final ACK, connection freed.

---

## Q2: Explain the difference between TIME_WAIT and CLOSE_WAIT. Why is CLOSE_WAIT always an application bug?

**TIME_WAIT:**
- Occurs on the side that initiates close (active closer)
- Duration: 60 seconds (hardcoded as `TCP_TIMEWAIT_LEN` in kernel)
- Purpose: (a) prevent delayed segments from corrupting new connections on same 4-tuple, (b) allow retransmission of final ACK if lost
- Normal and healthy; can be managed with `tcp_tw_reuse=1` and wider port range

**CLOSE_WAIT:**
- Occurs on the side that receives FIN (passive closer)
- Means: peer closed their end, local application has NOT called `close()`
- Has no timeout -- persists indefinitely until application acts
- Always an application bug because:
  1. No kernel tunable can force the application to close the socket
  2. Typically indicates: leaked connection objects, missing `finally`/`defer` close blocks, thread pool exhaustion, exception handler not closing socket
  3. Diagnosis: `ss -tanp state close-wait` to identify owning process, then inspect its connection lifecycle code

---

## Q3: How does Linux handle a SYN flood attack? Explain SYN cookies in detail.

1. **Normal SYN handling:** Each SYN creates a `request_sock` on the SYN queue, consuming memory and a backlog slot
2. **SYN flood problem:** Millions of SYNs from spoofed IPs fill the SYN queue, blocking legitimate connections
3. **SYN cookies mechanism** (`net.ipv4.tcp_syncookies = 1`):
   - Activated when SYN queue is full
   - Kernel encodes connection parameters into the ISN of the SYN+ACK:
     - 5 bits: timestamp (coarse)
     - 3 bits: MSS index (one of 8 values)
     - 24 bits: cryptographic hash of (src_ip, src_port, dst_ip, dst_port, timestamp, secret key)
   - No state stored for half-open connections
   - When client ACK arrives (ACK# = ISN+1), kernel reconstructs parameters, creates full socket
4. **Limitations:**
   - TCP options (window scaling, SACK, timestamps) cannot be reliably encoded, so are degraded
   - Newer kernels improve encoding to preserve more options
5. **Complementary defenses:**
   - Increase `somaxconn` and `tcp_max_syn_backlog` to 65535
   - Deploy edge DDoS protection (cloud provider scrubbing)
   - XDP-based SYN proxy for extreme scale (10M+ pps)

---

## Q4: Describe the complete DNS resolution path on a modern Linux system.

1. **Application calls `getaddrinfo()`** -- glibc's Name Service Switch (NSS) framework
2. **NSS reads `/etc/nsswitch.conf`** -- `hosts:` line determines lookup order (e.g., `files resolve dns`)
3. **`files`:** Checks `/etc/hosts` for static mappings
4. **`resolve`:** Queries `systemd-resolved` (127.0.0.53)
   - Checks local cache (positive + negative)
   - On miss: forwards to configured upstream recursive resolver
5. **`dns` (fallback):** Reads `/etc/resolv.conf`, queries nameservers in listed order
   - Default timeout: 5 seconds per server, 2 attempts
   - Max 3 nameservers honored
6. **Recursive resolver** (e.g., 8.8.8.8) checks its cache
7. **Iterative resolution on cache miss:**
   - Root servers (13 anycast IPs) return TLD NS records
   - TLD server returns domain NS records
   - Authoritative server returns A/AAAA record with TTL
8. **Response cached** at each layer (resolved, recursive), respecting TTL
9. **`getaddrinfo()` returns** linked list of `struct addrinfo` (address selection per RFC 6724)

**Kubernetes-specific issues:**
- `ndots:5` in resolv.conf causes 5 FQDN expansion attempts before bare lookup
- Conntrack race between parallel A/AAAA queries causes 5-second DNS timeouts
- Fix: `options single-request-reopen`, or use NodeLocal DNSCache

---

## Q5: What is conntrack and why does it matter in production? How do you size and tune it?

**What:**
- Netfilter subsystem tracking every network flow's state
- Hash table mapping 5-tuple (proto, src_ip, src_port, dst_ip, dst_port) to state (NEW, ESTABLISHED, RELATED, INVALID)

**Why it matters:**
1. Required for stateful firewall rules (`-m state --state ESTABLISHED,RELATED`)
2. Required for all NAT operations (SNAT, DNAT, MASQUERADE)
3. Overflow silently drops packets -- no application-visible error, only `dmesg` message

**Sizing:**
1. `net.netfilter.nf_conntrack_max` -- max entries (default often 65536)
2. `net.netfilter.nf_conntrack_buckets` -- hash buckets (set to `max / 4`)
3. Each entry ~300 bytes; 1M entries = ~300 MB
4. Rule of thumb: 2x expected peak concurrent flows

**Timeout tuning:**
- `nf_conntrack_tcp_timeout_established`: 432000 (5 days) default; reduce to 3600 for high-churn
- `nf_conntrack_udp_timeout`: 30 (from default 180)
- `nf_conntrack_generic_timeout`: 60

**Bypass for performance:**
- `iptables -t raw -A PREROUTING -j NOTRACK` for stateless flows
- nftables: `ct state untracked`

---

## Q6: What is the difference between iptables and nftables?

**iptables (legacy):**
1. Separate binaries: `iptables`, `ip6tables`, `arptables`, `ebtables`
2. Linear O(n) rule evaluation per chain
3. Atomic load via `iptables-restore`
4. Widely documented, most Kubernetes CNI plugins use it
5. Modern kernels: `iptables` commands translate to nftables via `iptables-nft`

**nftables (modern):**
1. Single `nft` binary for all protocol families
2. In-kernel VM executes bytecode (more efficient)
3. Native sets, maps, concatenated lookups (O(1) matching)
4. Atomic per-table rule replacement
5. Better syntax with variables and named sets

**When to choose:**
- New deployments (kernel 4.x+): prefer nftables
- Kubernetes: most CNIs still emit iptables rules; use `iptables-nft` compatibility
- 10k+ rules: nftables with sets dramatically outperforms linear iptables

---

## Q7: How do network namespaces work? How does container networking use them?

1. **Kernel mechanism:** `clone(CLONE_NEWNET)` or `unshare(CLONE_NEWNET)` creates new `struct net`
2. **Each namespace isolates:**
   - Network interfaces (loopback auto-created)
   - Routing tables, iptables/nftables rules
   - `/proc/net/*`, socket binding space
   - ARP/neighbor tables
3. **veth pairs:** Virtual Ethernet pairs connect namespaces; one end per namespace, full-duplex
4. **Docker bridge networking:**
   - `docker0` bridge in host namespace
   - Each container: veth pair (one end in container ns, other attached to `docker0`)
   - Outbound NAT via iptables MASQUERADE
5. **Kubernetes pod networking:**
   - Each pod gets its own namespace
   - CNI plugins (Calico, Cilium, Flannel) configure namespace
   - Flat model: pod-to-pod communication without NAT

---

## Q8: Explain TCP congestion control. Compare cubic, bbr, and reno.

**Core concept:**
- Sender maintains congestion window (`cwnd`) limiting bytes in flight
- `cwnd` adjusts based on feedback (ACKs, losses, RTT measurements)

**Reno (RFC 5681):**
1. Slow start: cwnd doubles per RTT until `ssthresh`
2. Congestion avoidance: +1 MSS per RTT (additive increase)
3. Loss (3 dup ACKs): cwnd halved (multiplicative decrease), fast retransmit
4. Timeout: cwnd = 1, restart slow start
5. Problem: conservative, single loss drastically cuts throughput

**Cubic (Linux default since 2.6.19):**
1. cwnd follows cubic function of time since last loss
2. Faster recovery: approaches pre-loss cwnd quickly, then cautious probe
3. Better BDP utilization on high-bandwidth high-latency links
4. Still loss-based: relies on packet loss as congestion signal

**BBR (Google, kernel 4.9+):**
1. Model-based: estimates bottleneck bandwidth and minimum RTT
2. Does NOT rely on loss as primary signal
3. Paces packets to match estimated bottleneck rate
4. Much better on lossy links (wireless, intercontinental)
5. Enable: `sysctl net.ipv4.tcp_congestion_control=bbr` + `net.core.default_qdisc=fq`
6. BBRv2 addresses fairness issues with cubic coexistence

---

## Q9: What is Path MTU Discovery and why does it break?

**How PMTUD works:**
1. TCP sets Don't Fragment (DF) bit on all IPv4 packets
2. Router that cannot forward without fragmenting sends ICMP Type 3 Code 4 ("Fragmentation Needed") with correct MTU
3. Sender adjusts MSS accordingly

**Why it breaks (PMTUD black hole):**
1. Firewalls/security groups block ICMP (including Type 3 Code 4)
2. Sender never learns correct MTU
3. TCP handshake works (small packets); data transfer stalls on large payloads

**Diagnosis:**
1. `ping -M do -s <size> target` -- binary search for max working size
2. `tcpdump` on both sides -- large packets sent but never ACKed
3. `nstat TcpExtTCPMTUProbe` -- check kernel probing activity

**Fix:**
1. `sysctl net.ipv4.tcp_mtu_probing=1` -- kernel probes MTU via reduced segment size
2. MSS clamping: `iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu`
3. Allow ICMP Type 3 in all firewalls (never block PMTUD messages)
4. Set correct MTU on overlay/tunnel interfaces (physical MTU - encapsulation overhead)

---

## Q10: How does `ss` differ from `netstat`? What unique information does it provide?

1. **Architecture:** `ss` queries kernel via netlink (direct API). `netstat` parses `/proc/net/tcp` text files.
2. **Performance:** 100k connections: `ss` returns in milliseconds; `netstat` takes seconds.
3. **Extended TCP info (`ss -ti`):**
   - `cwnd`: congestion window size
   - `rtt`/`rttvar`: round-trip time and variance
   - `retrans`: per-connection retransmit count
   - `send`: calculated throughput
   - `mss`: maximum segment size
   - `bytes_sent`/`bytes_received`: byte counters
4. **State filtering:** `ss state established`, `ss state time-wait` -- direct state filtering
5. **Socket memory (`ss -m`):** Shows buffer allocation (rbuf, tbuf, wmem_queued, backlog)
6. **Process info (`ss -p`):** Shows pid and process name, same as `netstat -p`

---

## Q11: What happens when a Linux host receives a packet destined for another host?

1. **Packet arrives at NIC**, processed through NAPI, enters `ip_rcv()`
2. **PREROUTING chain** traversed (DNAT may alter destination)
3. **Routing decision** (`ip_route_input()`): FIB lookup, destination not local
4. **ip_forward check:** `net.ipv4.ip_forward` must be `1`; if `0`, packet silently dropped
5. **FORWARD chain** traversed (firewall rules for transit traffic)
6. **TTL decremented:** If reaches 0, drop + ICMP Time Exceeded back to sender
7. **POSTROUTING chain** traversed (SNAT/MASQUERADE may alter source)
8. **ARP resolution** for next-hop MAC (or use cached neighbor entry)
9. **`dev_queue_xmit()`** -- packet enters TX qdisc, then NIC driver for transmission

---

## Q12: How do you diagnose and fix TcpExtListenOverflows?

**What it means:**
- Accept queue (fully established connections awaiting `accept()`) has overflowed
- New completed connections are being dropped or RST'd

**Diagnosis:**
1. `ss -tlnp` -- compare Recv-Q (current) with Send-Q (limit)
2. `sysctl net.core.somaxconn` -- often 128 by default
3. Check application listen backlog (nginx: `listen 80 backlog=511;`)
4. Effective backlog = `min(application_backlog, somaxconn)`

**Common causes:**
- Application too slow to `accept()` (thread exhaustion, GC pauses)
- `somaxconn` too low for traffic volume
- Thundering herd after failover

**Fix:**
1. `sysctl -w net.core.somaxconn=65535`
2. Increase application backlog to match
3. Profile application: is `accept()` latency high?
4. Monitor `nstat TcpExtListenOverflows` as critical SLI

---

## Q13: Explain ARP's role in packet delivery. What happens with stale entries?

1. **ARP maps IP to MAC** on local broadcast networks via broadcast request/unicast reply
2. **ARP cache** (`ip neigh show`) stores entries with states: REACHABLE, STALE, DELAY, PROBE, FAILED
3. **Stale entry lifecycle:**
   - Marked STALE after `base_reachable_time/2` (~15-45s)
   - On next use: DELAY (unicast ARP probe) then PROBE
   - No response: FAILED (packet dropped, ICMP host unreachable)
4. **Production issues:**
   - VIP failover: other hosts' ARP cache points to old MAC; fix with gratuitous ARP (GARP)
   - Container migration: stale entries for moved pods
   - `ip neigh flush dev eth0` forces re-resolution

---

## Q14: What is TCP Fast Open and when would you use it?

1. **Problem:** Standard TCP needs full RTT (SYN, SYN+ACK, ACK+data) before sending data
2. **TFO mechanism (RFC 7413):**
   - First connection: server issues TFO cookie (encrypted token)
   - Subsequent connections: client sends cookie + data in SYN
   - Server validates cookie, delivers data to app immediately -- saves 1 RTT
3. **Enable:** `sysctl net.ipv4.tcp_fastopen=3` (client+server)
4. **Application support:** `sendto()` with `MSG_FASTOPEN` or `TCP_FASTOPEN` socket option
5. **Use cases:** CDN origin fetches, DNS over TCP, any protocol with predictable first message
6. **Limitations:** Some middleboxes drop SYN+data; TFO has built-in fallback to normal handshake

---

## Q15: How do you troubleshoot intermittent packet loss in a cloud environment?

1. **Quantify:** `ping -c 1000 -i 0.01 target`, `mtr -n -c 100 target`
2. **Local host checks:**
   - `ethtool -S eth0` -- NIC drops, errors, missed interrupts
   - `ip -s link show eth0` -- interface-level drops
   - `nstat -sz | grep -i drop` -- protocol drops
   - `dmesg | grep -i drop` -- kernel messages (conntrack, etc.)
3. **Netfilter:** `iptables -L -v -n` (DROP rules?), `conntrack -S` (per-CPU drops)
4. **Path:** `traceroute -n target`, `tcpdump` on both ends (compare counts)
5. **Cloud-specific:**
   - Security groups / network ACLs
   - Instance bandwidth limits
   - VPC flow logs
6. **MTU:** `ping -M do -s 1472 target` (test for PMTUD issues)
7. **Methodology:** Capture at sender, each hop, receiver -- identify where packets disappear

---

## Q16: What sysctl parameters must every production Linux host tune for networking?

**Connection handling:**
1. `net.core.somaxconn = 65535`
2. `net.ipv4.tcp_max_syn_backlog = 65535`
3. `net.ipv4.tcp_syncookies = 1`

**Port range and reuse:**
4. `net.ipv4.ip_local_port_range = 1024 65535`
5. `net.ipv4.tcp_tw_reuse = 1`

**Buffer sizes:**
6. `net.core.rmem_max = 16777216`
7. `net.core.wmem_max = 16777216`
8. `net.ipv4.tcp_rmem = 4096 131072 16777216`
9. `net.ipv4.tcp_wmem = 4096 16384 16777216`

**Connection tracking:**
10. `net.netfilter.nf_conntrack_max = 1048576`
11. `net.netfilter.nf_conntrack_buckets = 262144`

**Congestion and MTU:**
12. `net.ipv4.tcp_congestion_control = bbr`
13. `net.core.default_qdisc = fq`
14. `net.ipv4.tcp_mtu_probing = 1`

---

## Q17: Describe the Netfilter chain traversal for: (a) locally destined, (b) forwarded, and (c) locally generated packets.

**(a) Locally destined packet (incoming to this host):**
1. PREROUTING (raw, conntrack, mangle, nat-DNAT)
2. Routing decision: destination is local
3. INPUT (mangle, filter, security, nat-SNAT)
4. Delivered to local socket

**(b) Forwarded packet (transit through this host):**
1. PREROUTING (raw, conntrack, mangle, nat-DNAT)
2. Routing decision: destination is remote
3. FORWARD (mangle, filter, security)
4. POSTROUTING (mangle, nat-SNAT/MASQUERADE, conntrack confirm)
5. Transmitted via outgoing interface

**(c) Locally generated packet (outgoing from this host):**
1. OUTPUT (raw, conntrack, mangle, nat-DNAT, filter, security)
2. Routing decision (may re-route after DNAT in OUTPUT)
3. POSTROUTING (mangle, nat-SNAT/MASQUERADE, conntrack confirm)
4. Transmitted via outgoing interface

**Key points:**
- Every packet traverses at least 2 hooks
- Conntrack happens early (after raw, before mangle) so all subsequent rules can match on state
- Table evaluation order within a hook follows priority: raw (-300), mangle (-150), nat (-100/100), filter (0), security (50)

---

## Q18: What causes 5-second DNS timeouts in Kubernetes? How do you fix it?

**Root cause:**
1. glibc sends A and AAAA queries simultaneously from the same UDP source port
2. Both packets enter the kernel's conntrack table
3. Race condition: second packet may see the conntrack entry from the first as ESTABLISHED and get its own entry marked INVALID
4. The INVALID packet is dropped by iptables rules (`-m state --state INVALID -j DROP`)
5. glibc waits 5 seconds (default timeout) before retrying

**Diagnosis:**
- `conntrack -S | grep insert_failed` -- non-zero confirms the race
- `time dig +short service.namespace.svc.cluster.local` -- exactly 5s delay

**Fixes (any one):**
1. `/etc/resolv.conf`: `options single-request-reopen` -- separate source ports for A and AAAA
2. `/etc/resolv.conf`: `options use-vc` -- use TCP for DNS (eliminates conntrack race)
3. Deploy NodeLocal DNSCache DaemonSet -- local cache on every node
4. Use Cilium CNI (eBPF-based, bypasses conntrack for DNS)
5. Upgrade to kernel 5.0+ with `nf_conntrack_skip_filter` patches
