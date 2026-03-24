# Interview Questions 08: Performance & Debugging (Observability, Profiling, Tracing)

> FAANG / Staff+ SRE interview preparation. All answers structured with bullets/numbered lists.
> Full notes: [Performance & Debugging](../08-performance-and-debugging/performance-and-debugging.md)

---

## Q1: Walk me through how you would debug a slow server. What is your systematic methodology?

1. **Do not guess -- establish the bottleneck resource first.** Run the 60-second checklist: `uptime`, `dmesg -T | tail`, `vmstat 1`, `mpstat -P ALL 1`, `pidstat 1`, `iostat -xz 1`, `free -m`, `sar -n DEV 1`, `sar -n TCP,ETCP 1`, `top -bn1`
2. **Check PSI** (kernel 4.20+): `cat /proc/pressure/{cpu,memory,io}` -- directly identifies which resource has contention
3. **CPU path** (PSI cpu elevated, `vmstat r` > cores, high `us`/`sy`):
   - `pidstat 1` to identify the process
   - `perf top -g` or `perf record -g` for function-level profiling
   - Generate flame graph: `perf script | stackcollapse-perf.pl | flamegraph.pl > flame.svg`
4. **Memory path** (PSI memory elevated, `vmstat si/so` > 0, `free -m` available low):
   - `ps aux --sort=-%mem | head` to identify the memory consumer
   - `cat /proc/<PID>/smaps_rollup` for true memory footprint
   - `memleak-bpfcc -p <PID>` to detect leaks
5. **Disk path** (PSI io elevated, `iostat await` high, `vmstat wa` high):
   - `iotop -oP` to identify the I/O source
   - Check if it is swap activity (redirects to memory path)
   - Verify I/O scheduler: `cat /sys/block/<dev>/queue/scheduler`
6. **Network path** (infrastructure clean, PSI low):
   - `ss -s` for socket state anomalies (CLOSE_WAIT, TIME_WAIT explosion)
   - `nstat -sz | grep -E 'Retrans|Drop|Overflow'` for TCP/IP errors
   - `ethtool -S eth0` for NIC-level drops
7. **Application path** (all infrastructure clean):
   - `perf record -g -p <PID>` to profile application code
   - Check application logs, thread dumps, dependency health
8. **Correlate with recent changes:** What was deployed? What config changed? Check `last reboot`, deployment logs, git history

---

## Q2: Explain the USE method. How does it differ from RED? When would you use each?

**USE Method (Brendan Gregg) -- for infrastructure resources:**
- For every physical or software resource (CPU, memory, disk, NIC, kernel queues), check:
  1. **Utilization:** % time the resource is busy or % capacity used
  2. **Saturation:** Degree to which work is queued (overloaded)
  3. **Errors:** Count of error events
- Check order: Errors first (fast, often decisive), then Saturation (easy to interpret), then Utilization
- Example for CPU: Utilization = `mpstat %usr+%sys`, Saturation = `vmstat r` > cores, Errors = MCE in `dmesg`

**RED Method (Tom Wilkie) -- for request-driven services:**
- For every service endpoint, measure:
  1. **Rate:** Requests per second
  2. **Errors:** Failed requests per second
  3. **Duration:** Response time distribution (histograms, p50/p99/p999)
- Focus is on user experience, not infrastructure health

**When to use which:**
- USE for infrastructure investigation (CPU, disks, NICs, kernel queues)
- RED for application/service investigation (APIs, microservices)
- **SRE workflow:** Start with RED (user-facing symptoms: latency, errors), then drill into USE (infrastructure root cause)
- Google's Four Golden Signals (latency, traffic, errors, saturation) combine both perspectives

---

## Q3: What is the difference between perf and strace? When would you use each in production?

**strace:**
- Traces system calls using `ptrace()` -- stops the process twice per syscall (entry + exit)
- Causes 2 context switches per syscall, resulting in 100-300x slowdown in worst case
- Shows exact syscall arguments and return values (deterministic, not sampled)
- Use for: development debugging, finding missing config files, understanding unknown program behavior
- **Never use in production** on latency-sensitive services

