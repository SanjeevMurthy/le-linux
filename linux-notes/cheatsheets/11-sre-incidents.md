# Cheatsheet 11: SRE Incidents & Incident Response

> Quick reference for senior SRE/Cloud Engineer interviews and production work.
> Full notes: [SRE Incidents](../11-real-world-sre-usecases/sre-incidents.md)

---

<!-- toc -->
## Table of Contents

- [Incident Response Phases](#incident-response-phases)
- [Severity Classification](#severity-classification)
- [SLI / SLO / SLA / Error Budget](#sli-slo-sla-error-budget)
- [Incident Triage Commands (First 5 Minutes)](#incident-triage-commands-first-5-minutes)
- [Deep Investigation Commands](#deep-investigation-commands)
- [Emergency Mitigation Commands](#emergency-mitigation-commands)
- [Incident Pattern Recognition](#incident-pattern-recognition)
- [Kubernetes Incident Commands](#kubernetes-incident-commands)
- [Key Metrics](#key-metrics)
- [10 Incident Quick Reference (Cross-Topic)](#10-incident-quick-reference-cross-topic)
- [Anti-Patterns (Quick List)](#anti-patterns-quick-list)

<!-- toc stop -->

## Incident Response Phases

```
DETECT (0-5 min)    -> Acknowledge page, open incident channel, assign IC
TRIAGE (5-15 min)   -> Identify scope, classify severity, run initial diagnostics
MITIGATE (15-60 min)-> Rollback / failover / drain / rate-limit -- STOP USER IMPACT
COMMUNICATE (ongoing)-> Status updates every 30 min: IMPACT | STATUS | NEXT STEPS | ETA
RESOLVE             -> Confirm SLIs within SLO for 15+ min, apply permanent fix
POST-MORTEM (72 hr) -> Blameless timeline, root cause, action items with owners
```

## Severity Classification

```
SEV1: Full outage / data loss risk     -> Page + IC, updates every 15 min
SEV2: Significant degradation          -> Page, updates every 30 min
SEV3: Minor degradation, workaround    -> Ticket, respond within 4 hours
SEV4: Cosmetic / non-impacting         -> Ticket, respond within 1 business day
```

## SLI / SLO / SLA / Error Budget

```
SLI  = Quantitative measure of service behavior (latency, error rate, throughput)
SLO  = Internal target for an SLI (99.9% availability over 30-day window)
SLA  = External contract with consequences (credits, penalties)
Error Budget = 100% - SLO (e.g., 0.1% = 43.8 min/month downtime)

Availability Table:
  99%     = 7.3 hours/month    = Internal tools
  99.9%   = 43.8 min/month     = Business apps
  99.95%  = 21.9 min/month     = External APIs
  99.99%  = 4.38 min/month     = Payment, auth
  99.999% = 26.3 sec/month     = Core infra, DNS
```

## Incident Triage Commands (First 5 Minutes)

```bash
# System overview
uptime                                    # Load average
dmesg -T | tail -50                       # Kernel messages (OOM, hardware)
journalctl -p err --since "30 min ago"    # Recent errors

# CPU
top -bn1 | head -20                       # Top processes snapshot
mpstat -P ALL 1 3                         # Per-CPU utilization
pidstat -u 1 5                            # Per-process CPU

# Memory
free -h                                   # Memory and swap
vmstat 1 5                                # si/so = swap activity
cat /proc/meminfo | grep -E "MemAvail|SwapFree|Committed"

# Disk
iostat -xz 1 3                            # I/O latency (%util, await)
df -h && df -i                             # Space + inode usage

# Network
ss -s                                      # Socket summary
ss -tnp                                    # TCP connections + process
ip -s link                                 # Interface errors/drops
ethtool -S eth0 | grep -i "error\|drop"   # NIC hardware counters
```

## Deep Investigation Commands

```bash
# Process / cgroup analysis
cat /proc/<pid>/status                     # Process state, memory, caps
cat /proc/<pid>/cgroup                     # Cgroup membership
systemd-cgtop                              # Live cgroup resource usage
cat /proc/<pid>/stack                      # Kernel stack (D-state debug)

# Tracing
strace -fp <pid> -e trace=network -T       # Network syscalls + timing
perf top                                   # Live CPU profiling
perf record -g -p <pid> -- sleep 30        # Record CPU profile

# Network deep dive
tcpdump -i eth0 -nn -c 100 port 53        # DNS traffic capture
tcpdump -i eth0 -nn 'tcp[tcpflags] & (tcp-rst) != 0'  # TCP resets
ss -tnp state time-wait | wc -l           # TIME_WAIT count
conntrack -L | wc -l                       # Conntrack table size

# Disk / filesystem
smartctl -a /dev/sda                       # SMART disk health
xfs_repair -n /dev/sdX                     # XFS integrity check (dry-run)
lsof +D /var/log | wc -l                  # Open files in directory
```

## Emergency Mitigation Commands

```bash
# Memory relief
sync; echo 3 > /proc/sys/vm/drop_caches   # Drop page cache
swapoff -a && swapon -a                    # Reset swap (if safe)

# Process control
kill -STOP <pid>                           # Freeze runaway process
renice +19 -p <pid>                        # Deprioritize CPU hog
ionice -c 3 -p <pid>                       # Idle I/O class for disk hog

# Network emergency
iptables -A INPUT -s <ip> -j DROP          # Block bad source
ip route flush cache                       # Flush routing cache

# Disk emergency
truncate -s 0 /var/log/huge.log            # Reclaim space from bloated log
lsof +L1                                   # Find deleted-but-open files consuming space

# Service management
systemctl restart <service>                # Restart failed service
journalctl -u <service> -f                 # Follow service logs
```

## Incident Pattern Recognition

```
High load + Low CPU util  -> I/O wait: iostat -xz, check D-state processes
High load + High CPU util -> CPU-bound: top, pidstat, check for fork bombs
OOMKilled in dmesg        -> Memory: free -h, cgroup limits, check for leaks
ENOSPC errors             -> Disk full: df -h, df -i, find large files
Connection timeouts       -> Network: ss -s, ethtool errors, DNS resolution
Zombie processes          -> Reaping: ps aux | grep Z, check PID 1 init
Clock skew errors         -> NTP: chronyc tracking, check stratum and offset
Permission denied         -> SELinux: ausearch -m avc, ls -Z, restorecon
```

## Kubernetes Incident Commands

```bash
kubectl get events --sort-by='.lastTimestamp' | tail -20  # Recent events
kubectl top pods --sort-by=memory -A | head -20           # Memory hogs
kubectl top nodes                                          # Node resource usage
kubectl describe pod <pod> | tail -30                      # Events section
kubectl logs <pod> --tail=100 --previous                   # Previous crash logs
kubectl get pods -A | grep -vE "Running|Completed"         # Non-healthy pods
```

## Key Metrics

```
MTTD (Mean Time to Detect)      Target: < 5 min
MTTM (Mean Time to Mitigate)    Target: < 15 min
MTTR (Mean Time to Resolve)     Target: < 4 hours
MTBF (Mean Time Between Failures) Target: increasing QoQ
Error Budget Burn Rate           Alert: > 2% consumed in 1 hour
On-Call Page Rate                Target: < 2 pages per 12-hour shift
```

## 10 Incident Quick Reference (Cross-Topic)

| # | Incident | Key Subsystem | First Command |
|---|---|---|---|
| 1 | Cascading OOM (microservices) | Memory + cgroups | `dmesg -T \| grep "Out of memory"` |
| 2 | Kernel livepatch failure | Kernel + process | `cat /sys/kernel/livepatch/*/transition` |
| 3 | DNS TTL stale endpoints | Networking + DNS | `dig +short @local-resolver domain` |
| 4 | Thundering herd on restart | CPU + networking | `top -bn1`, check simultaneous startups |
| 5 | Silent data corruption | Filesystem | `xfs_repair -n /dev/sdX`, checksum audit |
| 6 | Split-brain (net partition) | Networking + design | `etcdctl endpoint health --cluster` |
| 7 | Log explosion -> disk full -> OOM | Filesystem + memory | `df -h`, `du -sh /var/log/*` |
| 8 | Container escape (kernel CVE) | Security + kernel | `ausearch -m EXECVE -ts today` |
| 9 | Clock skew (distributed) | Fundamentals + net | `chronyc tracking`, check stratum |
| 10 | NIC firmware packet loss | Networking + debug | `ethtool -S eth0 \| grep rx_missed` |

## Anti-Patterns (Quick List)

```
Hero culture         -> Enforce rotation, write runbooks
Premature RCA        -> Mitigate first, investigate after
Alert fatigue        -> Every alert must be actionable or deleted
Blameful post-mortem -> Focus on systems, not individuals
Rollback phobia      -> Design every deploy to be rollback-safe
Infinite retry loops -> Exponential backoff + jitter + circuit breaker
Infra-only monitoring-> SLIs must measure user experience
```
