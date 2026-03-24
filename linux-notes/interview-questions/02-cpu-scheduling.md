# Interview Questions: 02 -- CPU Scheduling

> **Study guide for Senior SRE / Staff+ / Principal Engineer interviews**
> Full topic reference: [cpu-scheduling.md](../02-cpu-scheduling/cpu-scheduling.md)
> Cheatsheet: [02-cpu-scheduling.md](../cheatsheets/02-cpu-scheduling.md)

---

## How to Use This File

- Questions are organized by category and tagged with difficulty level
- **Senior** = Expected knowledge for Senior SRE (L5/E5)
- **Staff** = Expected for Staff Engineer (L6/E6)
- **Principal** = Expected for Principal/Distinguished Engineer (L7+/E7+)
- Practice answering aloud. Time yourself: 2-3 minutes for conceptual, 3-5 minutes for scenario-based
- For scenario questions, structure your answer as: Symptoms -> Hypothesis -> Investigation commands -> Root cause -> Fix -> Prevention

---

## Category 1: Conceptual Deep Questions

### Q1. Explain the difference between load average and CPU utilization. Why can you have a load average of 50 on a 16-core system with 5% CPU utilization?

**Difficulty:** Senior | **Category:** Core Concepts

**Answer:**

1. **CPU utilization** measures the percentage of time CPUs spend executing (non-idle), counting `%usr`, `%sys`, `%irq`, `%softirq`, `%steal`, `%guest`
2. **Load average** counts the average number of tasks in **both** the runnable (R) state AND the uninterruptible sleep (D) state over 1, 5, and 15 minute exponentially decaying windows
3. The **D-state inclusion** is Linux-specific -- other Unixes only count runnable tasks. This was intentionally added to capture I/O-stalled demand
4. Load of 50 with 5% CPU means ~48 processes are in D-state (uninterruptible sleep), typically:
   - Blocked NFS operations (server unresponsive)
   - Disk I/O on failing or degraded storage
   - Kernel lock contention (rare)
5. **Diagnostic commands:**
   - `mpstat -P ALL 1` -- confirm low CPU, check `%iowait`
   - `ps aux | awk '$8 ~ /D/'` -- list D-state processes
   - `cat /proc/pressure/io` -- I/O pressure
   - `dmesg | tail` -- storage or NFS errors
6. **Key takeaway:** Load average is a **demand** metric (how many things want to run or are blocked), not a **utilization** metric (how busy CPUs are)

---

### Q2. How does CFS calculate time slices? What happens to time slices as the number of runnable tasks increases?

**Difficulty:** Staff | **Category:** Scheduler Internals

**Answer:**

1. CFS does not use fixed time slices. It calculates a **proportional share** of the scheduling period
2. The **scheduling period** (`sched_latency_ns`) is the interval in which every runnable task should get at least one turn (default: 6ms for up to 8 tasks)
3. Each task's time slice = `sched_latency * (task_weight / total_weight_of_all_runnable_tasks)`
4. **Example with equal priorities:** 4 tasks at nice 0 (weight 1024 each): each gets 6ms/4 = 1.5ms
5. **Example with mixed priorities:** nice -5 (weight 3121) + three nice 0 (weight 1024 each):
   - Total weight = 3121 + 3072 = 6193
   - Nice -5: 6ms * (3121/6193) = 3.02ms
   - Each nice 0: 6ms * (1024/6193) = 0.99ms
6. When tasks exceed `sched_nr_latency` (default 8), the period extends: `period = nr_tasks * sched_min_granularity_ns` (default 0.75ms)
7. With 100 tasks: period becomes 100 * 0.75ms = 75ms, each nice-0 task gets 0.75ms
8. **Trade-off:** More tasks = longer scheduling period = higher scheduling latency, but minimum granularity prevents context switch thrashing

---

### Q3. Explain EEVDF and how it improves upon CFS. What specific problems did CFS have that EEVDF solves?

**Difficulty:** Principal | **Category:** Scheduler Internals

**Answer:**

