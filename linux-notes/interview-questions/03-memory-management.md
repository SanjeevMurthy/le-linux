# Interview Questions: 03 -- Memory Management (Virtual Memory, Page Tables, OOM, NUMA, Swap)

> **Study guide for Senior SRE / Staff+ / Principal Engineer interviews**
> Full topic reference: [memory-management.md](../03-memory-management/memory-management.md)
> Cheatsheet: [03-memory-management.md](../cheatsheets/03-memory-management.md)

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

### Q1. Explain the difference between page cache and buffer cache. Are they the same thing in modern Linux?

**Difficulty:** Senior | **Category:** Memory Internals

**Answer:**

1. **Historical separation (pre-Linux 2.4):**
   - Buffer cache: cached raw disk blocks at block granularity (512 bytes or 1 KiB), indexed by block device + block number
   - Page cache: cached file data at page granularity (4 KiB), indexed by inode + file offset
   - Problem: the same data could be cached in both, wasting RAM and creating coherence issues

2. **Unification (Linux 2.4+):**
   - The page cache became the single primary cache for all file I/O
   - Buffer heads (`struct buffer_head`) still exist but now point into page cache pages
   - A "buffer" is a view into a page cache page that tracks the disk block mapping for that page

3. **What the fields mean in `/proc/meminfo` today:**
   - `Cached` = file-backed pages in the page cache (most of the "cache")
   - `Buffers` = pages tracking raw block device metadata (filesystem superblocks, journal blocks, inode tables)
   - Both are reclaimable under memory pressure

4. **The practical answer:**
   - They are effectively the same subsystem in modern Linux
   - `free` combines them into a single `buff/cache` column because the distinction is academic
   - The key insight: all are reclaimable memory that the kernel uses to speed up I/O

---

### Q2. What happens when a process calls malloc(1 GiB) on a system with only 512 MiB of free RAM? Walk through each step.

**Difficulty:** Staff | **Category:** Virtual Memory

**Answer:**

1. `malloc()` in glibc calls `mmap(NULL, 1GiB, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0)` for large allocations (threshold: `MMAP_THRESHOLD`, default 128 KiB)

2. The kernel creates a `vm_area_struct` (VMA) describing the new virtual mapping in the process's `mm_struct`

3. **No physical pages are allocated at this point.** The kernel only updates virtual address space metadata. `Committed_AS` in `/proc/meminfo` increases by 1 GiB.

4. **Overcommit check depends on `vm.overcommit_memory`:**
   - Mode 0 (heuristic): kernel checks if the request is "reasonable" relative to free + reclaimable memory. Likely succeeds.
   - Mode 1 (always): succeeds unconditionally
   - Mode 2 (strict): fails if `Committed_AS + 1 GiB > CommitLimit`. Returns `MAP_FAILED` / `NULL`.

5. When the process first touches a page within the allocation:
   - CPU raises a page fault (PTE is not present)
   - Kernel confirms the address falls within a valid VMA
   - Allocates a zeroed physical page from the buddy allocator
   - Installs PTE mapping the virtual address to the new physical page
   - This is a **minor fault** -- no disk I/O

6. If physical memory is exhausted during demand paging:
   - kswapd or direct reclaim attempts to free pages (reclaim page cache, swap anonymous pages)
   - If reclaim fails, OOM killer is invoked
   - The process may be killed (depending on `oom_score`) even though `malloc()` succeeded

7. **Key insight:** `malloc()` success does NOT guarantee the memory is available. This is the overcommit contract.

---

### Q3. Explain the relationship between RSS, VSZ, PSS, and USS. Which metric should you use for capacity planning?

**Difficulty:** Senior | **Category:** Memory Metrics

**Answer:**

1. **VSZ (Virtual Size):**
   - Total virtual address space mapped (includes all regions: heap, stack, mmap, shared libs, unmapped pages)
   - Includes memory never actually touched (demand paging means VSZ >> physical usage)
   - Nearly useless for capacity planning on 64-bit systems

2. **RSS (Resident Set Size):**
   - Physical memory currently mapped in the process's page tables
   - Includes shared library pages and shared memory segments
   - **Double-counting problem:** if 100 processes share a 50 MiB libc, each process's RSS includes that 50 MiB

