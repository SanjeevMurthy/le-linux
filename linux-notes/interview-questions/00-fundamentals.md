# Interview Questions: 00 -- Fundamentals (Boot Process, Kernel Architecture, System Calls)

> **Study guide for Senior SRE / Staff+ / Principal Engineer interviews**
> Full topic reference: [fundamentals.md](../00-fundamentals/fundamentals.md)
> Cheatsheet: [00-fundamentals.md](../cheatsheets/00-fundamentals.md)

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

### Q1. Explain the difference between a monolithic kernel and a microkernel. Why did Linux choose monolithic, and what are the modern mitigations for its downsides?

**Difficulty:** Senior | **Category:** Architecture

**Answer:**

1. **Monolithic architecture:** Linux runs kernel, device drivers, filesystem implementations, and networking stack all in the same address space at Ring 0 privilege level
   - **Risk:** A single bad pointer dereference in any driver can corrupt kernel memory and panic the entire system
2. **Microkernel contrast** (e.g., QNX, seL4, Fuchsia):
   - Only essential services (scheduler, IPC, basic memory management) run in kernel space
   - Drivers, filesystems, and networking run as user-space processes -- a driver crash is isolated
   - **Trade-off:** Every driver interaction requires IPC across address spaces, adding latency
3. **Why Linux chose monolithic:** Direct function calls within the kernel are orders of magnitude faster than cross-process IPC. For a server handling 1M+ network packets per second, this difference is decisive

**Modern mitigations for monolithic downsides:**
1. **Loadable Kernel Modules (LKMs)** -- drivers compiled separately, inserted/removed at runtime via `modprobe` without rebooting
2. **eBPF** -- safe, verified bytecode executed in kernel context without writing actual kernel modules. Enables observability (tracing, profiling) and networking (XDP) without kernel modification
3. **Kernel lockdown mode** -- restricts what even root can do to a running kernel (prevents `/dev/mem` access, unsigned module loading)
4. **KASAN, UBSAN, KCSAN** -- kernel sanitizers that catch memory bugs, undefined behavior, and data races during development
5. **RCU (Read-Copy-Update)** -- lockless synchronization for safe concurrent access to kernel data structures
6. **Kernel live patching** (`kpatch`, Canonical Livepatch) -- patch critical vulnerabilities without rebooting

---

### Q2. What is the vDSO and why does it exist? Name the specific syscalls it accelerates and explain the mechanism.

**Difficulty:** Staff | **Category:** System Calls

**Answer:**

1. **What it is:** A small ELF shared library that the kernel automatically maps into every process's address space, allowing certain system calls to execute entirely in user space
2. **Why it exists:** Avoids the ~50-100 CPU cycle overhead of a Ring 3 to Ring 0 transition
3. **Mechanism:** The kernel maintains shared read-only memory pages with frequently updated data (e.g., current time). The vDSO code reads these pages directly as a normal function call -- no privilege transition. Updated each timer tick.
4. **Accelerated functions on x86_64:**
   - `clock_gettime()` -- the most impactful, used by virtually all latency-sensitive applications
   - `gettimeofday()` -- legacy time function, also accelerated
   - `time()` -- simple epoch time
   - `getcpu()` -- returns current CPU and NUMA node
5. **Scale impact:** A monitoring agent calling `clock_gettime()` millions of times per second gains 10-100x performance vs. trapping into the kernel each time. In HFT, the difference can be hundreds of microseconds per second of cumulative latency.
6. **History:** Before vDSO, `vsyscall` existed at a fixed address -- a security liability (fixed address = predictable ROP gadgets). vDSO is mapped at a random address via ASLR.
7. **Verification:** `ldd /bin/ls | grep vdso` shows `linux-vdso.so.1`. Statically linked applications bypass vDSO and must trap into the kernel for every time-related call.

---

### Q3. Walk through exactly what happens at the CPU level when a user-space process makes a system call on x86_64.

**Difficulty:** Principal | **Category:** System Calls / CPU Architecture

**Answer:**

1. The application calls a glibc wrapper function (e.g., `write(fd, buf, count)`)

2. The glibc wrapper prepares registers:
   - RAX = syscall number (1 for `write` on x86_64)
   - RDI = first argument (fd)
   - RSI = second argument (buf)
   - RDX = third argument (count)
   - R10, R8, R9 for arguments 4-6 if needed