1. **EEVDF** = Earliest Eligible Virtual Deadline First, replaced CFS in kernel 6.6 (October 2023, authored by Peter Zijlstra, based on a 1995 paper)
2. **CFS problems EEVDF solves:**
   - CFS relied on ad-hoc heuristics for latency control (`sched_latency_ns`, `sched_min_granularity_ns`, sleeper vruntime adjustment)
   - Sleeper fairness was a constant source of regressions -- CFS had to guess how much vruntime credit to give waking tasks
   - CFS picked leftmost (lowest vruntime) task, but did not account for how much time the task actually needed
3. **EEVDF mechanism:**
   - Tracks **lag** for each task: positive lag = underserved, negative lag = overserved
   - A task is **eligible** only if `lag >= 0`
   - Among eligible tasks, picks the one with the **earliest virtual deadline**
   - Virtual deadline = `vruntime + (requested_slice / weight)`
4. **Why this is better:**
   - Latency guarantees are **algorithmic** -- an underserved task automatically gets a shorter virtual deadline
   - No sleeper-fairness heuristics -- lag naturally accounts for time away from CPU
   - Short-running tasks (latency-sensitive) get earlier deadlines than long-running tasks (throughput)
   - Fewer sysctl knobs that can be misconfigured in production
5. **Practical impact:** Most workloads see negligible difference; latency-sensitive workloads (desktop interactivity, real-time audio) see measurable improvement in tail latency

---

### Q4. What is the relationship between scheduling priority, nice value, and weight in the Linux kernel? Why is the mapping exponential rather than linear?

**Difficulty:** Staff | **Category:** Scheduler Design

**Answer:**

1. **Priority** = kernel internal value (0-139):
   - 0-99: real-time priorities
   - 100-139: normal task priorities (maps to nice -20 to +19)
2. **Nice value** = user-visible priority (-20 to +19), maps to kernel priority as `priority = nice + 120`
3. **Weight** = what the scheduler actually uses for CPU share calculation, from `sched_prio_to_weight[]` table:
   - Nice 0 = weight 1024 (baseline)
   - Nice -20 = weight 88761 (86.7x baseline)
   - Nice +19 = weight 15 (0.015x baseline)
4. **Why exponential (1.25x per level):**
   - With linear mapping, the difference between nice 0->1 would be the same absolute amount as nice 18->19
   - Exponential means each nice level always represents a **10% relative change** in CPU share
   - Makes nice values intuitive: "nice +1 always gives 10% less CPU than before" regardless of starting point
   - Mathematical basis: `1 - 1/1.25 = 0.2`; with two tasks differing by 1 nice level, the higher-priority task gets ~55% vs ~45% (approximately 10% advantage)
5. **Practical implication:** The difference between nice -20 and nice -10 is the same **ratio** (~9.3x) as between nice 0 and nice 10

---

### Q5. Describe the three parameters of SCHED_DEADLINE (runtime, deadline, period) and how the kernel's admission control works.

**Difficulty:** Principal | **Category:** Real-Time Scheduling

**Answer:**

1. **SCHED_DEADLINE** implements Earliest Deadline First (EDF) with Constant Bandwidth Server (CBS):
   - `runtime`: CPU time (nanoseconds) the task is guaranteed per period
   - `deadline`: time window from the start of each period within which the runtime must be delivered
   - `period`: the recurrence interval
2. **Constraints:** `runtime <= deadline <= period`
3. **Example:** `runtime=10ms, deadline=30ms, period=50ms` means: every 50ms, the task gets 10ms of CPU, which must be delivered within the first 30ms of each period
4. **Admission control:**
   - Kernel checks that `sum(runtime_i / period_i)` for all SCHED_DEADLINE tasks on a CPU does not exceed 1.0 (100%)
   - If adding a new SCHED_DEADLINE task would exceed capacity, `sched_setattr()` returns `-EBUSY`
   - This prevents overcommitment and guarantees that accepted deadlines can be met
5. **Behavioral guarantees:**
   - SCHED_DEADLINE preempts all other scheduling classes (including SCHED_FIFO at priority 99)
   - If a task exceeds its runtime budget, it is **throttled** until the next period (CBS mechanism)
   - Does not require root if `/proc/sys/kernel/sched_rt_runtime_us` is properly configured
6. **Production use case:** Periodic sensor polling, audio frame processing, control loops where both periodicity and bounded latency are required

---

## Category 2: Scenario-Based Questions