3. **PSS (Proportional Set Size):**
   - Like RSS, but shared pages are divided by the number of sharers
   - If 100 processes share 50 MiB libc, each gets credited 0.5 MiB
   - **Sum of all PSS across all processes approximates total physical memory used**
   - Read from `/proc/<PID>/smaps_rollup`

4. **USS (Unique Set Size):**
   - Only private pages belonging exclusively to this process
   - Equals `Private_Clean + Private_Dirty` in smaps_rollup
   - This is exactly the memory freed if the process is killed

5. **Recommendations:**
   - **Capacity planning:** Use PSS (it correctly accounts for sharing)
   - **"What happens if I kill this process?":** Use USS
   - **Quick operational triage:** RSS is sufficient (fast, available in `ps`)
   - **Never use VSZ** for memory capacity analysis

---

### Q4. How does Copy-on-Write work at the page table level during fork()? Why is this important for Redis and PostgreSQL?

**Difficulty:** Staff | **Category:** Virtual Memory / Production

**Answer:**

1. **fork() mechanics:**
   - Kernel creates a new `task_struct` and `mm_struct` for the child
   - Parent's page tables are copied (not the physical pages)
   - Both parent and child PTEs point to the same physical page frames
   - All shared pages are marked **read-only** in both processes' PTEs
   - Physical page reference counts are incremented

2. **When either process writes:**
   - CPU raises a page fault (write to read-only page)
   - Kernel checks the page's reference count (`_refcount` in `struct page`)
   - If refcount > 1: allocates a new page, copies 4 KiB (or 2 MiB with THP), updates the writer's PTE to point to the new page with write permission, decrements old page's refcount
   - If refcount == 1: simply marks the page writable (last reference, no copy needed)

3. **Redis BGSAVE impact:**
   - Redis calls `fork()` for background RDB persistence
   - Child reads all data and writes the dump file; parent continues serving writes
   - Every write by the parent to a COW page triggers a page copy
   - Worst case: write-heavy workload copies most of memory during BGSAVE
   - **With THP:** COW copies 2 MiB per write instead of 4 KiB (512x amplification)
   - Monitor: `rdb_last_cow_size` in `redis-cli INFO persistence`

4. **PostgreSQL implications:**
   - Each client connection is a separate process (multiprocess model via `fork()`)
   - Shared buffers are COW-shared across connections
   - `fork()` itself is fast (just page table copy)
   - Memory grows as connections modify their own pages over time

5. **Key production concern:** Always account for COW overhead in capacity planning. A Redis instance with 30 GiB RSS may need 60 GiB during BGSAVE on a write-heavy workload.

---

### Q5. Describe the x86_64 page table hierarchy. What are 5-level page tables and why were they added?

**Difficulty:** Staff | **Category:** Kernel Internals

**Answer:**

1. **4-level hierarchy (standard x86_64, 48-bit VA):**
   - PGD (Page Global Directory): bits [47:39], 512 entries, each maps 512 GiB
   - PUD (Page Upper Directory): bits [38:30], 512 entries, each maps 1 GiB
   - PMD (Page Middle Directory): bits [29:21], 512 entries, each maps 2 MiB
   - PTE (Page Table Entry): bits [20:12], 512 entries, each maps 4 KiB
   - Offset: bits [11:0], byte within page

2. **Physical structure:**
   - Each table is exactly one 4 KiB page (512 entries x 8 bytes)
   - CR3 register holds the physical address of the PGD, reloaded on context switch
   - TLB caches recent translations to avoid the 4-level walk on every memory access

3. **Huge pages terminate the walk early:**
   - 2 MiB huge page: walk stops at PMD (bits [20:0] are the offset)
   - 1 GiB huge page: walk stops at PUD (bits [29:0] are the offset)
   - Fewer TLB entries needed = fewer TLB misses = better performance for large datasets

4. **5-level page tables (kernel 4.14+, `CONFIG_X86_5LEVEL`):**
   - P4D level inserted between PGD and PUD
   - Extends virtual addressing from 48 bits (256 TiB) to 57 bits (128 PiB)
   - Driven by Intel hardware support (Ice Lake+) for larger physical memory
   - Applications needing >128 TiB of virtual address space (large databases, HPC)
   - Backwards compatible: on hardware without 5-level support, the P4D level is folded away at compile time