3. The wrapper executes the `syscall` instruction. The CPU hardware then:
   - Saves the return address (RIP) into RCX
   - Saves RFLAGS into R11
   - Loads the kernel entry point from MSR_LSTAR (Model-Specific Register, set during kernel boot to point to `entry_SYSCALL_64`)
   - Loads the kernel code segment selector from MSR_STAR
   - Masks RFLAGS according to MSR_FMASK (crucially, this disables interrupts via the IF flag)
   - Transitions from Ring 3 (user mode) to Ring 0 (kernel mode)

4. Execution arrives at `entry_SYSCALL_64` (in `arch/x86/entry/entry_64.S`):
   - Switches from the user stack to the kernel stack (per-task kernel stack pointer stored in TSS)
   - Saves all user-space registers into a `pt_regs` structure on the kernel stack
   - Re-enables interrupts

5. Dispatches the syscall via `sys_call_table[RAX]`:
   - This is an array of function pointers indexed by syscall number
   - For `write`, dispatches to `ksys_write()`

6. The handler executes:
   - Validates arguments, checks permissions
   - For `write`: traverses VFS -> filesystem-specific write -> possibly block I/O
   - Places return value in RAX (bytes written, or negative errno)

7. Returns via `sysret`:
   - Restores RIP from RCX, RFLAGS from R11
   - Transitions back to Ring 3

8. Back in glibc:
   - Checks if RAX is negative (indicates error)
   - If error: negates the value, stores it in thread-local `errno`, returns -1
   - If success: returns the value directly

**Important edge case:** `sysret` has a known vulnerability on Intel CPUs -- if RCX contains a non-canonical address, `sysret` generates a general protection fault *while still in Ring 0*, which can be exploited. The kernel works around this by checking RCX before using `sysret` and falling back to `iretq` (slower but safe) when necessary.

---

### Q4. What is the difference between the kernel's process and thread representation? How does clone() unify them?

**Difficulty:** Staff | **Category:** Process Management / Kernel Internals

**Answer:**

1. **No separate thread struct:** Both processes and threads are represented by `task_struct` (defined in `include/linux/sched.h`). A thread is simply a `task_struct` that shares resources with other `task_struct`s in the same thread group.

2. **Unifying mechanism -- `clone()` flags:** The `clone()` syscall accepts flags determining which resources are shared vs. copied:

| Flag | Shared Resource | fork() | pthread_create() |
|---|---|---|---|
| `CLONE_VM` | Virtual memory (mm_struct) | No (COW copy) | Yes |
| `CLONE_FILES` | File descriptor table | No (copy) | Yes |
| `CLONE_SIGHAND` | Signal handlers | No (copy) | Yes |
| `CLONE_THREAD` | Thread group ID | No | Yes |
| `CLONE_FS` | Root dir, cwd, umask | No (copy) | Yes |

3. **Process vs. thread:**
   - **Process** = `clone()` with no sharing flags (or `fork()`, which is `clone(SIGCHLD)`)
   - **Thread** = `clone()` with `CLONE_VM|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD|CLONE_FS`

4. **TGID vs PID:**
   - Each `task_struct` has a unique PID (task ID)
   - The TGID (Thread Group ID) equals the PID of the first thread (main thread)
   - `getpid()` returns the TGID (so all threads report the same "process ID")
   - `gettid()` returns the actual task PID (unique per thread)
   - This is why `kill(<PID>)` signals the entire process: it targets the TGID

5. **Scheduling implication:** The kernel schedules individual `task_struct`s (threads), not processes. On a 4-core machine, a multi-threaded process with 4 threads can genuinely run on all 4 cores simultaneously.

---

### Q5. Explain the role of the Memory Management Unit (MMU) and page tables in the context of process isolation.

**Difficulty:** Senior | **Category:** Memory / Architecture

**Answer:**

1. **MMU role:** A hardware component (part of the CPU) that translates virtual addresses (what a process sees) to physical addresses (actual RAM locations). Every memory access goes through the MMU.

2. **Page tables:** Each process has its own set, defining the virtual-to-physical mapping. The kernel loads the top-level page table address into the CR3 register (x86_64) during context switches.

3. **How this enables isolation:**
   - Process A's page tables map virtual address 0x7fff00000000 to physical frame 0x12345000
   - Process B's page tables map the SAME virtual address to a DIFFERENT physical frame 0x67890000
   - Neither process can access the other's physical memory -- their page tables don't contain entries for the other's frames
   - Kernel memory is mapped in every process's page table but with supervisor-only permission bits -- the MMU blocks Ring 3 access

4. **Page table structure on x86_64 (4-level):**
   PGD (Page Global Directory) -> PUD (Page Upper Directory) -> PMD (Page Middle Directory) -> PTE (Page Table Entry) -> Physical Page (4KB default)