### Q6. Your team's latency-sensitive API service is experiencing p99 latency spikes every 30 seconds. The spikes last 2-3 seconds. CPU utilization is normal. What do you investigate?

**Difficulty:** Senior | **Category:** Debugging

**Answer:**

1. **Hypothesis:** Periodic task causing preemption or resource contention
2. **Investigation steps:**
   - `pidstat -u -w 1 60` -- correlate involuntary context switch spikes with the 30-second interval
   - `cat /sys/fs/cgroup/<pod>/cpu.stat` -- check for CPU throttling (`nr_throttled`)
   - `sar -q 1 60` -- check if run queue depth spikes every 30 seconds
   - `perf sched record -- sleep 60` then `perf sched latency --sort max` -- find scheduling latency outliers
3. **Common causes of periodic 30-second spikes:**
   - Cron jobs or systemd timers (log rotation, health checks, metric collection)
   - Garbage collection pauses (JVM, Go GC) -- check GC logs
   - Kubernetes liveness/readiness probes triggering expensive health check endpoints
   - cgroup CPU throttling (burst then throttle cycle)
   - Transparent Huge Page (THP) compaction: `cat /proc/vmstat | grep thp_collapse_alloc`
4. **Resolution:** Identify the periodic task with `atop` recording, stagger cron jobs, tune GC settings, or disable THP defrag: `echo madvise > /sys/kernel/mm/transparent_hugepage/defrag`

---

### Q7. After deploying a new version, your service's CPU utilization jumped from 40% to 85%. How do you methodically identify the cause?

**Difficulty:** Senior | **Category:** Performance

**Answer:**

1. **Immediate triage:**
   - `mpstat -P ALL 1 5` -- is the increase in `%usr` (application code) or `%sys` (syscalls/kernel)?
   - `pidstat -u -t 1 5` -- per-thread CPU breakdown to identify hot threads
2. **If %usr increase:**
   - `perf record -g -p <PID> sleep 30` then `perf report` or generate flamegraph
   - Compare flamegraph with previous version's baseline
   - Look for new hot functions, increased call frequency, algorithmic complexity regression
   - `strace -c -p <PID>` -- summary of syscall frequency and time
3. **If %sys increase:**
   - `perf stat -e 'syscalls:sys_enter_*' -p <PID> sleep 10` -- which syscalls increased?
   - Common causes: excessive logging (`write()`), memory allocation storms (`mmap/brk`), new network calls (`connect/sendto`)
4. **Correlation with deployment:**
   - Diff deployment artifacts and config between versions
   - Check thread pool sizes, connection pool sizes, buffer sizes
   - Check dependency version changes (new library version doing CPU-intensive work)
5. **Quick mitigation:** Set a `cpu.max` limit to protect co-located services while investigating

---

### Q8. You notice that a specific CPU core is at 100% while all other cores are near idle. What could cause this, and how do you fix it?

**Difficulty:** Staff | **Category:** CPU Topology

**Answer:**

1. **Possible causes:**
   - Single-threaded process pinned (via `taskset` or `cpuset`) to that core
   - IRQ affinity: a busy NIC's interrupts all assigned to one core
   - Software interrupt (softirq) processing concentrated on one core (RPS/RFS not configured)
   - Kernel worker thread (`kworker`) bound to a specific CPU
2. **Investigation:**
   - `mpstat -P ALL 1` -- identify the hot core number
   - `ps -eo pid,psr,pcpu,comm --sort=-pcpu | head` -- `psr` column shows which CPU each process uses
   - `cat /proc/interrupts` -- check IRQ distribution across CPUs
   - `cat /proc/irq/<IRQ>/smp_affinity_list` -- see which CPUs handle each interrupt
3. **Fixes by cause:**
   - **Pinned process:** Remove affinity: `taskset -pc 0-$(nproc) <PID>`
   - **IRQ imbalance:** Spread interrupts: `echo 2 > /proc/irq/<IRQ>/smp_affinity` or enable `irqbalance`
   - **NIC softirq:** Enable Receive Packet Steering: `echo fff > /sys/class/net/eth0/queues/rx-0/rps_cpus`
   - **Single-threaded bottleneck:** Architectural problem requiring multi-threading or multi-process redesign

---