**perf:**
- Uses `perf_events` kernel subsystem with hardware PMU (Performance Monitoring Unit)
- Sampling mode: periodic PMU interrupts capture instruction pointer + call stack, < 5% overhead
- Counting mode: `perf stat` counts hardware events with near-zero overhead
- Shows statistical profile of where CPU time is spent (functions, not individual calls)
- Safe for production with appropriate sample rate

**Production alternatives to strace:**
- `perf trace` -- tracepoint-based syscall tracing (~3x overhead, not 100x)
- `bpftrace` with syscall tracepoints (< 5% overhead)
- BCC `syscount` -- syscall frequency summary (< 1% overhead)

---

## Q4: Explain the eBPF architecture. Why is it safe to run in the production kernel?

1. **Program lifecycle:**
   - Source: written in C (BCC) or bpftrace DSL
   - Compiled to BPF bytecode by clang/LLVM
   - Loaded into kernel via `bpf()` system call
2. **Verifier (the safety gate):**
   - Performs static analysis of every possible execution path (DAG walk)
   - Ensures no out-of-bounds memory access
   - Ensures no infinite loops (pre-5.3) or bounded loops only (5.3+)
   - Ensures no unreachable code, validates all helper function calls
   - Rejects unsafe programs before they can execute -- this is the key safety guarantee
   - Limit: 1 million verified instructions (kernel 5.2+)
3. **JIT compiler:**
   - Converts verified BPF bytecode to native x86_64/ARM64 instructions
   - Eliminates interpreter overhead, runs at near-native speed
   - Enabled by default: `net.core.bpf_jit_enable = 1`
4. **Attachment points:**
   - kprobes (any kernel function entry/return)
   - Tracepoints (stable kernel instrumentation)
   - uprobes (user-space function tracing)
   - XDP (NIC driver pre-stack), socket filters, LSM hooks
5. **Maps (shared data structures):**
   - Hash tables, arrays, ring buffers, per-CPU variants, LRU caches, stack trace storage
   - Enable communication between kernel BPF programs and userspace tools
6. **Why safe:** Cannot crash the kernel, cannot access arbitrary memory, bounded execution time, all accesses validated before execution. Fundamentally safer than kernel modules.

---

## Q5: How do you generate and interpret a CPU flame graph?

1. **Record stack traces:**
   - `perf record -g -a sleep 30` (system-wide, 30 seconds, with call graphs)
   - `-g` enables call graph recording using frame pointers (or `--call-graph dwarf` for DWARF unwinding)
2. **Generate:**
   - `perf script | stackcollapse-perf.pl | flamegraph.pl > flame.svg`
   - Open in browser for interactive SVG (click to zoom)
3. **Interpretation rules:**
   - **X-axis:** Width = proportion of samples (wider = more CPU time). NOT a time axis.
   - **Y-axis:** Call stack depth. Bottom = entry point (e.g., `__libc_start_main`). Top = leaf function where CPU is actually burning.
   - **Color:** Random warm palette by default (no semantic meaning)
   - A wide plateau at the top = that function is directly consuming CPU
   - A wide frame in the middle with many narrow children = dispatch function
4. **Off-CPU flame graphs** (complementary):
   - `offcputime-bpfcc -df 30 > off.stacks && flamegraph.pl --color=io < off.stacks > offcpu.svg`
   - Show where threads are blocked (I/O, locks, sleep, page faults)
   - Essential for latency investigation -- on-CPU alone misses blocking time
5. **Differential flame graphs:**
   - Compare before/after: red = increased CPU, blue = decreased
   - Useful for identifying performance regressions after deployments

---

## Q6: Explain PSI (Pressure Stall Information). How is it superior to traditional metrics?