---

## Category 2: Scenario-Based Questions

### Q6. A production server shows 0% free memory in monitoring but no alerts from the application. The SRE team wants to add more RAM. How do you assess the situation?

**Difficulty:** Senior | **Category:** Operational

**Answer:**

1. **Do NOT trust "free" memory as an indicator.** Linux intentionally uses free RAM for page cache.

2. **Check `free -h`:** Focus on the `available` column, not `free`
   - If `available` > 20% of total: system is healthy, recommend NOT adding RAM
   - If `available` < 10%: investigate further

3. **Verify with `/proc/meminfo`:**
   - `Cached + Buffers + SReclaimable`: this is reclaimable memory being used as cache
   - `AnonPages`: actual process memory consumption
   - `SwapFree` vs `SwapTotal`: any active swapping?

4. **Check for active memory pressure with `vmstat 1`:**
   - `si` and `so` columns: if both are 0, no swapping is occurring
   - `b` column: blocked processes waiting for I/O (swap-related)

5. **Check `/proc/vmstat` for reclaim indicators:**
   - `pgscan_direct`: if increasing, processes are stalling on memory allocation
   - `pgmajfault` rate: if > 100/sec, real pressure exists

6. **Check PSI (kernel 4.20+):**
   - `cat /proc/pressure/memory`: `some` > 0 means at least one task is stalled

7. **Recommendation:**
   - Fix the monitoring to use `MemAvailable` instead of `MemFree`
   - Only add RAM if `MemAvailable` is consistently low AND swap activity is present
   - Document that low `MemFree` is Linux working as designed

---

### Q7. You SSH into a server and it takes 45 seconds to get a shell. Once logged in, commands are slow. What is your memory-related debugging approach?

**Difficulty:** Staff | **Category:** Debugging

**Answer:**

1. **SSH slowness strongly suggests swap thrashing or extreme memory pressure:**
   - sshd needs to allocate memory; under direct reclaim, even small allocations block
   - PAM authentication may fork() processes, which requires page table allocation

2. **First commands once shell is available:**
   ```bash
   vmstat 1 5        # si/so, b (blocked), wa (I/O wait)
   free -h           # Check available and swap usage
   ```

3. **Analyze vmstat output:**
   - `si > 0` + `so > 0`: bidirectional swapping = thrashing
   - `b > 10`: many processes blocked on I/O (likely swap)
   - `wa > 50%`: CPU mostly waiting for disk I/O

4. **Identify the offender:**
   ```bash
   ps aux --sort=-rss | head -10    # Top RSS consumers
   dmesg | tail -50                  # Check for OOM kills
   ```

5. **Check overcommit state:**
   - `grep Committed /proc/meminfo`: is `Committed_AS` >> `CommitLimit`?

6. **Emergency triage:**
   - Kill the largest non-critical process: `kill -9 <PID>`
   - Free page cache: `echo 1 > /proc/sys/vm/drop_caches`
   - If swap device is the bottleneck: consider `swapoff -a` (only if enough RAM after killing processes)

7. **Root cause investigation (post-recovery):**
   - Was there a memory leak? (check historical metrics)
   - Missing cgroup limits? (kubectl describe pod)
   - Insufficient capacity? (AnonPages growing steadily)

8. **Prevention:**
   - Increase `min_free_kbytes` and `watermark_scale_factor` to trigger earlier reclaim
   - Deploy earlyoom as a safety net
   - Set memory cgroup limits on all workloads

---

### Q8. A container running with memory.max=4G is being OOM-killed, but the application inside reports using only 2 GiB of heap. What is consuming the other 2 GiB?

**Difficulty:** Staff | **Category:** Containers / Cgroups

**Answer:**

1. **Cgroup `memory.max` counts ALL memory charged to the cgroup, not just heap:**
   - Anonymous pages (heap, stack, mmap anonymous)
   - Page cache for files opened by processes in this cgroup
   - Slab objects allocated on behalf of cgroup processes (dentries, inodes)
   - Tmpfs/shared memory pages
   - Kernel stack pages for threads
   - Socket buffers (TCP receive/send buffers)