### Q9. A containerized workload is using exactly its CPU limit but its actual throughput is 30% lower than expected. The same workload on bare-metal with the same core count performs fine. Diagnose.

**Difficulty:** Staff | **Category:** cgroups / Containers

**Answer:**

1. **Check CPU throttling:**
   - `cat /sys/fs/cgroup/<pod>/cpu.stat` -- look at `nr_throttled` and `throttled_usec`
   - Even if average utilization equals the limit, throttling occurs due to **burst patterns**
   - A workload using 4 cores for 50ms then idling for 50ms gets throttled because quota is consumed in bursts
2. **CFS bandwidth control bug (pre-5.4 kernels):**
   - Known issue where multi-threaded applications were over-throttled because quota consumed globally but checked per-CPU
   - Fixed in kernel 5.4 with CFS bandwidth timer rework
3. **NUMA effects in containers:**
   - Container not pinned to a NUMA node -- cross-node memory access adding 40-100% latency
   - Check with `numastat -p <PID>`
4. **CPU steal time:**
   - `mpstat 1` -- check `%steal` column for hypervisor reclamation
5. **Context switch overhead:**
   - Many threads sharing a small CPU quota -- excessive switching within the cgroup
   - Check: `cat /proc/<PID>/status | grep ctxt`
6. **Resolution:** Increase `cpu.max` period (200ms instead of 100ms) to smooth burst throttling, pin to NUMA node, verify no CPU steal, right-size thread pool to match allocated cores

---

### Q10. Production Redis instances show bimodal latency: some operations at 50us, others at 120us, with no pattern. How do you investigate?

**Difficulty:** Staff | **Category:** NUMA

**Answer:**

1. **Hypothesis:** NUMA imbalance -- process bouncing between NUMA nodes
2. **Investigation:**
   - `numactl --hardware` -- confirm multi-socket system and node distances
   - `taskset -p $(pgrep redis-server)` -- check if pinned (likely not)
   - `numastat -p $(pgrep redis-server)` -- check memory distribution across nodes
   - `cat /proc/vmstat | grep numa` -- check `numa_miss` and `numa_foreign` counts
   - `pidstat -u -p $(pgrep redis-server) 1 10` -- watch CPU column for node bouncing
3. **Confirmation:** If memory is split ~50/50 across nodes and `numa_miss` is significant (>5% of `numa_hit`), NUMA imbalance is confirmed
4. **Root cause:** Without NUMA pinning, the scheduler migrates the single-threaded Redis process between nodes. Cross-node memory access (typically 2x slower due to QPI/UPI interconnect) creates the bimodal distribution
5. **Fix:**
   - Immediate: `numactl --cpunodebind=0 --membind=0 -- redis-server /etc/redis/redis.conf`
   - Systemd: `CPUAffinity=0-15`, `NUMAPolicy=bind`, `NUMAMask=0`
   - Verify: `numastat -p <PID>` should show all memory on one node
6. **Prevention:** NUMA pinning audit for all latency-sensitive services, monitor `numa_miss` in `/proc/vmstat`

---

## Category 3: Debugging Questions

### Q11. Walk through exactly how you would use `perf sched` to diagnose a scheduling latency problem.

**Difficulty:** Staff | **Category:** Observability

**Answer:**

1. **Record scheduling events:**
   ```bash
   sudo perf sched record -a -- sleep 30
   ```
   Traces `sched_switch`, `sched_wakeup`, `sched_migrate` events system-wide for 30 seconds

2. **Analyze with `perf sched latency`:**
   ```bash
   sudo perf sched latency --sort max
   ```
   - Shows per-task: max scheduling latency, avg latency, total runtime, switch count
   - Look for tasks with max >> avg (outliers indicate periodic starvation)

3. **Timeline view with `perf sched timehist`:**
   ```bash
   sudo perf sched timehist --summary
   ```
   - Shows each context switch with wait time and run time
   - Filter: `perf sched timehist | grep myapp`
   - Look for individual switches with wait time exceeding your latency budget

4. **CPU map view:**
   ```bash
   sudo perf sched map
   ```
   - Shows which task runs on which CPU at each point in time
   - Useful for finding migration patterns or underutilized CPUs

5. **Key red flags:**
   - Max wait time > 10ms = scheduling starvation
   - Frequent CPU migrations = cache thrashing
   - Involuntary switches >> voluntary switches = CPU contention

