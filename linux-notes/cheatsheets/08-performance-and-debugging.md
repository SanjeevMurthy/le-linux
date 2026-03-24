# Cheatsheet 08: Performance & Debugging (Observability, Profiling, Tracing)

> Quick reference for senior SRE/Cloud Engineer interviews and production work.
> Full notes: [Performance & Debugging](../08-performance-and-debugging/performance-and-debugging.md)

---

## The 60-Second Performance Checklist

```bash
# Run these 10 commands in order during the first 60 seconds of any investigation.

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

---

## PSI (Pressure Stall Information) -- Kernel 4.20+

```bash
cat /proc/pressure/cpu                  # CPU contention (some = partial stall)
cat /proc/pressure/memory               # Memory pressure (some + full)
cat /proc/pressure/io                   # I/O stall (some + full)

# Interpret:
# some avg10=0.00  →  No contention, healthy
# some avg10=5.00  →  5% of time at least one task stalled
# full avg10=3.00  →  3% of time ALL tasks stalled (severe)

# Watch live:
watch -n1 'cat /proc/pressure/cpu; echo ---; cat /proc/pressure/memory; echo ---; cat /proc/pressure/io'
```

---

## USE Method Quick Reference

| Resource | Utilization | Saturation | Errors |
|---|---|---|---|
| **CPU** | `mpstat -P ALL 1` (%usr+%sys+%st) | `vmstat 1` r > core count | `dmesg`, MCE events |
| **Memory** | `free -m` (available) | `vmstat 1` si/so > 0 | `dmesg \| grep -i kill` |
| **Disk** | `iostat -xz 1` %util | `iostat` avgqu-sz > 1, await | `smartctl -a`, `dmesg` |
| **Network** | `sar -n DEV 1` kB/s | `nstat` drops, retransmits | `ethtool -S` errors |
| **Swap** | `swapon -s` | `vmstat 1` si+so rate | N/A |

---

## vmstat Column Reference

```bash
vmstat 1 5                              # Skip first line (boot average)
# procs -----memory---- ---swap-- -----io---- -system-- ------cpu-----
#  r  b   swpd  free  buff  cache   si   so    bi   bo   in   cs us sy id wa st
```

| Column | Meaning | Red Flag |
|---|---|---|
| `r` | Runnable processes | > CPU core count |
| `b` | Blocked (D state) | > 10 |
| `si/so` | Swap in/out (KiB/s) | Any sustained > 0 |
| `wa` | I/O wait % | > 20% |
| `st` | Stolen time % | > 10% (VM throttled) |
| `cs` | Context switches/sec | > 100k (contention) |

---

## iostat Column Reference

```bash
iostat -xz 1                            # Extended stats, skip idle, 1-sec
```

| Column | Meaning | Red Flag |
|---|---|---|
| `r/s, w/s` | IOPS (read/write) | Near device max |
| `await` | Avg I/O latency (ms) | > 10ms SSD, > 20ms HDD |
| `avgqu-sz` | Queue length | > 1 (single device) |
| `%util` | Time busy | Misleading on NVMe! |

---

## CPU Profiling (perf)

```bash
# Count hardware events (zero overhead)
perf stat <command>                     # Cycles, instructions, IPC, cache misses
perf stat -a sleep 10                   # System-wide for 10 seconds
perf stat -e cache-misses,cache-references,instructions,cycles -p <PID> sleep 5

# Sample and profile (low overhead)
perf record -g -p <PID> sleep 30       # Profile specific PID with call graphs
perf record -g -a sleep 30             # System-wide profiling
perf report --stdio                     # Text report from perf.data
perf top -g                             # Live system-wide profiling

# Generate flame graph
perf script | stackcollapse-perf.pl | flamegraph.pl > flame.svg

# Scheduler analysis
perf sched record sleep 10 && perf sched latency  # Scheduler latency

# Tracepoints (alternative to strace)
perf trace -p <PID>                     # Low-overhead syscall tracing
```

---

## strace (Development/Non-Production Only)

```bash
strace -c -p <PID>                      # Syscall summary (lowest overhead mode)
strace -T -p <PID>                      # Time spent per syscall
strace -f -e trace=file <cmd>           # File operations only (follows forks)
strace -f -e trace=network <cmd>        # Network operations only
strace -e trace=openat -p <PID>         # Single syscall type
strace -o /tmp/trace.out -ff <cmd>      # Per-child output files
```

**WARNING:** strace causes 100x+ slowdown via ptrace. Use `perf trace` or eBPF in production.

---

## eBPF / BCC Essential Tools

```bash
# Process tracing
execsnoop                               # All new process exec() calls
opensnoop                               # All file open() calls
opensnoop -p <PID>                      # File opens for specific PID

# Disk I/O
biolatency                              # Block I/O latency histogram
biosnoop                                # Per-event I/O with PID, latency
ext4slower 10                           # ext4 ops slower than 10ms

# Network
tcpretrans                              # TCP retransmissions
tcpconnect                              # Outbound TCP connections
tcpaccept                               # Inbound TCP connections

# CPU/Scheduling
runqlat                                 # Run queue latency histogram
runqlen                                 # Run queue length histogram
profile                                 # CPU stack profiling (for flame graphs)
offcputime                              # Off-CPU blocking analysis
cpudist                                 # On-CPU time distribution

# Memory
memleak -p <PID>                        # Trace memory allocations/frees
oomkill                                 # Trace OOM kill events
shmsnoop                                # Shared memory operations