2. **Investigation steps:**
   ```bash
   cat /sys/fs/cgroup/<path>/memory.stat
   ```
   Key fields:
   - `anon`: anonymous pages (~2 GiB matching heap)
   - `file`: page cache charged to cgroup (likely the "missing" memory)
   - `slab_reclaimable` + `slab_unreclaimable`: kernel objects
   - `kernel_stack`: kernel stacks for all threads
   - `sock`: socket buffer memory

3. **Common culprits:**
   - **Log files:** Application writes extensive logs; page cache for those files is charged to the cgroup
   - **Data file reads:** Reading large CSVs, ML models, etc. creates page cache entries
   - **Many small files:** dentry/inode slab cache grows proportionally
   - **TCP connections:** Each TCP socket has send/receive buffers (default: up to 6 MiB per socket)

4. **Solutions:**
   - Set `memory.high` to 3.5G (applies back-pressure before hard OOM)
   - Use `posix_fadvise(POSIX_FADV_DONTNEED)` after one-time file reads
   - Increase memory limit to account for page cache needs
   - Reduce log verbosity or stream logs out of the container
   - Tune TCP buffer sizes if network-heavy: `sysctl net.ipv4.tcp_rmem`

---

### Q9. Your team runs a service on NUMA-aware hardware. After a kernel upgrade, P99 latency doubles. Memory usage and CPU usage appear unchanged. Where do you look?

**Difficulty:** Principal | **Category:** NUMA / Performance

**Answer:**

1. **Check NUMA balancing behavior change:**
   ```bash
   sysctl kernel.numa_balancing
   ```
   - If changed from 0 to 1: kernel now automatically migrates pages between NUMA nodes
   - Page migration during access can cause latency spikes as pages are moved
   - If changed from 1 to 0: pages stay where initially allocated, possibly on remote nodes

2. **Check NUMA stats for imbalance:**
   ```bash
   numastat -m          # Per-node memory distribution
   numastat -p <PID>    # Per-process NUMA placement
   ```
   - Compare `numa_miss` / `numa_hit` ratio before and after upgrade

3. **Check if scheduler topology detection changed:**
   ```bash
   lscpu                # Verify NUMA node / core mapping
   ```
   - New kernel might detect different LLC (Last Level Cache) domains
   - Changed topology affects thread migration decisions

4. **Check THP and compaction behavior:**
   ```bash
   grep -E "compact_stall|thp_" /proc/vmstat
   ```
   - New kernel may have different THP defaults or more aggressive compaction

5. **Check memory reclaim parameters:**
   - Watermark calculations may differ between kernel versions
   - kswapd behavior evolves between kernels

6. **Check numactl settings survived the upgrade:**
   - Verify systemd unit files still have correct `ExecStart` with `numactl`
   - New kernel may ignore some older numactl flags

7. **Hardware-level verification:**
   ```bash
   perf stat -e cache-misses,cache-references,node-loads,node-load-misses -p <PID> -- sleep 10
   ```
   - Increased `node-load-misses` confirms cross-NUMA access pattern change

---

## Category 3: Debugging Questions

### Q10. How do you determine whether a system is experiencing memory pressure vs. healthy page cache usage?

**Difficulty:** Senior | **Category:** Monitoring

**Answer:**

1. **Healthy state (no action needed):**
   - `MemAvailable` > 15-20% of `MemTotal`
   - `vmstat` shows `si` = `so` = 0
   - `/proc/vmstat` `pgmajfault` rate < 10/sec
   - `pgscan_direct` in `/proc/vmstat` not increasing
   - Large `Cached` in `/proc/meminfo` = working as intended

2. **Memory pressure (investigate):**
   - `MemAvailable` < 5% of `MemTotal`
   - `vmstat` shows `so > 0` sustained
   - `pgmajfault` rate > 100/sec
   - `pgscan_direct` increasing (processes forced to reclaim synchronously)
   - `allocstall_normal` in `/proc/vmstat` increasing
   - `kswapd` visible in `top` consuming CPU