---

### Q12. A process has 50,000 involuntary context switches per second. Is this a problem? How do you determine the cause?

**Difficulty:** Senior | **Category:** Performance

**Answer:**

1. **Assessment:** 50K involuntary switches/sec is likely a problem:
   - Each costs ~2-5 microseconds
   - Total: 100-250ms of overhead per second on one core (10-25% capacity loss)
2. **Voluntary vs. involuntary:**
   - **Voluntary:** Process called `sleep()`, `read()`, `futex()` -- chose to yield. Normal
   - **Involuntary:** Scheduler forcibly preempted -- time slice expired or higher-priority task arrived
3. **Diagnosis commands:**
   - `pidstat -w -t -p <PID> 1` -- per-thread involuntary switch counts
   - `cat /proc/<PID>/sched` -- `nr_involuntary_switches`, `se.slice`
   - `vmstat 1` -- system-wide `cs` column
   - `ps -eLo pid,tid,psr,ni,comm -p <PID>` -- thread count and CPU assignments
4. **Common causes:**
   - Too many threads for available cores (thread pool oversizing)
   - Low nice value competing with many other processes
   - CPU cgroup throttling (quota exhausted within period)
   - RT task preemption from another process
5. **Fix:** Reduce thread count, pin to dedicated CPUs, increase CPU weight/quota, or reduce competing workloads

---

### Q13. Explain what `/proc/sched_debug` shows and when you would use it.

**Difficulty:** Staff | **Category:** Kernel Internals

**Answer:**

1. **Contents:**
   - Per-CPU run queue state: number of runnable tasks, current task, clock values
   - CFS run queue details: `min_vruntime`, `nr_running`, `load` weight
   - RT run queue state: per-priority-level task counts
   - Per-task scheduling entity details: `vruntime`, `sum_exec_runtime`, `nr_switches`
2. **When to use:**
   - Investigating why a specific task is not getting scheduled despite being runnable
   - Debugging scheduler fairness issues -- compare `vruntime` values across tasks
   - Verifying `isolcpus` is working -- isolated CPUs should show 0 tasks
   - Checking for run queue imbalance across CPUs
3. **Key fields:**
   - `runnable tasks:` count per CPU (should be balanced)
   - `.min_vruntime` -- per-CFS-RQ floor value
   - `curr->vruntime` -- current task's virtual runtime
   - `clock` and `clock_task` -- per-CPU scheduler clocks
4. **Complementary files:**
   - `/proc/schedstat` -- per-CPU scheduling statistics
   - `/proc/<PID>/sched` -- per-process scheduling details

---

### Q14. How do you identify and resolve CPU throttling in a Kubernetes pod?

**Difficulty:** Senior | **Category:** Containers

**Answer:**

1. **Detection:**
   - `cat /sys/fs/cgroup/kubepods/pod-<ID>/cpu.stat`
   - Key fields: `nr_throttled` (throttle event count), `throttled_usec` (total time throttled)
   - Calculate throttle ratio: `nr_throttled / nr_periods` -- alert if > 10%
   - Prometheus: `container_cpu_cfs_throttled_periods_total` / `container_cpu_cfs_periods_total`
2. **Symptoms:**
   - Application latency spikes at regular intervals
   - CPU utilization flat at exactly the limit
   - Throughput degrades under load despite "available" CPU
3. **Common causes:**
   - CPU limit too low for bursty workloads
   - Multi-threaded app with more threads than allocated cores
   - Short CFS period (100ms default) penalizes burst patterns
4. **Resolution options (ordered by recommendation):**
   - Increase CPU limit (simplest)
   - Remove CPU limit entirely (use only requests) -- controversial but used at Google-scale
   - Increase CFS period: `--cpu-cfs-quota-period` in kubelet (e.g., 200ms)
   - Right-size thread pool to allocated cores
   - Use `CPUManagerPolicy=static` for Guaranteed QoS pods (exclusive cores)

---

## Category 4: Trick Questions

### Q15. A system with 8 cores shows a load average of 4. Is the system underutilized, overloaded, or properly loaded?

**Difficulty:** Senior | **Category:** Trick Question

**Answer:**