- **What:** Kernel 4.20+ feature that directly measures the percentage of wall-clock time tasks are stalled on a resource
- **Files:** `/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io`, `/proc/pressure/irq` (5.18+)
- **Two severity levels per file:**
  - `some`: At least one task stalled (partial -- some work still happening)
  - `full`: All non-idle tasks stalled simultaneously (complete -- zero productive work)
- **Time windows:** `avg10`, `avg60`, `avg300` (10-second, 60-second, 5-minute moving averages) + `total` (cumulative microseconds)
- **Why superior to traditional metrics:**
  1. CPU 80% utilization with PSI `some avg10=0` = fine (nobody waiting)
  2. CPU 80% utilization with PSI `some avg10=15` = tasks are waiting, users impacted
  3. `free -m` shows low available but PSI memory 0% = page cache doing its job
  4. `free -m` shows low available and PSI memory 8% = active reclaim causing latency
  5. `iostat %util` 100% but PSI io 0% = device has headroom (NVMe parallel I/O)
- **Production use:**
  - PSI triggers: write threshold to `/proc/pressure/memory`, poll fd for proactive response
  - `systemd-oomd` uses memory PSI to kill processes before kernel OOM killer
  - Kubernetes uses PSI for node health signaling
  - Export `avg10` to Prometheus; alert on `some avg10 > 10%` sustained

---

## Q7: What does %util in iostat actually measure? Why can it be misleading?

- `%util` measures the percentage of time during which at least one I/O request was outstanding on the device
- **Designed for single-queue rotational devices:** If one request at a time is all the device can handle, 100% means fully saturated
- **Misleading for modern devices (NVMe, RAID, SSDs):**
  - NVMe can serve 64+ requests in parallel across multiple hardware queues
  - A device at "100% util" could be serving 64 concurrent I/Os and have capacity for 64 more
  - `%util` reports 100% because there was always at least one I/O in flight -- it says nothing about parallelism
- **Better saturation indicators:**
  - `avgqu-sz`: Average I/O queue length. Compare to device queue depth capability.
  - `await`: Average latency including queue time. If much higher than device-rated latency, device is saturated.
  - `r_await` / `w_await`: Separate read/write latency. High write latency with low read may indicate journal contention.
- **Rule:** For NVMe, ignore `%util`. Use `await` and `avgqu-sz` as primary saturation indicators.

---

## Q8: How does strace work internally? Why does it cause 100x overhead?