3. **Definitive pressure indicator:**
   - PSI (Pressure Stall Information), kernel 4.20+:
     ```bash
     cat /proc/pressure/memory
     some avg10=2.50 avg60=1.80 avg300=0.95 total=45678901
     full avg10=0.50 avg60=0.30 avg300=0.10 total=1234567
     ```
   - `some > 0`: at least one task stalled on memory at some point
   - `full > 0`: ALL tasks stalled (severe -- system is nearly halted)

4. **Decision rule:** `pgscan_direct > 0 AND MemAvailable < 10%` = real pressure

---

### Q11. A process is consuming 50 GiB of RSS but you cannot find the memory in its heap or mapped files. How do you investigate?

**Difficulty:** Principal | **Category:** Advanced Debugging

**Answer:**

1. **Get per-mapping breakdown:**
   ```bash
   cat /proc/<PID>/smaps | awk '/^[0-9a-f]/{region=$0} /^Rss:/{if($2>10240) print $2, region}' | sort -rn | head -20
   ```
   - Identify the largest individual mappings

2. **Check for large anonymous mappings (no file path):**
   - These come from `mmap(MAP_ANONYMOUS)` -- JNI allocations, custom allocators, Go runtime arenas
   - Not tracked by JVM heap metrics or application memory profilers

3. **Check glibc malloc arena fragmentation:**
   - glibc `malloc` uses multiple arenas (one per thread by default)
   - Freed memory may not be returned to OS (`MALLOC_TRIM_THRESHOLD_`)
   - `[heap]` region in maps can be much larger than live allocations
   - Fix: set `MALLOC_ARENA_MAX=2` or switch to jemalloc/tcmalloc

4. **Check for shared memory segments:**
   ```bash
   ipcs -m                          # System V shared memory
   ls -la /dev/shm/                  # POSIX shared memory
   grep -E "shm|SYSV" /proc/<PID>/maps
   ```

5. **For JVM processes specifically:**
   - Off-heap memory: `DirectByteBuffer`, `Unsafe.allocateMemory()`, JNI native allocations
   - Metaspace: class metadata (can grow unbounded without `-XX:MaxMetaspaceSize`)
   - Code cache: JIT compiled native code
   - Thread stacks: each thread uses 1 MiB by default
   - Use `jcmd <PID> VM.native_memory summary` if NativeMemoryTracking is enabled

6. **Use eBPF to trace allocation source:**
   ```bash
   sudo memleak -p <PID> --top 10 -a
   ```
   - Shows outstanding allocations with stack traces

7. **Use `pmap -x <PID>`** for a cleaner view than raw `/proc/<PID>/smaps`

---

### Q12. How do you investigate a suspected kernel slab memory leak?

**Difficulty:** Staff | **Category:** Kernel Debugging

**Answer:**

1. **Confirm slab growth:**
   ```bash
   watch -d -n 60 'grep -E "^(Slab|SReclaimable|SUnreclaim)" /proc/meminfo'
   ```
   - `SUnreclaim` steadily increasing without plateau = strong leak indicator

2. **Identify which slab cache is growing:**
   ```bash
   watch -d -n 30 'slabtop -o -s c | head -20'
   ```
   - Note which cache shows increasing `ACTIVE OBJS` and `CACHE SIZE`

3. **Attempt reclaim first (rule out aggressive caching):**
   ```bash
   echo 2 > /proc/sys/vm/drop_caches    # Force dentry/inode reclaim
   ```
   - If `SUnreclaim` drops: not a leak, just caching
   - If `SUnreclaim` unchanged: true leak in non-reclaimable slabs

4. **Common leak patterns:**
   - `dentry` growing without file operations: filesystem driver bug
   - `kmalloc-*` growing: generic kernel allocation leak
   - `sk_buff`, `tcp_sock` growing: network driver or netfilter leak
   - `task_struct` growing: zombie process accumulation

5. **Enable kernel memory leak detector:**
   ```bash
   echo scan > /sys/kernel/debug/kmemleak
   cat /sys/kernel/debug/kmemleak
   ```
   - Requires `kmemleak=on` boot parameter and `CONFIG_DEBUG_KMEMLEAK`