1. **You cannot determine this from load average alone** -- this is the trick
2. If load 4 = four CPU-bound runnable tasks: using 50% capacity (4/8 cores). Likely fine
3. If load 4 = four tasks in D-state (I/O wait): CPU might be 0% utilized but system is **stalled** on I/O
4. If load 4 = 300 tasks each with tiny CPU slices: could indicate overhead from context switching
5. **What you actually need:**
   - `mpstat -P ALL 1` for per-CPU utilization
   - `cat /proc/pressure/cpu` for CPU pressure
   - D-state count: `ps -eo stat | grep -c D`
   - `vmstat 1` for run queue depth and context switches
6. **Rule of thumb:** Load < cores = generally OK, but only if load is from runnable (not D-state) processes

---

### Q16. If you set a process to nice -20, does it get "all the CPU"?

**Difficulty:** Senior | **Category:** Trick Question

**Answer:**

1. **No.** Nice -20 gives weight 88761 vs. nice 0 weight 1024 (86.7x ratio)
2. With one nice -20 task and one nice 0 task: nice -20 gets `88761/(88761+1024)` = **98.86%**. Nice 0 still gets **1.14%**
3. Nice affects **proportional share** among SCHED_NORMAL tasks only
4. It does NOT provide:
   - Guaranteed CPU time (SCHED_FIFO tasks still preempt it)
   - Exclusive CPU access (other tasks get their proportional share)
   - I/O priority benefit (nice does not affect I/O scheduling -- use `ionice` for that)
   - Memory allocation priority
5. For "all the CPU": use SCHED_FIFO at priority 99 (dangerous), or `cpuset` isolation giving exclusive cores

---

### Q17. Can a SCHED_IDLE task starve a SCHED_NORMAL task?

**Difficulty:** Staff | **Category:** Trick Question

**Answer:**

1. **Yes, via priority inversion** -- this surprises most candidates
2. SCHED_IDLE tasks are scheduled by CFS/EEVDF with an extremely low weight (~3 vs. 1024 for nice 0)
3. Under normal conditions, a SCHED_IDLE task gets negligible CPU versus SCHED_NORMAL (weight ratio ~341:1)
4. **However, starvation can occur indirectly:**
   - SCHED_IDLE task holds a kernel lock (mutex, semaphore) that a SCHED_NORMAL task needs
   - The SCHED_IDLE task is rarely scheduled, so the lock is held for a very long time
   - The SCHED_NORMAL task blocks waiting for the lock -- effectively starved
5. **Kernel mitigations:**
   - Priority inheritance (PI) on RT mutexes temporarily boosts the lock holder's priority
   - Not all kernel locks use PI -- regular mutexes and semaphores typically do not
6. **Takeaway:** SCHED_IDLE is not the same as "harmless" -- lock dependencies create transitive scheduling relationships

---

### Q18. Load average is 0.01 on an 8-core machine. Is the system definitely idle?

**Difficulty:** Senior | **Category:** Trick Question

**Answer:**

1. **Not necessarily.** Load average is an exponentially decaying moving average -- a burst that just ended takes time to register
2. Load average only counts R-state and D-state tasks. Tasks in S-state (interruptible sleep) are invisible:
   - Network I/O waits (socket reads) -- not counted
   - Futex waits (lock contention) -- not counted
   - Poll/epoll waits -- not counted
3. A web server handling 10,000 req/sec could show load ~0 if each request completes in microseconds and the event loop uses epoll (thread sleeps in S-state between events)
4. CPU utilization could be 70% while load average is low if work is done in very short bursts by a small number of threads
5. **Conclusion:** Load avg = 0.01 means very few tasks are in R or D state **on average**, but says nothing about instantaneous CPU utilization or total throughput

---

## Bonus Questions

### Q19. Your application runs fine on kernel 6.5 but shows 15% higher tail latency on kernel 6.6. What scheduler change should you investigate?

**Difficulty:** Principal | **Category:** Kernel Upgrade

**Answer:**

1. Kernel 6.6 replaced CFS with the **EEVDF** scheduler -- this is the prime suspect
2. **Key behavioral differences to investigate:**
   - EEVDF removes CFS sleeper fairness heuristics -- waking tasks may no longer get the vruntime boost they depended on
   - EEVDF's eligible-task filtering changes which task runs next compared to CFS's simple leftmost-vruntime selection
   - The `sched_latency_ns` and `sched_min_granularity_ns` tuning knobs were removed or changed