- strace uses `ptrace(PTRACE_SYSCALL)` system call
- **Per-syscall overhead (2 stops, 2 context switches):**
  1. Tracee enters syscall, kernel checks `TIF_SYSCALL_TRACE` flag
  2. Kernel stops tracee, delivers `SIGTRAP` to tracer (context switch #1)
  3. Tracer reads syscall number + arguments via `ptrace(PTRACE_PEEKUSER)` / `PTRACE_GETREGS`
  4. Tracer resumes tracee with `ptrace(PTRACE_SYSCALL)`
  5. Syscall executes in kernel
  6. Kernel stops tracee on syscall exit (context switch #2)
  7. Tracer reads return value, formats output, resumes tracee
- **Overhead compounds with syscall rate:**
  - 100k syscalls/sec = 200k context switches/sec added
  - Each stop copies data between address spaces via small fixed-size ptrace transfers
  - The traced process does zero useful work while stopped
  - Benchmarks show 100-300x slowdown for I/O-heavy workloads
- **Low-overhead alternatives:**
  - `perf trace` (~3x overhead, uses tracepoints, not ptrace)
  - `bpftrace` with `tracepoint:raw_syscalls:sys_enter` (< 5% overhead)
  - BCC `syscount` (< 1% overhead, summary only)

---

## Q9: A server has load average 64 but only 10% CPU utilization. What is happening?

- **Key insight:** Linux load average includes both runnable processes AND processes in uninterruptible sleep (D state)
- **D state** = process waiting for I/O that cannot be interrupted (disk, NFS, kernel lock)
- **Diagnosis:**
  1. `vmstat 1`: Check `b` column (blocked processes) and `wa` (I/O wait %). High `b` + high `wa` = I/O bottleneck.
  2. `ps aux | awk '$8 ~ /^D/'`: List D-state processes
  3. `cat /proc/<PID>/stack`: See where each D-state process is blocked in the kernel
  4. `iostat -xz 1`: Check for a device with very high `await` (latency)
- **Common causes:**
  - Dead or slow NFS server (processes stuck in `nfs4_wait_clnt_recover`)
  - Failing disk (high latency, errors in `dmesg`)
  - Full swap on slow storage (processes stuck in page-in from disk)
  - Mass page fault activity (all processes stalled waiting for memory reclaim)
- **Resolution depends on cause:** Fix NFS, replace disk, add RAM, mount NFS with `soft,timeo=50`
- **Interview trap:** High load average does NOT mean CPU bottleneck. It often means I/O problem.

---

## Q10: How would you diagnose TCP retransmissions in production?

1. **Detect retransmissions:**
   - `nstat -sz | grep Retrans` -- `TcpRetransSegs` total count
   - Compare `TcpRetransSegs` to `TcpOutSegs` for retransmit ratio
   - Healthy: < 0.1%. Concerning: > 1%. Critical: > 5%.
2. **Identify affected connections:**
   - `ss -ti state established | grep -v 'retrans:0'` -- per-connection retransmit count
3. **Live tracing:**
   - `tcpretrans-bpfcc` -- BCC tool showing each retransmit with source, destination, state
   - `bpftrace -e 'kprobe:tcp_retransmit_skb { @[kstack] = count(); }'` -- with kernel stacks
4. **Determine root cause:**
   - Retransmits to specific destination = remote host or path issue
   - Retransmits on all connections = local NIC or switch problem
   - `ethtool -S eth0 | grep -i drop` -- NIC-level drops
   - `sar -n DEV 1` -- per-second for microburst detection
5. **Differentiate retransmit types:**
   - `TcpExtTCPLossProbes` (TLP) -- proactive probes, usually benign
   - `TcpExtTCPLostRetransmit` -- actual detected losses
   - `TcpExtTCPSackRecovery` -- SACK-based recovery events
6. **Resolution:**
   - Increase ring buffers: `ethtool -G eth0 rx 4096`
   - Switch to BBR congestion control for lossy links
   - Fix MTU/PMTUD issues if large packets are being dropped

---

## Q11: Explain the differences between vmstat, mpstat, pidstat, and sar. What is the investigation workflow?

**vmstat (Virtual Memory Statistics):**
- System-wide snapshot: CPU, memory, swap, I/O, scheduling
- Use as first command for high-level picture
- Key columns: `r` (run queue), `si/so` (swap), `us/sy/wa/st` (CPU)
- **Gotcha:** First line is boot average -- always skip it

**mpstat (Multi-Processor Statistics):**
- Per-CPU breakdown
- Use when vmstat shows high CPU to determine distribution
- Identifies: single-threaded bottleneck (one CPU 100%), IRQ imbalance (one CPU high %irq)

**pidstat (Per-Process Statistics):**
- Per-process CPU, memory, I/O, context switches, threads
- Use to attribute system-wide resource usage to specific processes
- Like scriptable `top` but with `-d`, `-r`, `-w`, `-t` modes

**sar (System Activity Reporter):**
- Historical data collection and replay (requires sysstat cron job)
- Covers: CPU, memory, disk, network, TCP, run queue
- Use for: post-incident analysis, baseline comparison, trend analysis
- `sar -A` for comprehensive report, `sar -f /var/log/sa/sa15` for specific day

**Investigation workflow:**
1. `vmstat 1` -- system-wide overview (which resource?)
2. `mpstat -P ALL 1` -- per-CPU breakdown (even distribution or single-core?)
3. `pidstat 1` -- per-process attribution (which process?)
4. `sar -f <file>` -- historical context (when did it start? is this normal?)

---

## Q12: How would you debug a process stuck in D (uninterruptible sleep) state?

1. **Identify D-state processes:**
   - `ps aux | awk '$8 ~ /^D/ {print}'`
   - `top`: look for `D` in the `S` column
2. **Get the kernel stack:**
   - `cat /proc/<PID>/stack` -- shows exactly where in the kernel the process is blocked
3. **Common D-state causes and kernel stack signatures:**
   - **Disk I/O wait:** Stack shows `io_schedule`, `wait_on_page_bit`, `blk_mq_*` -- check `iostat -xz 1`
   - **NFS hang:** Stack shows `nfs4_wait_clnt_recover`, `rpc_wait_bit_killable` -- check NFS server
   - **Device driver:** Stack shows driver-specific functions -- check `dmesg` for hardware errors
   - **Kernel lock:** Stack shows `mutex_lock`, `down_read` -- potential kernel bug
4. **D-state processes cannot be killed:**
   - `SIGKILL` is queued but process cannot wake to handle it
   - Must fix the underlying I/O or resource issue
5. **NFS-specific fixes:**
   - `mount -o soft,timeo=50` to allow NFS ops to fail instead of hang
   - `mount -o intr` on older kernels
6. **Disk-specific:**
   - Check device timeout: `cat /sys/block/<dev>/device/timeout`
   - If disk is failing, D-state resolves when I/O completes or error timeout expires

---

## Q13: What is ftrace? When would you use it instead of perf or eBPF?

**What ftrace is:**
- Kernel's built-in tracing framework, controlled via `/sys/kernel/debug/tracing/` (tracefs)
- Tracers: `function` (every kernel function call), `function_graph` (with call depth + timing), `nop` (tracepoints only)
- Implemented via GCC `-pg` flag inserting `mcount()` calls, NOP'd at boot, dynamically patched when enabled

**When to use ftrace over perf/eBPF:**
1. **Minimal environment:** No perf, BCC, or bpftrace installed (rescue mode, embedded, old kernel). ftrace is always present if `CONFIG_FTRACE=y`.
2. **Function call flow visualization:** `function_graph` tracer shows exact call sequences with indentation and per-function timing -- perf and eBPF cannot easily replicate this
3. **Kernel boot tracing:** ftrace can trace kernel initialization before userspace tools are available
4. **trace-cmd for structured capture:** `trace-cmd record -p function_graph -g ext4_file_write_iter` captures a call graph for KernelShark visualization

**When NOT to use ftrace:**
- When you need aggregation (histograms, per-process stats) -- use eBPF
- When you need userspace tracing -- use uprobes via perf/bpftrace
- When you need low-overhead production monitoring -- use eBPF

---

## Q14: Explain how kdump works. How do you analyze a kernel panic post-mortem?

**kdump mechanism:**
1. At boot, `kexec -p` preloads a secondary "capture kernel" into reserved memory (typically 256 MiB, configured via `crashkernel=256M` boot parameter)
2. When the kernel panics, instead of rebooting, it `kexec`s into the capture kernel
3. The capture kernel runs in the reserved memory region and can safely access the crashed kernel's memory
4. The crashed kernel's memory is exported as `/proc/vmcore` (ELF format)
5. The vmcore is saved to disk (default: `/var/crash/`) or transmitted over network
6. System reboots into the normal kernel

**Analyzing with crash tool:**
- `crash /usr/lib/debug/lib/modules/$(uname -r)/vmlinux /var/crash/<dir>/vmcore`
- Key commands:
  - `bt` -- Backtrace of the panicking task (most important first step)
  - `bt -a` -- Backtrace of all CPUs
  - `ps` -- Process list at time of crash
  - `log` -- dmesg buffer from crashed kernel
  - `kmem -i` -- Kernel memory summary
  - `files <PID>` -- Open files of a specific process
  - `vm <PID>` -- Virtual memory map of a process
  - `task` -- Current task struct details

**Prerequisites:**
- Package `kexec-tools` installed and `kdump` service enabled
- Kernel debuginfo package matching running kernel
- Sufficient reserved memory (`crashkernel=` boot parameter)

---

## Q15: What are BCC and bpftrace? When do you choose one over the other?

**BCC (BPF Compiler Collection):**
- Toolkit of 80+ pre-built eBPF tools: `execsnoop`, `biolatency`, `tcpretrans`, `runqlat`, `memleak`
- Tools written in Python/Lua with embedded C (BPF program)
- Compiles C to BPF bytecode at runtime via LLVM (slow startup, ~5 seconds)
- Best for: complex, reusable tools and long-running collection daemons

**bpftrace:**
- High-level tracing language (AWK-like DSL) for Linux eBPF
- JIT compiles to BPF (faster startup than BCC)
- Best for: one-liners, ad-hoc investigation, quick hypotheses testing

**Decision guide:**
| Scenario | Tool |
|---|---|
| Quick: "What syscalls is PID 1234 making?" | `bpftrace` one-liner |
| Quick: "Show me I/O latency histogram" | `biolatency` (BCC) |
| Quick: "Count kernel function calls" | `funccount` (BCC) |
| Ad-hoc: "Trace writes to /tmp by root" | `bpftrace` script |
| Long-running: "Export metrics to Prometheus" | Custom BCC tool |
| Reusable tool for the team | BCC (Python wrapper) |

---

## Q16: How would you identify and fix network microbursts causing retransmissions?

1. **Detection challenge:** Microbursts are invisible to 5-minute average monitoring (2Gbps average on 10Gbps link looks fine)
2. **Per-second monitoring:** `sar -n DEV 1 60 | grep eth0` -- look for seconds where throughput spikes to near line rate
3. **NIC-level evidence:**
   - `ethtool -S eth0 | grep -E 'drop|miss|over'` -- ring buffer overflows
   - `nstat TcpRetransSegs` -- retransmissions correlated with burst windows
4. **High-resolution tracing:**
   - `bpftrace -e 'tracepoint:net:netif_receive_skb { @bytes = sum(args->len); } interval:ms:100 { printf("100ms: %d bytes\n", @bytes); clear(@bytes); }'`
   - Shows per-100ms traffic volume, revealing burst patterns
5. **Fix (absorb the burst):**
   - Increase NIC ring buffer: `ethtool -G eth0 rx 4096`
   - Increase TCP receive buffers: `sysctl net.core.rmem_max=16777216`
   - Increase socket backlog: `sysctl net.core.netdev_max_backlog=5000`
6. **Fix (prevent the burst):**
   - Traffic shaping at the source (token bucket, pacing)
   - Enable TCP pacing on sender: `sysctl net.ipv4.tcp_pacing=1` or use BBR (has built-in pacing)
7. **Monitoring:** Deploy per-second NIC drop rate and per-second bandwidth monitoring, not per-5-minute

---

## Q17: Explain the I/O schedulers available in modern Linux. How do you choose the right one?

**Available schedulers (blk-mq era, kernel 5.x+):**

| Scheduler | Best For | How It Works |
|---|---|---|
| `none` (noop) | NVMe, SSDs, RAID arrays | Simple FIFO, no reordering. Device handles parallelism internally. |
| `mq-deadline` | SSDs, general purpose | Assigns deadline to each I/O request, prevents starvation. Good default. |
| `bfq` (Budget Fair Queue) | Desktops, interactive | Per-process I/O budgets. Excellent responsiveness but higher overhead. |
| `kyber` | Fast SSDs | Token-based. Targets read/write latencies. Low overhead. |

**Legacy (single-queue, pre-5.0):**
- `cfq` (Completely Fair Queuing): default for HDDs, harmful on SSDs due to reordering overhead
- `deadline`: precursor to `mq-deadline`
- `noop`: simple FIFO

**How to check and set:**
```bash
cat /sys/block/nvme0n1/queue/scheduler   # Check current
echo none > /sys/block/nvme0n1/queue/scheduler  # Set
# Persistent via udev rule or kernel boot parameter
```

**Decision guide:**
- NVMe: `none` (always)
- Enterprise SSD (SATA/SAS): `mq-deadline`
- HDD: `mq-deadline` or `bfq`
- Desktop/laptop: `bfq` (best interactive responsiveness)

---

## Q18: What is the OOM killer? How does the kernel select which process to kill?

1. **Trigger:** Kernel cannot satisfy a memory allocation after exhausting all reclaim options (kswapd, direct reclaim, compaction all failed)
2. **Selection algorithm (`oom_badness()`):**
   - Base score = RSS + swap usage of the process (proportional to memory consumed)
   - Children's memory can be included
   - Adjusted by `oom_score_adj` (-1000 to +1000)
   - Score -1000: process is completely exempt from OOM kill
   - Score +1000: process is killed first
   - Kernel threads and PID 1 (init) are always exempt
   - The process with the highest final score is selected
3. **Execution:** Sends `SIGKILL` to selected process; logged in `dmesg` with full memory dump
4. **Control mechanisms:**
   - `echo -1000 > /proc/<PID>/oom_score_adj` -- protect critical services (use sparingly)
   - Memory cgroups (`memory.max`) -- scope OOM to a cgroup (container/pod)
   - `vm.overcommit_memory=2` -- strict mode, prevents OOM by refusing allocations
   - `earlyoom` / `systemd-oomd` -- userspace OOM using PSI triggers, kills before kernel OOM
5. **View current scores:** `cat /proc/<PID>/oom_score` -- higher = more likely to be killed

---

## Q19: How do you debug a kernel soft lockup? What causes them?

- **Soft lockup:** A CPU has been executing kernel code for longer than the watchdog threshold (default 20 seconds) without scheduling
- **Detection:** `watchdog/N` kernel thread checks that the scheduler ran on each CPU. If not, logs: `BUG: soft lockup - CPU#N stuck for Xs!`
- **Common causes:**
  1. **Spinlock contention:** A lock held for too long under heavy contention (e.g., conntrack hash table on many-core machines)
  2. **Long-running interrupt handler:** A device driver spending too long in hardirq or softirq context
  3. **Kernel bug:** Infinite loop in kernel code path
  4. **RCU stall:** Read-Copy-Update mechanism stalled (related messages: `rcu: INFO: rcu_sched detected stalls`)
- **Investigation:**
  - `dmesg`: The soft lockup message includes a backtrace showing where the CPU was stuck
  - `perf top`: Look for hot kernel functions (`_raw_spin_lock`, specific driver functions)
  - `mpstat -P ALL 1`: Affected CPUs show 100% in `%sys` or `%soft`
  - `bpftrace -e 'kprobe:_raw_spin_lock { @[kstack(5)] = count(); }'` -- identify contended locks
- **Resolution depends on cause:**
  - Spinlock contention: reduce lock scope, increase hash table size, bypass the subsystem (e.g., `NOTRACK` for conntrack)
  - Device driver: update driver, check firmware, replace hardware
  - Kernel bug: upgrade kernel, apply patch

---

## Q20: A Java application reports 8 GiB RSS but free -m shows 2 GiB available. Is this a problem?

- **Not necessarily.** Evaluate with these checks:
  1. `cat /proc/pressure/memory` -- if `some avg10 ~ 0`, no pressure, system is fine
  2. `vmstat 1` -- if `si`/`so` are 0, no swapping
  3. `sar -B 1` -- if `pgscank` and `pgscand` are near 0, reclaim is not active
  4. `cat /proc/$(pidof java)/smaps_rollup` -- check `Private_Dirty` for true unique usage
- **When it IS a problem:**
  - `MemAvailable` trending downward over days (memory leak)
  - PSI memory `some avg10` > 5% (active pressure)
  - `si`/`so` > 0 sustained (swap storm)
  - JVM `-Xmx` > physical RAM and GC cannot keep heap compact
- **Key principle:** `MemFree` being low is **normal** -- Linux uses free memory for page cache. `MemAvailable` is the correct metric. Alert on `MemAvailable`, never on `MemFree`.