5. **Key features:**
   - **Demand paging:** PTEs marked "not present" cause a page fault when accessed; the kernel then allocates a physical page, fills it, and updates the PTE. Enables lazy allocation and swap.
   - **Copy-on-Write (COW):** After `fork()`, parent and child share physical pages with read-only PTEs. Only when one writes does the kernel copy the page -- making `fork()` fast even for large processes.
   - **Huge pages** (2MB or 1GB): reduce TLB misses for workloads with large memory footprints (databases, VMs). Configured via `hugetlbfs` or Transparent Huge Pages.

---

## Category 2: Scenario-Based Questions

### Q6. You perform a kernel upgrade on a production server and it won't boot. Walk through your troubleshooting approach.

**Difficulty:** Senior | **Category:** Boot / Troubleshooting

**Answer:**

**Step 1: Determine where in the boot chain the failure occurs.**

Check serial console output (or IPMI/iLO virtual console):
- No output at all → firmware/hardware issue (unlikely if only kernel changed)
- GRUB menu appears → bootloader is working
- Kernel starts but panics → kernel or initramfs issue
- Kernel starts, systemd hangs → user-space issue

**Step 2: Restore service immediately.**

At the GRUB menu, select the **previous kernel** (kept by package managers for exactly this reason). This gets the server back in service while you investigate.

**Step 3: Investigate the failure from the recovered system.**

```bash
journalctl -b -1 -p err      # Errors from the failed boot
dmesg -T | grep -i panic      # Kernel panic messages
cat /proc/cmdline              # Compare current (working) vs failed boot params
```

**Step 4: Common causes and targeted fixes:**

- **`VFS: Unable to mount root fs`** → initramfs doesn't contain the storage driver for this kernel version. Fix: `update-initramfs -u -k <new-kernel>` or `dracut --force`
- **`Kernel panic - not syncing: VFS`** → wrong root= parameter, or root UUID changed. Fix: verify UUID with `blkid`, update GRUB config
- **Module panic** → incompatible out-of-tree module. Fix: `modprobe.blacklist=<module>` in kernel cmdline, rebuild module for new kernel
- **systemd fails** → a service unit depends on a kernel feature that changed. Fix: `systemd.unit=rescue.target`, then `systemctl --failed`

**Step 5: Prevention for future upgrades:**
- Canary deployment: upgrade 1 node, verify boot, then proceed to fleet
- Automated boot verification: health check within 5 minutes of reboot
- Keep N-2 kernels installed as fallbacks
- Test kernel + initramfs + GRUB config in a VM before production deployment

---

### Q7. A fleet of 10,000 nodes is experiencing 3-minute boot times. Your SLO is 45 seconds. How do you diagnose and fix this?

**Difficulty:** Staff | **Category:** Boot Performance / Fleet Management

**Answer:**

**Phase 1: Data Collection (10 minutes)**

Sample 20 affected nodes across different roles and data centers:

```bash
# On each sampled node:
systemd-analyze                          # Total boot time breakdown
systemd-analyze blame | head -20         # Top 20 slowest units
systemd-analyze critical-chain           # The dependency chain that determines total time
```

Aggregate results. Look for patterns.

**Phase 2: Identify the Bottleneck Class**

Common categories:
1. **Network wait** -- `NetworkManager-wait-online.service` (2-3 minutes): waiting for DHCP response or link detection. Fix: switch to `systemd-networkd` with faster timeout, use static IP assignment, or configure `NM_ONLINE_TIMEOUT=10`.

2. **Filesystem check** -- `systemd-fsck@*.service` (minutes on large partitions): forced fsck after unclean shutdown or after mount-count threshold. Fix: `tune2fs -c 0 -i 0` to disable periodic fsck on data volumes (application manages integrity). Move OS to SSD.

3. **Device wait** -- `dev-*.device` (slow storage detection): multipath path discovery, SAN fabric login, degraded RAID rebuild. Fix: optimize multipath timeout (`fast_io_fail_tmo`, `dev_loss_tmo`), pre-configure RAID.

4. **Dependency cycle** -- `systemd-analyze verify` reports circular dependencies. Fix: refactor unit files to break the cycle.

5. **Slow service start** -- A custom service with long `ExecStartPre` or `Type=oneshot` blocking all dependents. Fix: convert to `Type=simple` or `Type=forking`, move heavy initialization to `ExecStartPost` or a timer.

**Phase 3: Fix and Validate**

Apply fixes to a canary group. Measure before/after with `systemd-analyze`. Roll out to fleet. Set up continuous monitoring: export boot time metric via node_exporter, alert if any node exceeds 2x SLO.