# General
funccount 'vfs_*'                       # Count kernel function calls
trace 'do_sys_open "%s", arg2'          # Function argument tracing
syscount                                # System call frequency count
```

---

## bpftrace One-Liners

```bash
# Count syscalls by process
bpftrace -e 'tracepoint:raw_syscalls:sys_enter { @[comm] = count(); }'

# New process tracing
bpftrace -e 'tracepoint:syscalls:sys_enter_execve { printf("%d %s %s\n", pid, comm, str(args->filename)); }'

# Block I/O latency histogram
bpftrace -e 'tracepoint:block:block_rq_complete { @us = hist((nsecs - args->io_start_time_ns)/1000); }'

# VFS read latency by process
bpftrace -e 'kprobe:vfs_read { @start[tid] = nsecs; }
  kretprobe:vfs_read /@start[tid]/ { @us[comm] = hist((nsecs - @start[tid])/1000); delete(@start[tid]); }'

# TCP retransmit with stack
bpftrace -e 'kprobe:tcp_retransmit_skb { @[kstack] = count(); }'

# Run queue latency
bpftrace -e 'tracepoint:sched:sched_wakeup { @qtime[args->pid] = nsecs; }
  tracepoint:sched:sched_switch { if (@qtime[args->next_pid]) {
    @us = hist((nsecs - @qtime[args->next_pid])/1000); delete(@qtime[args->next_pid]); }}'
```

---

## ftrace / trace-cmd

```bash
# Function graph tracing (no tools needed, just kernel)
echo function_graph > /sys/kernel/debug/tracing/current_tracer
echo ext4_file_write_iter > /sys/kernel/debug/tracing/set_graph_function
echo 1 > /sys/kernel/debug/tracing/tracing_on
cat /sys/kernel/debug/tracing/trace_pipe    # Live output
echo 0 > /sys/kernel/debug/tracing/tracing_on

# trace-cmd (user-friendly frontend)
trace-cmd record -p function_graph -g do_sys_open sleep 5
trace-cmd report | head -50
```

---

## Network Performance

```bash
ss -tanp                                # All TCP connections with PIDs
ss -s                                   # Socket summary (established, TIME_WAIT)
ss -ti state established               # Per-connection TCP internals (cwnd, rtt)
nstat -sz                               # Kernel TCP/IP counters
nstat -sz | grep -E 'Retrans|Drop|Overflow'  # Error counters
ethtool -S eth0 | grep -E 'drop|err|miss'   # NIC hardware errors
ethtool -g eth0                         # Ring buffer sizes
ethtool -G eth0 rx 4096                 # Increase RX ring buffer
sar -n DEV 1                            # Per-second NIC throughput
sar -n TCP,ETCP 1                       # TCP activity and errors
```

---

## Memory Diagnostics

```bash
free -m                                 # available (NOT free) is the key metric
cat /proc/meminfo | grep -E 'MemAvail|MemFree|Cached|Slab|SwapFree'
slabtop -s c                            # Kernel slab cache (sorted by size)
smem -t -k                              # Per-process PSS (true memory footprint)
cat /proc/<PID>/smaps_rollup            # RSS, PSS, Private_Dirty for a process
cat /proc/<PID>/status | grep -E 'VmRSS|VmSize|VmSwap'
cat /proc/pressure/memory               # Memory PSI
vmstat 1 | awk '{print $7,$8}'          # Watch si/so (swap in/out)
```

---

## Disk and Filesystem Diagnostics

```bash
iostat -xz 1                            # Disk I/O stats
iotop -oP                               # Per-process I/O (only active)
pidstat -d 1                            # Per-process I/O via pidstat
cat /sys/block/<dev>/queue/scheduler    # Current I/O scheduler
echo none > /sys/block/<dev>/queue/scheduler  # Set to noop (NVMe)
lsof +D /var/log                        # What processes have files open in dir
fio --name=randread --ioengine=libaio --direct=1 --bs=4k \
    --numjobs=4 --size=1G --runtime=30 --rw=randread  # Benchmark
```

---

## kdump / crash (Kernel Panic Analysis)

```bash
systemctl status kdump                  # Is kdump configured?
crash /usr/lib/debug/lib/modules/$(uname -r)/vmlinux /var/crash/*/vmcore
# Inside crash:
bt                                      # Backtrace of panicking task
ps                                      # Process list at crash time
log                                     # dmesg buffer
kmem -i                                 # Memory summary
files <PID>                             # Open files of a process
```

---

## Key /proc Files

| File | Purpose |
|---|---|
| `/proc/pressure/{cpu,memory,io}` | PSI stall metrics |
| `/proc/stat` | CPU time breakdown (all CPUs) |
| `/proc/meminfo` | Detailed memory stats |
| `/proc/vmstat` | VM event counters |
| `/proc/diskstats` | Per-disk I/O stats |
| `/proc/<PID>/stack` | Kernel stack (why D state?) |
| `/proc/<PID>/smaps_rollup` | True memory footprint |
| `/proc/<PID>/io` | Per-process I/O counters |
| `/proc/<PID>/sched` | Scheduler stats (wait time) |
| `/proc/schedstat` | Per-CPU scheduler stats |

---

## Decision Tree: "My Server Is Slow"

```
1. cat /proc/pressure/*         → Which resource is stalled?
2. cpu high?   → mpstat -P ALL  → pidstat 1    → perf top -g → flame graph
3. memory high? → free -m       → vmstat si/so → memleak / slabtop
4. io high?    → iostat -xz 1   → iotop -oP   → biolatency → check scheduler
5. all low?    → ss -s          → nstat retrans → ethtool -S → app profiling
```