6. **Check kernel version** against known slab leak CVEs and bug reports

7. **Last resort:** trace with ftrace:
   ```bash
   echo 1 > /sys/kernel/debug/tracing/events/kmem/kmem_cache_alloc/enable
   ```

---

### Q13. Explain how to use /proc/buddyinfo and /proc/pagetypeinfo to diagnose memory fragmentation.

**Difficulty:** Staff | **Category:** Kernel Internals

**Answer:**

1. **Reading `/proc/buddyinfo`:**
   ```
   Node 0, zone   Normal  4096  2048  1024  512  256  128  64  32  16  8  4
   ```
   - Each column = free blocks of order 0, 1, 2, ..., 10
   - Order N = 2^N contiguous pages = 2^N * 4 KiB
   - Column 0: free 4 KiB pages, Column 10: free 4 MiB blocks

2. **Healthy vs. fragmented:**
   - Healthy: reasonable counts across all orders (especially order 4-9)
   - Fragmented: high counts at order 0-2, zero at order 4+
   - Why it matters: huge page allocation (order 9) needs 512 contiguous pages

3. **`/proc/pagetypeinfo` adds mobility classification:**
   - `Unmovable`: kernel allocations (cannot be migrated for compaction)
   - `Movable`: user-space pages (can be migrated to create contiguous blocks)
   - `Reclaimable`: page cache (can be dropped to free memory)
   - High `Unmovable` fragmentation is the hardest to resolve

4. **When fragmentation causes problems:**
   - THP allocation failures: `thp_fault_fallback` in `/proc/vmstat` increasing
   - `compact_stall` increasing: processes blocking during compaction
   - High-order allocation failures in dmesg

5. **Mitigation:**
   - Trigger compaction: `echo 1 > /proc/sys/vm/compact_memory`
   - Increase `min_free_kbytes` to reserve more contiguous memory
   - Use explicit huge page reservation (`vm.nr_hugepages`) instead of THP
   - Long-term: increase `watermark_scale_factor` to keep more free memory

---

## Category 4: Trick Questions

### Q14. Is it possible for a Linux system to run out of memory even when /proc/meminfo shows significant MemFree?

**Difficulty:** Staff | **Category:** Trick

**Answer:**

1. **Yes, several scenarios make this possible:**

2. **Zone exhaustion:**
   - Free memory may be in `ZONE_NORMAL` (above 4 GiB) but the allocation requires `ZONE_DMA32` (below 4 GiB)
   - The kernel cannot use higher-zone memory for lower-zone requirements
   - Check per-zone free memory: `/proc/zoneinfo`

3. **External fragmentation:**
   - Total free pages may be sufficient but scattered across non-contiguous locations
   - A high-order allocation (e.g., order 9 for 2 MiB huge page) needs 512 contiguous pages
   - Check `/proc/buddyinfo` for zero counts at higher orders

4. **NUMA constraints:**
   - Free memory on node 1 but `membind` policy restricts allocation to node 0
   - `numastat` shows imbalanced free memory across nodes

5. **Cgroup memory limits:**
   - Process's cgroup may have reached `memory.max` even though the host has free RAM
   - OOM kill is cgroup-scoped, not system-scoped

6. **`vm.overcommit_memory=2` limit:**
   - `Committed_AS` may have reached `CommitLimit`
   - Prevents new virtual memory allocations despite physical availability
   - `CommitLimit = SwapTotal + (MemTotal * overcommit_ratio / 100)`

7. **Key takeaway:** Memory availability is not a single number. It depends on zone, NUMA node, cgroup, fragmentation state, and overcommit policy.

---

### Q15. A process has 20 GiB VSZ and 50 MiB RSS. Is this process consuming excessive memory?

**Difficulty:** Senior | **Category:** Trick

**Answer:**

1. **Almost certainly not excessive.** The 20 GiB VSZ costs effectively nothing.

2. **What VSZ includes (but does not physically consume):**
   - Memory-mapped files not yet faulted in (demand paging)
   - JVM reserved but uncommitted heap space (`-Xmx` vs actual live objects)
   - Go runtime pre-allocated virtual arena
   - Shared library virtual address ranges
   - Stack guard pages (mapped `PROT_NONE`)
   - `MAP_NORESERVE` regions