---

### Q8. Describe what happens from power-on to a login prompt at the maximum level of detail.

**Difficulty:** Principal | **Category:** Full Boot Sequence

**Answer:**

(This is the #1 Linux interview question. A principal-level answer should take 3-5 minutes and mention specific files, functions, and data structures.)

**1. Firmware (BIOS/UEFI)**
- CPU executes reset vector at `0xFFFFFFF0` (x86), which jumps to firmware code in ROM/flash
- POST: tests CPU registers, memory controller, RAM (pattern test), enumerates PCI bus, SATA controllers, USB, NIC
- UEFI: reads GPT partition table, identifies EFI System Partition (ESP, FAT32), loads configured EFI application (e.g., `/EFI/ubuntu/grubx64.efi`). If Secure Boot enabled, verifies digital signature before execution
- BIOS: reads first 512 bytes of boot device (MBR), executes the 446-byte boot code

**2. Bootloader (GRUB2)**
- GRUB has its own filesystem drivers (ext4, XFS, btrfs). Reads `/boot/grub/grub.cfg`
- Presents menu (if timeout > 0) or auto-selects default entry
- Loads `vmlinuz` (compressed kernel image) into RAM. On UEFI, also loads via EFISTUB if configured
- Loads `initrd.img`/`initramfs.img` into RAM adjacent to the kernel
- Passes kernel command line (from `grub.cfg`): `root=UUID=... ro quiet console=ttyS0,115200 crashkernel=256M`
- Transfers control to the kernel entry point

**3. Kernel Initialization**
- `start_kernel()` in `init/main.c`: the first C function. Before this, assembly code in `arch/x86/boot/` sets up protected/long mode, decompresses the kernel if compressed
- CPU initialization: identify model, enable features (SSE, AVX), calibrate timers
- Memory: set up initial page tables, initialize the zone allocator (ZONE_DMA, ZONE_NORMAL, ZONE_HIGHMEM on 32-bit), slab allocator for kernel objects
- Scheduler: initialize the CFS (EEVDF in 6.6+), create the idle task
- Interrupts: set up the IDT (Interrupt Descriptor Table), enable APIC, configure timer interrupt (tick)
- Device discovery: ACPI table parsing, PCI bus enumeration, device-driver matching
- Console: early console via serial port (earlycon) for boot debugging
- Mounts the initramfs (gzip-compressed cpio archive) as the initial root filesystem
- Executes `/init` from initramfs (this is the first user-space process, PID 1 temporarily)

**4. initramfs**
- Runs a minimal systemd (in initrd mode) or shell scripts
- `udev` coldplug: creates device nodes in `/dev/` for all detected hardware
- Loads storage drivers: RAID (`md`), LVM (`dm`), LUKS (`dm-crypt`), multipath (`dm-multipath`), NVMe, virtio-blk
- Assembles the root block device (e.g., `mdadm --assemble`, `vgchange -ay`, `cryptsetup luksOpen`)
- Mounts the real root filesystem (read-only) at `/sysroot`
- Executes `switch_root` (or `pivot_root`): replaces initramfs with real rootfs, frees initramfs memory, execs `/sbin/init` on the real rootfs

**5. systemd (PID 1)**
- Reads configuration from `/etc/systemd/system/` and `/usr/lib/systemd/system/`
- Determines default target: `systemctl get-default` (usually `multi-user.target` or `graphical.target`)
- Builds a dependency graph of all required units (services, mounts, sockets, targets)
- Activates units in parallel where dependency ordering allows
- Key early units: `systemd-journald` (logging), `systemd-udevd` (device management), `systemd-tmpfiles-setup` (temp directories), `local-fs.target` (mount filesystems), `network-online.target`
- Remounts root filesystem read-write after fsck
- Starts network configuration, SSH daemon, cron, application services
- Reaches `multi-user.target`
- Spawns `getty` on TTYs (or `agetty` for serial console)

**6. Login**
- `getty` displays the login prompt, reads username
- Passes to `login` (or `sshd` for remote)
- `login` calls PAM (Pluggable Authentication Modules) for authentication
- PAM checks `/etc/passwd`, `/etc/shadow`, optional LDAP/Kerberos backends
- On success: `login` calls `setuid()`, `setgid()`, `initgroups()`, changes to user's home directory, execs the user's shell from `/etc/passwd`
- Shell reads profile files (`/etc/profile`, `~/.bashrc`), displays prompt

---

### Q9. A process is making millions of gettimeofday() calls per second and you need to optimize it. What kernel mechanisms are relevant?

**Difficulty:** Staff | **Category:** Performance / System Calls

**Answer:**

1. **Verify the application uses vDSO:**
   ```bash
   ldd /path/to/application | grep vdso
   # Should show: linux-vdso.so.1 => (0x00007fff...)
   ```
   - If statically linked, it bypasses vDSO and issues a real syscall each time (~50-100 cycles instead of ~5-10)
   - Fix: relink dynamically, or switch to `__vdso_gettimeofday` symbol directly

2. **Check the clocksource:**
   ```bash
   cat /sys/devices/system/clocksource/clocksource0/current_clocksource
   ```
   - `tsc` (Time Stamp Counter) -- fastest, hardware register on the CPU
   - `kvm-clock` -- fast, appropriate for KVM guests
   - `hpet` -- slow (requires MMIO read), sometimes used as fallback
   - `acpi_pm` -- slowest
   - If `hpet` or `acpi_pm`, fix: `echo tsc > /sys/devices/system/clocksource/clocksource0/current_clocksource` (if TSC is stable)

3. **Consider precision trade-offs:**
   - If nanosecond precision is not needed, switch from `CLOCK_MONOTONIC` to `CLOCK_MONOTONIC_COARSE` (or `CLOCK_REALTIME_COARSE`)
   - `_COARSE` variants read a cached value without hardware access -- kernel's tick-based approximation

4. **Application-level optimization:**
   - Cache the timestamp and reuse within a batch of operations
   - Most applications don't need a unique timestamp per operation -- one per batch of 100-1000 is sufficient

---

## Category 3: Debugging Questions

### Q10. `dmesg` shows "Out of memory: Kill process 1234 (java)". Explain the full chain of events and how you investigate.

**Difficulty:** Senior | **Category:** Memory / Kernel

**Answer:**

**Chain of events:**
1. A process (or the kernel itself) requested a memory allocation via `alloc_pages()` or `kmalloc()`
2. The page allocator could not find free pages in the requested zone
3. The kernel tried reclaiming memory: flushing dirty pages, shrinking page cache, compacting memory
4. Reclamation was insufficient (or the allocation was GFP_ATOMIC, which can't sleep/reclaim)
5. The OOM killer was invoked (`out_of_memory()` in `mm/oom_kill.c`)
6. It calculated a "badness score" (`oom_badness()`) for each eligible process, considering:
   - RSS (Resident Set Size) -- proportional to memory consumed
   - `oom_score_adj` (tunable per-process via `/proc/<PID>/oom_score_adj`, range -1000 to 1000)
   - Root processes get a slight discount (3% of RAM)
7. The process with the highest score was selected (java, PID 1234)
8. The kernel sent SIGKILL to the selected process and all threads in its thread group
9. The kill was logged to the kernel ring buffer with details

**Investigation steps:**

```bash
# Check the full OOM kill message (includes memory breakdown):
dmesg -T | grep -A 30 "Out of memory"
# Look for: total memory, free, cached, swap, per-zone breakdown, top consumers

# Check current memory state:
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Cached|SwapTotal|SwapFree"

# Check if memory cgroups imposed a limit:
cat /sys/fs/cgroup/memory/<group>/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/<group>/memory.usage_in_bytes

# Check OOM score for surviving processes:
for pid in $(pgrep -f important); do
    echo "$pid: $(cat /proc/$pid/oom_score) adj=$(cat /proc/$pid/oom_score_adj)"
done

# Protect critical processes from OOM:
echo -1000 > /proc/<critical_PID>/oom_score_adj  # Never OOM-kill this process
```

**Prevention:**
- Set `vm.overcommit_memory=2` with `vm.overcommit_ratio=80` for strict memory accounting (prevents over-commitment)
- Use memory cgroups to limit per-service memory consumption
- Set `oom_score_adj=-1000` for critical services (database, init)
- Monitor memory usage trends; alert at 85% utilization
- Ensure adequate swap (debate: some FAANG shops run swapless for predictable latency; others keep small swap for safety)

---

### Q11. A node shows "hung_task_timeout_secs" warnings in dmesg. What does this indicate and how do you debug it?

**Difficulty:** Staff | **Category:** Kernel / I/O

**Answer:**

**What it indicates:**
- The kernel's hung task detector (`kernel/hung_task.c`) found a task in `TASK_UNINTERRUPTIBLE` (D-state) for longer than `kernel.hung_task_timeout_secs` (default: 120 seconds)
- D-state means the process is waiting on I/O or a kernel lock and **cannot be interrupted** -- even `SIGKILL` is ignored

**Common causes:**
1. **Failed/slow disk** -- I/O submitted but never completed
2. **Unreachable NFS server** -- NFS mounts are "hard" by default; client waits forever
3. **iSCSI/SAN timeout** -- fabric disruption, path failure
4. **Kernel lock contention** -- a mutex held by another stuck task
5. **Deadlock** -- two tasks waiting for each other's locks

**Debugging steps:**

```bash
# Find D-state processes:
ps aux | awk '$8 ~ /D/ {print}'

# Get the kernel stack trace of the stuck process:
cat /proc/<PID>/stack
# Example output showing NFS wait:
# [<0>] rpc_wait_bit_killable+0x24/0x90
# [<0>] __rpc_execute+0x190/0x360
# [<0>] nfs4_do_call_sync+0x5c/0x80
# [<0>] nfs4_proc_getattr+0x73/0x90

# Check I/O health:
iostat -x 1 5                            # Look for 100% util, high await
cat /proc/mdstat                         # RAID status
multipath -ll                            # Multipath status
mount | grep nfs                         # NFS mounts
showmount -e <nfs-server>               # NFS server accessibility

# Check for general I/O stalls:
cat /proc/diskstats | awk '{if ($4+$8 > 0) print $3, "inflight:", $12}'
```

**Resolution:**
- NFS: add `soft,timeo=300,retrans=3` mount options so NFS operations fail instead of blocking forever
- Disk: replace failed disk, check RAID health
- SAN: verify fabric connectivity, check multipath failover
- Contention: identify lock holder via `crash` utility or `/proc/lock_stat` (if enabled)

---

### Q12. After a reboot, `systemd-analyze` shows userspace took 90 seconds. Your normal baseline is 15 seconds. How do you find the bottleneck?

**Difficulty:** Senior | **Category:** Boot Performance / systemd

**Answer:**

```bash
# Step 1: Find the critical path (not just the slowest unit)
systemd-analyze critical-chain
# This shows the DEPENDENCY CHAIN that determined total boot time.
# A unit taking 60s doesn't matter if nothing depends on it.
# A unit taking 10s that blocks 20 other units IS the bottleneck.

# Step 2: Find the slowest individual units
systemd-analyze blame | head -20

# Step 3: Check for dependency cycles
systemd-analyze verify default.target 2>&1 | grep -i cycle

# Step 4: Check for unit-file errors
systemd-analyze verify *.service 2>&1 | grep -i error

# Step 5: Compare with a normal boot
# If you have journald persistent storage:
journalctl --list-boots
# Compare timestamps of key units between normal and slow boot
```

**Common bottleneck patterns:**

1. **Single slow unit blocking chain:** A `Type=oneshot` unit with a slow `ExecStartPre` command (e.g., a health check that times out). Dependents cannot start until it finishes. Fix: increase parallelism, convert to `Type=simple`, or move the slow operation to `ExecStartPost`.

2. **Device wait:** `dev-sda.device` or similar taking minutes. Indicates slow storage detection (SAN login, RAID rebuild, missing multipath path). Fix: check hardware, tune multipath timeouts.

3. **Network wait:** `NetworkManager-wait-online.service` or `systemd-networkd-wait-online.service`. Fix: reduce timeout (`NM_ONLINE_TIMEOUT=15`), ensure DHCP server is fast, consider static IP.

4. **Filesystem check:** `systemd-fsck@dev-*.service` running full fsck on large partitions. Fix: `tune2fs -c 0 -i 0` on non-critical partitions, move to XFS (faster journal replay).

5. **Random entropy wait:** `systemd-random-seed.service` or services needing `/dev/random`. Fix: install `haveged` or `rng-tools` to provide entropy, or use `virtio-rng` in VMs.

---

### Q13. How would you determine if a performance issue is caused by excessive system calls?

**Difficulty:** Senior | **Category:** Performance / Tracing

**Answer:**

**Layer 1: Quick assessment with strace (higher overhead, good for short runs):**

```bash
strace -c -p <PID>
# Press Ctrl+C after 10 seconds
# Output shows syscall count, total time, errors per syscall type
```

If a single syscall type dominates (e.g., 500,000 `futex` calls in 10 seconds), that is your suspect.

**Layer 2: Lower-overhead tracing with perf:**

```bash
perf stat -e 'syscalls:sys_enter_*' -p <PID> -- sleep 10
# Shows count of each syscall type with minimal overhead

perf trace -p <PID> --duration 100
# Like strace but using perf events (not ptrace), much lower overhead
# --duration 100 shows only syscalls taking >100ms
```

**Layer 3: eBPF-based tools (production-safe, lowest overhead):**

```bash
# Using bcc tools:
syscount-bpfcc -p <PID> -d 10           # Syscall counts over 10 seconds
syscount-bpfcc -p <PID> -L              # Include per-syscall latency

# Using bpftrace:
bpftrace -e 'tracepoint:raw_syscalls:sys_enter /pid == <PID>/ { @[comm] = count(); }'
```

**Interpretation guidelines:**
- A web server doing 50,000 `epoll_wait` calls/second: **normal** (event-driven I/O)
- Same server doing 50,000 `open`/`close` cycles/second: **abnormal** (not caching file descriptors)
- An application doing 1M+ `clock_gettime` calls/second: check if vDSO is being used; if yes, these don't actually enter the kernel and aren't a problem
- Thousands of `futex` calls: likely lock contention in a multi-threaded application

---

## Category 4: Trick Questions

### Q14. Does Linux load average include processes waiting for I/O? How is this different from other Unix systems?

**Difficulty:** Senior | **Category:** Metrics / Misconceptions

**Answer:**

1. **Yes** -- Linux load average includes both `TASK_RUNNING` (on CPU or in run queue) and `TASK_UNINTERRUPTIBLE` (D-state, typically waiting for I/O) processes. This was a deliberate change made in a 1993 kernel patch.
2. **Different from other Unixes:** Solaris, FreeBSD, and macOS count only runnable processes.
3. **Why this matters:** A load average of 8 on an 8-core machine does NOT necessarily mean CPU saturation. It could mean:
   - 8 processes running on CPU (CPU saturated, I/O fine)
   - 8 processes blocked in D-state waiting for I/O (CPU idle, I/O bottleneck)
   - 4 CPU-bound + 4 I/O-blocked (mixed)

**How to distinguish:**

```bash
# CPU utilization (actual CPU usage):
mpstat -P ALL 1        # %usr + %sys = CPU busy. %idle > 50% = not CPU-saturated

# I/O wait:
vmstat 1               # 'wa' column = I/O wait percentage
iostat -x 1            # %util per device, await = average I/O latency

# D-state process count:
ps aux | awk '$8 ~ /D/ {count++} END {print count}'
```

**Interview trap:** If an interviewer asks "the load average is 16 on a 16-core server, is it overloaded?" the correct answer is "I need more data" -- specifically, CPU utilization and I/O wait. Load average alone on Linux is ambiguous.

---

### Q15. Is `init=/bin/bash` a security vulnerability?

**Difficulty:** Staff | **Category:** Security / Boot

**Answer:**

1. **What it does:** `init=/bin/bash` on the kernel command line causes the kernel to execute `/bin/bash` as PID 1 instead of the normal init system -- giving an unauthenticated root shell
2. **Prerequisite -- must be able to modify the kernel command line:**
   - Physical access to the machine (to reach the GRUB menu)
   - IPMI/iLO/BMC access (out-of-band management)
   - Serial console access
3. **Perspective:** If an attacker has physical access, you have already lost the physical security boundary. They could also remove the disk, boot from USB, or replace the firmware.
4. **Mitigations (defense in depth):**
   - **GRUB password:** `grub-mkpasswd-pbkdf2` + add to `/etc/grub.d/40_custom`. Prevents modifying boot parameters without the password.
   - **UEFI Secure Boot:** Firmware verifies the bootloader signature. Modified kernel command lines would need re-signing.
   - **LUKS full-disk encryption:** Even with `init=/bin/bash`, the root filesystem is encrypted. Without the passphrase, data is inaccessible.
   - **Measured boot with TPM:** PCR values change if the command line is modified. Remote attestation detects tampering.
   - **Kernel lockdown mode:** In `confidentiality` mode, prevents accessing kernel memory even as root.
5. **Cloud context:** Largely irrelevant -- the hypervisor controls the boot chain, and tenants cannot access the GRUB menu.

---

### Q16. A server shows uptime of 400 days. Is this good or bad?

**Difficulty:** Senior | **Category:** Operations / Security

**Answer:**

**It is a red flag.** While 400 days of uptime demonstrates hardware and OS stability, it means:

1. **400 days of unpatched kernel vulnerabilities.** Major CVEs are disclosed every few months (Spectre/Meltdown variants, use-after-free in netfilter, privilege escalation in overlayfs, etc.). A 400-day uptime means none of these patches have been applied via reboot.

2. **Possible compliance violations.** PCI-DSS, SOC2, and similar frameworks require timely patching. A 400-day kernel is likely out of compliance.

3. **Risk of accumulated state drift.** Kernel memory fragmentation, leaked resources, and other issues accumulate over long uptimes.

**Modern approach:**
- **Kernel live patching** (kpatch, Canonical Livepatch, RHEL kpatch) for critical security fixes between reboots
- **Scheduled rolling reboots:** Monthly or quarterly maintenance windows. At FAANG scale, this is automated and continuous -- nodes are drained and rebooted in a rolling fashion with zero user impact
- **No node should exceed 30-60 days** without a reboot in a well-managed fleet
- **Immutable infrastructure:** Instead of patching old nodes, replace them with freshly built images

---

### Q17. What is the difference between `TASK_INTERRUPTIBLE` and `TASK_UNINTERRUPTIBLE` sleep states? Why does it matter for the OOM killer?

**Difficulty:** Staff | **Category:** Kernel / Process States

**Answer:**

Both are sleep states where the process is waiting for an event (I/O completion, lock release, etc.) and is NOT on the CPU run queue:

**`TASK_INTERRUPTIBLE` (S-state in ps):**
- The process can be woken up by signals (including SIGKILL)
- If a signal arrives before the awaited event, the syscall returns -EINTR
- Example: `sleep(10)` puts the process in TASK_INTERRUPTIBLE; `kill` can interrupt it

**`TASK_UNINTERRUPTIBLE` (D-state in ps):**
- The process CANNOT be woken up by signals -- not even SIGKILL
- Only the awaited event (I/O completion, lock release) can wake it
- This exists to prevent data corruption: if a process is in the middle of a disk write, interrupting it could leave filesystem metadata inconsistent
- Example: process waiting for disk I/O in the block layer

**Why D-state matters for the OOM killer:**
- D-state processes cannot be killed (SIGKILL is deferred until they wake up)
- If the OOM killer selects a D-state process, the kill doesn't take effect immediately
- The system remains in OOM condition until the process eventually wakes up and processes the SIGKILL
- In extreme cases (e.g., NFS server unreachable), D-state processes never wake up, and the OOM killer is ineffective -- the system hangs

**`TASK_KILLABLE` (introduced in kernel 2.6.25):**
- A variant of TASK_UNINTERRUPTIBLE that can be woken by fatal signals (SIGKILL specifically)
- Used in NFS and other subsystems to allow stuck I/O to be killed without risking data corruption for non-critical operations
- This is why modern kernels handle NFS hangs more gracefully than older ones

---

### Q18. Explain the purpose of initramfs. Why can't the kernel mount the root filesystem directly?

**Difficulty:** Senior | **Category:** Boot Process

**Answer:**

1. **Simple case:** The kernel *can* mount simple root filesystems directly -- if the root device is a plain partition on a directly-attached disk with a driver compiled into the kernel
2. **But modern storage is not simple.** A typical production server might boot from:
   - An NVMe SSD behind a hardware RAID controller
   - A logical volume (LVM) on a LUKS-encrypted partition on a software RAID array
   - An iSCSI LUN accessed over a bonded network interface
   - A Ceph RBD device on a cloud instance
3. **Required drivers for complex root:** The kernel would need:
   - The RAID driver (e.g., `megaraid_sas`, `md`)
   - The LVM device mapper
   - The LUKS crypto subsystem
   - The network driver and iSCSI initiator
   - The filesystem driver (e.g., `ext4`, `xfs`)
   - Compiling ALL combinations into the kernel would make it enormous and unmanageable
4. **The initramfs solution:**
   - A minimal user-space environment (compressed cpio archive) loaded into RAM by the bootloader
   - Contains exactly the drivers and tools needed for this machine's specific storage configuration
   - Once the real root device is assembled and mounted, `switch_root` transitions to it and initramfs memory is freed
5. **Key interview detail:** initramfs is generated by `update-initramfs` (Debian/Ubuntu) or `dracut` (RHEL/Fedora) and is specific to the running kernel version and detected hardware. Moving a disk to different hardware may cause boot failure if the initramfs lacks the necessary drivers.

---

> **Study tip:** For Principal-level interviews, practice chaining these questions. An interviewer might start with "What happens when you press the power button?" and progressively drill into syscalls, memory management, and specific debugging scenarios. Your ability to go deep on any sub-topic while maintaining the big picture is what distinguishes Staff from Principal.

---

> Full topic reference: [fundamentals.md](../00-fundamentals/fundamentals.md) | Cheatsheet: [00-fundamentals.md](../cheatsheets/00-fundamentals.md)
