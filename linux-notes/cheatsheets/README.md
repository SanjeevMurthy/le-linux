# Cheatsheets -- Quick Reference

> Fast lookup for production debugging and interview recall.
> Full notes and deep explanations live in each topic folder.

---

<!-- toc -->
## Table of Contents

- [Cheatsheet Index](#cheatsheet-index)
- [The 60-Second Server Debugging Checklist](#the-60-second-server-debugging-checklist)
- [Most Important Commands (Top 20)](#most-important-commands-top-20)
- [Quick Links by Scenario](#quick-links-by-scenario)
  - ["Server is slow"](#server-is-slow)
  - ["Out of memory"](#out-of-memory)
  - ["Disk full"](#disk-full)
  - ["Network issues"](#network-issues)
  - ["Security incident"](#security-incident)
- [USE Method Quick Reference](#use-method-quick-reference)

<!-- toc stop -->

## Cheatsheet Index

| # | Topic | Link |
|---|-------|------|
| 00 | Fundamentals (Boot, Kernel, Syscalls) | [00-fundamentals.md](00-fundamentals.md) |
| 01 | Process Management | [01-process-management.md](01-process-management.md) |
| 02 | CPU Scheduling | [02-cpu-scheduling.md](02-cpu-scheduling.md) |
| 03 | Memory Management | [03-memory-management.md](03-memory-management.md) |
| 04 | Filesystem and Storage | [04-filesystem-and-storage.md](04-filesystem-and-storage.md) |
| 05 | LVM and Disk Management | [05-lvm.md](05-lvm.md) |
| 06 | Networking (TCP/IP, DNS, Netfilter) | [06-networking.md](06-networking.md) |
| 07 | Kernel Internals (Modules, cgroups, Namespaces) | [07-kernel-internals.md](07-kernel-internals.md) |
| 08 | Performance and Debugging | [08-performance-and-debugging.md](08-performance-and-debugging.md) |
| 09 | Security (SELinux, PAM, Hardening) | [09-security.md](09-security.md) |
| 10 | System Design Scenarios | [10-system-design-scenarios.md](10-system-design-scenarios.md) |
| 11 | Real-World SRE Incidents | [11-sre-incidents.md](11-sre-incidents.md) |

---

## The 60-Second Server Debugging Checklist

Run these 10 commands in order during the first 60 seconds of any investigation. This is the single most important sequence to memorize.

Full context: [Performance and Debugging Cheatsheet](08-performance-and-debugging.md)

```bash
uptime                                  # 1. Load averages: compare to CPU count
dmesg -T | tail -20                     # 2. Kernel errors, OOM kills, hardware faults
vmstat 1 5                              # 3. r=runqueue, si/so=swap, us/sy/wa/st=CPU
mpstat -P ALL 1 3                       # 4. Per-CPU: spot single-thread bottleneck
pidstat 1 3                             # 5. Per-process CPU attribution
iostat -xz 1 3                          # 6. Disk: await, %util, avgqu-sz
free -m                                 # 7. Memory: check "available" not "free"
sar -n DEV 1 3                          # 8. NIC throughput and drops
sar -n TCP,ETCP 1 3                     # 9. TCP: retrans/s, active/s, passive/s
top -bn1 | head -20                     # 10. Snapshot of top CPU/MEM consumers
```

Then check PSI (kernel 4.20+) to confirm which resource is under pressure:

```bash
cat /proc/pressure/cpu                  # CPU contention
cat /proc/pressure/memory               # Memory pressure
cat /proc/pressure/io                   # I/O stall
```

---

## Most Important Commands (Top 20)

Commands every SRE must know cold, organized by resource.

| # | Command | What It Tells You | Cheatsheet |
|---|---------|-------------------|------------|
| 1 | `vmstat 1` | CPU, memory, swap, I/O, context switches -- all in one | [08](08-performance-and-debugging.md) |
| 2 | `free -m` | Available memory (not "free") -- the real capacity metric | [03](03-memory-management.md) |
| 3 | `ps aux --sort=-%mem` | Top memory consumers by RSS | [01](01-process-management.md) |
| 4 | `ss -tanp` | All TCP connections with PIDs and states | [06](06-networking.md) |
| 5 | `iostat -xz 1` | Disk IOPS, latency (await), queue depth, utilization | [08](08-performance-and-debugging.md) |
| 6 | `dmesg -T \| tail` | Kernel errors, OOM kills, hardware faults with timestamps | [00](00-fundamentals.md) |
| 7 | `perf top -g` | Live CPU profiling with call graphs | [08](08-performance-and-debugging.md) |
| 8 | `mpstat -P ALL 1` | Per-CPU utilization -- spot single-core bottlenecks | [02](02-cpu-scheduling.md) |
| 9 | `strace -c -p <PID>` | Syscall summary (development only -- 100x overhead) | [08](08-performance-and-debugging.md) |
| 10 | `lsof -p <PID>` | All open files, sockets, pipes for a process | [04](04-filesystem-and-storage.md) |
| 11 | `cat /proc/<PID>/smaps_rollup` | True memory footprint (RSS, PSS, swap) | [03](03-memory-management.md) |
| 12 | `nstat -sz` | Kernel TCP/IP counters -- retransmits, drops, overflows | [06](06-networking.md) |
| 13 | `slabtop -s c` | Kernel slab cache usage -- find kernel memory leaks | [03](03-memory-management.md) |
| 14 | `pidstat -d 1` | Per-process I/O reads and writes | [08](08-performance-and-debugging.md) |
| 15 | `ethtool -S eth0` | NIC-level hardware errors, drops, ring buffer overflows | [06](06-networking.md) |
| 16 | `cat /proc/pressure/*` | PSI -- which resource (cpu/memory/io) is stalled | [08](08-performance-and-debugging.md) |
| 17 | `lvs -a -o+devices` | LVM logical volume layout with underlying devices | [05](05-lvm.md) |
| 18 | `journalctl -u <service> --since "1h ago"` | Recent systemd service logs | [00](00-fundamentals.md) |
| 19 | `perf record -g -p <PID> sleep 30` | CPU profile for flame graph generation | [08](08-performance-and-debugging.md) |
| 20 | `ausearch -m avc -ts recent` | Recent SELinux denials | [09](09-security.md) |

---

## Quick Links by Scenario

### "Server is slow"

Start here: [Performance Cheatsheet](08-performance-and-debugging.md)

```
1. cat /proc/pressure/*         --> Which resource is stalled?
2. cpu high?   --> mpstat -P ALL  --> pidstat 1    --> perf top -g --> flame graph
3. memory high? --> free -m       --> vmstat si/so --> slabtop / memleak
4. io high?    --> iostat -xz 1   --> iotop -oP   --> biolatency --> check scheduler
5. all low?    --> ss -s          --> nstat retrans --> ethtool -S --> app profiling
```

Key cheatsheets: [02 CPU](02-cpu-scheduling.md) | [03 Memory](03-memory-management.md) | [08 Performance](08-performance-and-debugging.md)

---

### "Out of memory"

Start here: [Memory Management Cheatsheet](03-memory-management.md)

```bash
# Assess the situation
free -m                                         # Check "available" -- is it truly low?
cat /proc/pressure/memory                       # PSI: is there actual memory pressure?
dmesg -T | grep -i "oom\|kill\|memory"          # Recent OOM kills?

# Find the consumer
ps aux --sort=-%mem | head -10                  # Top RSS consumers
cat /proc/<PID>/smaps_rollup                    # True memory footprint (PSS)
cat /proc/<PID>/status | grep -E 'VmRSS|VmSwap' # RSS and swap usage
slabtop -s c                                    # Kernel slab cache (dentry/inode leaks)
cat /proc/meminfo | grep -E 'Slab|SReclaimable' # Reclaimable vs unreclaimable slab

# Container-specific
cat /sys/fs/cgroup/<path>/memory.current        # Current cgroup memory usage
cat /sys/fs/cgroup/<path>/memory.stat           # Breakdown: anon, file, slab, sock
cat /sys/fs/cgroup/<path>/memory.events         # OOM kill count, low/high events
```

Key cheatsheets: [03 Memory](03-memory-management.md) | [07 Kernel (cgroups)](07-kernel-internals.md)

---

### "Disk full"

Start here: [Filesystem Cheatsheet](04-filesystem-and-storage.md)

```bash
# Basic assessment
df -h                                           # Filesystem usage
df -i                                           # Inode usage (can be full with free space)

# Find what is using space
du -sh /* 2>/dev/null | sort -rh | head -10     # Top directories
find /var/log -type f -size +100M               # Large log files

# Deleted files still held open (the classic "df full, du disagrees" problem)
lsof +L1                                        # Files with zero links (deleted but open)
# Truncate instead of delete: > /path/to/huge.log

# LVM: extend the volume
lvs                                             # Check available space in VG
vgs                                             # Free PEs in volume group
lvextend -L +50G -r /dev/vg/lv                  # Extend LV and resize filesystem
```

Key cheatsheets: [04 Filesystem](04-filesystem-and-storage.md) | [05 LVM](05-lvm.md)

---

### "Network issues"

Start here: [Networking Cheatsheet](06-networking.md)

```bash
# Socket state overview
ss -s                                           # Socket summary: established, TIME_WAIT
ss -tanp state close-wait                       # CLOSE_WAIT = application bug
ss -tanp state time-wait | wc -l                # TIME_WAIT count

# Error counters
nstat -sz | grep -E 'Retrans|Drop|Overflow'     # TCP retransmits, listen drops
ethtool -S eth0 | grep -E 'drop|err|miss'       # NIC hardware errors
cat /proc/net/nf_conntrack_count                 # Conntrack entries used
cat /proc/sys/net/nf_conntrack_max               # Conntrack table max

# DNS
dig +trace example.com                          # Full DNS resolution path
cat /etc/resolv.conf                            # Configured nameservers
systemd-resolve --status                        # systemd-resolved state

# Latency and path
mtr -n <destination>                            # Combined traceroute + ping
ss -ti dst <IP>                                 # Per-connection TCP internals (rtt, cwnd)
```

Key cheatsheets: [06 Networking](06-networking.md) | [08 Performance (network section)](08-performance-and-debugging.md)

---

### "Security incident"

Start here: [Security Cheatsheet](09-security.md)

```bash
# Who is on the system right now?
w                                               # Logged-in users and activity
last -20                                        # Recent logins
lastb -20                                       # Failed login attempts
ausearch -m USER_LOGIN --success no -ts today   # Audit trail of failed logins

# What changed?
ausearch -m EXECVE -ts recent                   # Recently executed commands
find / -perm -4000 -type f 2>/dev/null          # SUID binaries (check for new ones)
rpm -Va 2>/dev/null | grep -E '^..5'            # Verify package integrity (RHEL)
debsums -c 2>/dev/null                          # Verify package integrity (Debian)

# SELinux denials
ausearch -m avc -ts recent                      # Recent SELinux denials
sealert -a /var/log/audit/audit.log             # Human-readable SELinux analysis

# Network exposure
ss -tlnp                                        # All listening ports with PIDs
nft list ruleset                                # Current firewall rules (nftables)
iptables -L -n -v                               # Current firewall rules (iptables)

# Container escape indicators
cat /proc/1/cgroup                              # Are we in a container?
ls -la /proc/*/ns/ 2>/dev/null                  # Check namespace isolation
```

Key cheatsheets: [09 Security](09-security.md) | [07 Kernel (namespaces, capabilities)](07-kernel-internals.md)

---

## USE Method Quick Reference

For every resource, check Utilization, Saturation, Errors.

| Resource | Utilization | Saturation | Errors |
|----------|-------------|------------|--------|
| **CPU** | `mpstat -P ALL 1` (%usr+%sys+%st) | `vmstat 1` r > core count | `dmesg`, MCE events |
| **Memory** | `free -m` (available) | `vmstat 1` si/so > 0 | `dmesg \| grep -i kill` |
| **Disk** | `iostat -xz 1` %util | `iostat` avgqu-sz > 1, await | `smartctl -a`, `dmesg` |
| **Network** | `sar -n DEV 1` kB/s | `nstat` drops, retransmits | `ethtool -S` errors |
| **Swap** | `swapon -s` | `vmstat 1` si+so rate | N/A |

Full details: [Performance Cheatsheet](08-performance-and-debugging.md)