3. **Diagnostic approach:**
   - `perf sched latency --sort max` -- compare scheduling latency distributions between kernels
   - Check if custom `sched_latency_ns` / `sched_min_granularity_ns` values were set (now ignored/removed)
   - Profile with `perf record -g` to see if the latency is actually in the scheduler or elsewhere
4. **Resolution:**
   - Most EEVDF regressions were addressed in follow-up patches (6.6.x, 6.7, 6.8)
   - Ensure running the latest point release of kernel 6.6+
   - Review application's scheduling pattern: if it relied on specific CFS sleeper behavior, it may need adjustment
5. **Broader lesson:** Kernel upgrades can change scheduler behavior even without explicit tuning changes -- always benchmark critical paths before and after

---

### Q20. Explain how cgroups v2 cpu.weight and cpu.max interact. If a cgroup has weight 200 and max "100000 100000", which takes precedence?

**Difficulty:** Staff | **Category:** cgroups

**Answer:**

1. **Both apply simultaneously** -- they are not mutually exclusive
2. **cpu.weight (proportional share):**
   - Only matters when CPUs are contended (all siblings competing)
   - Weight 200 vs. sibling weight 100: gets 2x the share during contention
   - When CPU is free, weight has no effect (cgroup can use all available CPU)
3. **cpu.max (hard cap / bandwidth limit):**
   - Enforced **unconditionally**, even when CPUs are completely idle
   - "100000 100000" = 100ms quota per 100ms period = maximum 1 CPU core
   - Task is throttled when quota is exhausted regardless of idle CPU capacity
4. **Interaction with weight 200 and max "100000 100000":**
   - If CPU is idle: cgroup can use up to 1 core (limited by `cpu.max`), weight is irrelevant
   - If CPU is contended: cgroup gets 2x the proportional share of siblings (from `cpu.weight`), **but** still capped at 1 core (from `cpu.max`)
   - **cpu.max always wins** as the upper bound
5. **Production guidance:**
   - Use `cpu.weight` alone for best-effort proportional sharing (latency-sensitive services)
   - Use `cpu.max` alone for hard isolation (batch jobs, untrusted workloads)
   - Use both for guaranteed minimum share with a hard ceiling (most Kubernetes deployments)

---

### Q21. A developer wants to set their monitoring agent to SCHED_FIFO priority 99 "for reliability." Explain why this is dangerous and propose alternatives.

**Difficulty:** Senior | **Category:** Production Safety

**Answer:**

1. **Why SCHED_FIFO 99 is dangerous:**
   - Priority 99 is the highest user-accessible RT priority
   - SCHED_FIFO has no time slice -- the task runs until it yields, blocks, or is preempted
   - If the agent enters a busy loop (bug, retry storm, memory pressure), it will **starve every other process** on that CPU
   - Starvation victims include: sshd, systemd, database, kernel worker threads at lower priority
   - The RT throttling safety net (`sched_rt_runtime_us`) only reserves 50ms per second -- the agent still gets 95% of the CPU
2. **Real-world consequences:**
   - Can only be recovered via physical console or power cycle if SSH is starved
   - Database fails health checks, gets fenced, causes cascading outage
3. **Alternatives (ordered by recommendation):**
   - `SCHED_NORMAL` with `nice -5` -- gets priority but cannot starve the system
   - `cpu.weight=500` in cgroups -- guaranteed higher share without starvation risk
   - `SCHED_RR` at priority 10-20 with time slice -- RT but with rotation to other RT tasks
   - `SCHED_DEADLINE` with conservative runtime/period -- gets guaranteed bandwidth without monopolizing
4. **If RT is truly needed:**
   - Use the lowest priority that works (not 99)
   - Add `sched_reset_on_fork` flag (children inherit SCHED_NORMAL)
   - Keep `sched_rt_runtime_us=950000` (never disable)
   - Add a self-watchdog that calls `sched_yield()` or exits on timeout

---

> **Total questions:** 21 (4 Conceptual + 5 Scenario + 4 Debugging + 5 Trick + 3 Bonus)
> **Last updated:** 2026-03-24