3. **Physical cost:** Only 50 MiB of actual RAM (RSS) is consumed

4. **Virtual address space on 64-bit is essentially free:**
   - 48-bit VA = 128 TiB available per process
   - The kernel only allocates page table entries for pages actually touched
   - 20 GiB of untouched virtual mappings costs zero physical memory

5. **One exception:** If `vm.overcommit_memory=2`, the 20 GiB counts toward `Committed_AS` and may prevent other allocations even though no physical memory is used

6. **Common examples:** JVM with large `-Xmx`, Go binaries, mmap'd files not yet accessed, VDSO and other kernel-mapped regions

---

### Q16. If you set vm.swappiness=0, does Linux never swap?

**Difficulty:** Senior | **Category:** Trick

**Answer:**

1. **No, `vm.swappiness=0` does NOT disable swapping entirely**

2. **What it does:**
   - Tells the kernel to strongly prefer reclaiming file-backed pages (page cache) over swapping anonymous pages
   - The kernel will exhaust all file-backed page reclaim options before considering swap

3. **When it still swaps:**
   - If the only reclaimable pages are anonymous (no more file cache to reclaim)
   - During direct reclaim as a last resort before triggering OOM killer
   - When memory cgroup limits force anonymous page eviction

4. **Kernel version matters:**
   - Before kernel 3.5: `swappiness=0` more aggressively avoided swapping
   - After kernel 3.5: `swappiness=0` means "minimize but don't eliminate" -- kernel swaps during direct reclaim as last resort

5. **To truly prevent swapping:**
   - `swapoff -a` -- disables swap entirely (no safety net before OOM)
   - `mlock()` / `mlockall()` -- locks specific pages in RAM (per-process)
   - cgroup `memory.swap.max=0` -- prevents swap for specific cgroup

6. **Production recommendation:** Use `swappiness=1` (not 0) for databases. This minimizes swapping while maintaining the kernel's internal distinction between "never swap" and "avoid swapping."

---

### Q17. Does adding more swap space prevent OOM kills?

**Difficulty:** Senior | **Category:** Trick

**Answer:**

1. **Not necessarily, and it can make things worse**

2. **What more swap provides:**
   - Larger buffer between "memory full" and "OOM kill"
   - More time for kswapd to reclaim pages
   - Can prevent OOM for transient memory spikes

3. **What more swap does NOT solve:**
   - A genuine memory leak: the process will eventually consume swap too, just slower
   - The system may become unusably slow before OOM triggers
   - Swap thrashing (heavy `si`/`so`) can make the system effectively dead even though it technically has not OOM'd

4. **The dangerous middle ground:**
   - With too much swap, the system enters a state where it is alive (no OOM kill) but so slow from swap I/O that it is functionally dead
   - SSH may take minutes, health checks time out, but the kernel does not kill anything because there is technically still swap available
   - This "zombie state" is often worse than a clean OOM kill and restart

5. **Better approaches:**
   - Small swap on fast storage (NVMe or zram) as a safety buffer
   - Proper memory limits via cgroups
   - earlyoom or systemd-oomd for proactive killing before kernel OOM
   - Fix the root cause: right-size applications, fix leaks, add RAM

---

## Bonus Questions

### Q18. What is the difference between minor and major page faults, and how do you measure each for a running process?

**Difficulty:** Senior | **Category:** Memory Internals

**Answer:**

1. **Minor fault:**
   - The page is already in physical RAM (just not in this process's page table)
   - Examples: first access to a demand-paged allocation (zeroed page), COW fault, accessing page cache page
   - Cost: ~1-10 microseconds (CPU only, no disk I/O)
   - Indicates: normal operation, new memory allocation

2. **Major fault:**
   - The page must be read from disk (swap or filesystem)
   - Examples: reading swapped-out page, reading file page not in page cache
   - Cost: 1-10+ ms (HDD), 50-200 us (NVMe) -- orders of magnitude slower
   - Indicates: memory pressure (if swap) or cold file access (if file)

3. **Measurement methods:**
   ```bash
   # Per-process from /proc
   cat /proc/<PID>/stat | awk '{print "minflt:", $10, "majflt:", $12}'

   # Per-process snapshot
   ps -o pid,min_flt,maj_flt -p <PID>

   # System-wide rate
   vmstat 1      # Look at 'si' column (major fault proxy for swap)

   # System-wide counters
   grep -E "pgfault|pgmajfault" /proc/vmstat

   # Real-time per-process with perf
   perf stat -e page-faults,major-faults -p <PID> -- sleep 10
   ```

4. **Production alarm:** A sustained major fault rate > 100/sec on a non-I/O-intensive workload indicates memory pressure requiring investigation

---

### Q19. Explain how memory cgroups v2 work. What is the difference between memory.max, memory.high, memory.low, and memory.min?

**Difficulty:** Staff | **Category:** Containers / Cgroups

**Answer:**

1. **`memory.max`** (hard limit):
   - Absolute maximum memory the cgroup can use
   - If exceeded, OOM killer is invoked within the cgroup
   - Equivalent to cgroups v1 `memory.limit_in_bytes`
   - Default: `max` (unlimited)

2. **`memory.high`** (throttle threshold):
   - Soft limit that applies back-pressure when exceeded
   - Kernel throttles allocations in the cgroup (slows them down)
   - Does NOT trigger OOM kill
   - Provides graceful degradation before hitting `memory.max`
   - Best practice: set to expected normal usage

3. **`memory.low`** (best-effort protection):
   - Memory below this threshold is protected from reclaim
   - The kernel prefers to reclaim memory from other cgroups first
   - NOT a guarantee: if system-wide memory is critically low, these pages can still be reclaimed
   - Useful for protecting cache of latency-sensitive services

4. **`memory.min`** (hard protection):
   - Memory below this threshold is NEVER reclaimed, even under system-wide pressure
   - Hard guarantee (unlike `memory.low`)
   - Use sparingly: over-allocating `memory.min` across cgroups can cause system-wide OOM

5. **Recommended production configuration:**
   ```
   memory.min  = 512M       # Absolute minimum (critical data structures)
   memory.low  = 2G         # Protect working set from reclaim
   memory.high = 3.5G       # Throttle before hard limit
   memory.max  = 4G         # Hard OOM boundary
   ```

---

### Q20. What is the relationship between ZONE_DMA, ZONE_DMA32, and ZONE_NORMAL on x86_64? Can a process force allocation from a specific zone?

**Difficulty:** Principal | **Category:** Kernel Internals

**Answer:**

1. **Zone purposes on x86_64:**
   - `ZONE_DMA` (0 - 16 MiB): legacy ISA devices requiring 24-bit addressable DMA
   - `ZONE_DMA32` (16 MiB - 4 GiB): 32-bit PCI devices requiring 32-bit addressable DMA
   - `ZONE_NORMAL` (4 GiB - end of RAM): all general-purpose allocations

2. **Fallback hierarchy:**
   - An allocation requesting `ZONE_NORMAL` can fall back to `ZONE_DMA32` and then `ZONE_DMA`
   - An allocation requesting `ZONE_DMA` can ONLY come from `ZONE_DMA` (no fallback upward)
   - This means DMA zone exhaustion can happen even with plenty of ZONE_NORMAL free memory

3. **User-space perspective:**
   - Normal user-space processes cannot directly request a specific zone
   - `malloc()` / `mmap()` allocations come from whatever zone the buddy allocator provides (usually ZONE_NORMAL on x86_64)
   - Only kernel-space code (drivers) specifies zone via `GFP_DMA` or `GFP_DMA32` flags

4. **Why it matters in production:**
   - Some virtualization backends (e.g., old Xen) require DMA32 memory for device emulation
   - A host with 256 GiB RAM but all 4 GiB of ZONE_DMA32 consumed by balloon driver can fail to allocate for 32-bit DMA devices
   - Monitor per-zone free memory: `cat /proc/zoneinfo | grep -E "Node|zone|free "`

5. **ZONE_HIGHMEM:** Only exists on 32-bit kernels for physical memory above ~896 MiB that cannot be permanently mapped into the kernel's virtual address space. Completely irrelevant on x86_64 -- if this comes up in an interview, it is a trick question.
