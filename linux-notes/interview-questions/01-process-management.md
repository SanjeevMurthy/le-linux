# Interview Questions: Process Management

> **Source:** [Process Management — Full Guide](../01-process-management/process-management.md)
> **Level Range:** Senior / Staff / Principal SRE & Cloud Engineer
> **Total Questions:** 18

---

<!-- toc -->
## Table of Contents

- [Category A: Conceptual Deep Questions](#category-a-conceptual-deep-questions)
  - [Q1. Explain the relationship between PID and TGID in the Linux kernel. Why does `getpid()` return TGID?](#q1-explain-the-relationship-between-pid-and-tgid-in-the-linux-kernel-why-does-getpid-return-tgid)
  - [Q2. What happens to a process's children when the parent dies? Describe the complete orphan handling mechanism.](#q2-what-happens-to-a-processs-children-when-the-parent-dies-describe-the-complete-orphan-handling-mechanism)
  - [Q3. Explain Copy-on-Write in `fork()`. What are the performance implications for memory-intensive applications?](#q3-explain-copy-on-write-in-fork-what-are-the-performance-implications-for-memory-intensive-applications)
  - [Q4. Why can `SIGKILL` fail to kill a process? List all scenarios.](#q4-why-can-sigkill-fail-to-kill-a-process-list-all-scenarios)
  - [Q5. Describe the differences between `TASK_INTERRUPTIBLE`, `TASK_UNINTERRUPTIBLE`, and `TASK_KILLABLE`. Why does each exist?](#q5-describe-the-differences-between-task_interruptible-task_uninterruptible-and-task_killable-why-does-each-exist)
- [Category B: Scenario-Based Questions](#category-b-scenario-based-questions)
  - [Q6. You receive an alert that a production server has 5000 zombie processes. Walk through your investigation and remediation.](#q6-you-receive-an-alert-that-a-production-server-has-5000-zombie-processes-walk-through-your-investigation-and-remediation)
  - [Q7. A container running in Kubernetes cannot spawn new processes (`fork: Resource temporarily unavailable`), but the host has plenty of resources. Diagnose.](#q7-a-container-running-in-kubernetes-cannot-spawn-new-processes-fork-resource-temporarily-unavailable-but-the-host-has-plenty-of-resources-diagnose)
  - [Q8. Explain what happens step-by-step when you type `ls | grep foo` in bash, from fork to exit.](#q8-explain-what-happens-step-by-step-when-you-type-ls-grep-foo-in-bash-from-fork-to-exit)
  - [Q9. Your team's Go service is leaking goroutines, and the process has 50,000 threads. What is the system-level impact and how do you investigate?](#q9-your-teams-go-service-is-leaking-goroutines-and-the-process-has-50000-threads-what-is-the-system-level-impact-and-how-do-you-investigate)
- [Category C: Debugging Questions](#category-c-debugging-questions)
  - [Q10. How do you determine what a process in `D` state is waiting for?](#q10-how-do-you-determine-what-a-process-in-d-state-is-waiting-for)
  - [Q11. A process is consuming 100% of a CPU core but no output is being produced. How do you diagnose?](#q11-a-process-is-consuming-100-of-a-cpu-core-but-no-output-is-being-produced-how-do-you-diagnose)
  - [Q12. After deploying a new kernel, processes randomly receive SIGSEGV. How do you investigate?](#q12-after-deploying-a-new-kernel-processes-randomly-receive-sigsegv-how-do-you-investigate)
  - [Q13. How do you trace why a process is slow to start?](#q13-how-do-you-trace-why-a-process-is-slow-to-start)
- [Category D: Trick Questions](#category-d-trick-questions)
  - [Q14. Can a zombie process be killed with `kill -9`?](#q14-can-a-zombie-process-be-killed-with-kill--9)
  - [Q15. If `fork()` returns 0, are you in the parent or child? What if it returns -1?](#q15-if-fork-returns-0-are-you-in-the-parent-or-child-what-if-it-returns--1)
  - [Q16. Is it possible for a process to have PID 0? What about negative PIDs in `kill()`?](#q16-is-it-possible-for-a-process-to-have-pid-0-what-about-negative-pids-in-kill)
  - [Q17. What is the maximum number of processes a Linux system can run? What are all the limits that apply?](#q17-what-is-the-maximum-number-of-processes-a-linux-system-can-run-what-are-all-the-limits-that-apply)
  - [Q18. Explain the double-fork technique for creating daemon processes. Why is it no longer recommended?](#q18-explain-the-double-fork-technique-for-creating-daemon-processes-why-is-it-no-longer-recommended)
- [Scoring Guide](#scoring-guide)

<!-- toc stop -->

## Category A: Conceptual Deep Questions

### Q1. Explain the relationship between PID and TGID in the Linux kernel. Why does `getpid()` return TGID?
**Difficulty:** Senior | **Category:** Conceptual

**Answer:**
1. In the kernel's `task_struct`, `pid` is the unique thread identifier and `tgid` (Thread Group ID) is the process identifier
2. All threads created by `clone(CLONE_THREAD)` share the same `tgid` but have distinct `pid` values
3. The thread group leader's `pid` equals its `tgid`
4. `getpid()` returns `tgid` (not `pid`) to maintain POSIX compatibility — POSIX specifies that all threads in a process share the same process ID
5. `gettid()` returns the kernel `pid` field (the actual thread ID)
6. This means `/proc/<PID>/task/<TID>` directories use kernel `pid` values for TIDs while the outer directory name uses `tgid` for PID

---

### Q2. What happens to a process's children when the parent dies? Describe the complete orphan handling mechanism.
**Difficulty:** Senior | **Category:** Conceptual

**Answer:**
1. The kernel calls `forget_original_parent()` in `exit_notify()`
2. All children are re-parented — the new parent is determined by:
   - First, check for a `subreaper` ancestor (set via `prctl(PR_SET_CHILD_SUBREAPER)`)
   - If no subreaper exists, re-parent to PID 1 (`init`/`systemd`)
3. Any children that are already zombies get immediately reaped by the new parent
4. `SIGCHLD` is sent to the new parent for any zombie children
5. The subreaper mechanism was introduced for container init processes (e.g., `tini`, `dumb-init`) — they register as subreapers so orphans are adopted by the container's PID 1, not the host's PID 1
6. In a PID namespace, the namespace's init process (PID 1 within that namespace) acts as the reaper for all orphans in that namespace

---

### Q3. Explain Copy-on-Write in `fork()`. What are the performance implications for memory-intensive applications?
**Difficulty:** Staff | **Category:** Conceptual

**Answer:**
1. After `fork()`, parent and child share the same physical memory pages
2. The kernel marks all writable pages as read-only in both processes' page tables
3. When either process writes, a page fault occurs, the kernel allocates a new page, copies the content, and updates the page table
4. This makes `fork()` O(page_table_size) not O(memory_size) — very fast even for large processes
5. **Performance implications:**
   - Redis `BGSAVE`: fork for background save can cause memory usage to temporarily double if the dataset is being actively written during the save (every modified page gets copied)
   - JVM garbage collectors: a GC cycle after fork can trigger COW on large portions of the heap
   - Transparent Huge Pages (THP) amplify COW cost: a single write to a 2MB huge page requires copying the entire 2MB, not just 4KB
6. **Mitigation strategies:**
   - Disable THP for Redis: `echo never > /sys/kernel/mm/transparent_hugepage/enabled`
   - Use `posix_spawn()` or `vfork() + exec()` instead of `fork() + exec()` when you just want to launch a new program
   - `MADV_WIPEONFORK` flag (Linux 4.14+) tells kernel to zero pages instead of COW-copying them in the child

---

### Q4. Why can `SIGKILL` fail to kill a process? List all scenarios.
**Difficulty:** Staff | **Category:** Conceptual

**Answer:**
1. **`TASK_UNINTERRUPTIBLE` (D state):** Process is in an uninterruptible kernel code path (typically block I/O, NFS hard mount). Cannot receive any signals until the kernel operation completes
2. **Zombie process:** Already dead. Not a process anymore, just a process table entry. `SIGKILL` has no target to kill. The parent must call `wait()`
3. **PID 1 (init):** The kernel protects PID 1 from signals it has not explicitly registered handlers for. `SIGKILL` is dropped for init unless it has registered a handler (which it never should)
4. **PID 1 inside a PID namespace:** Similar protection — the namespace init process is immune to `SIGKILL` from within its namespace. It CAN be killed from the parent namespace
5. **Process in a frozen cgroup:** If a cgroup is in `FROZEN` state (via the freezer controller), signals are not delivered until the cgroup is thawed
6. **Kernel thread:** Kernel threads (visible in brackets in `ps`, e.g., `[kworker/0:1]`) cannot be killed by userspace signals

---

### Q5. Describe the differences between `TASK_INTERRUPTIBLE`, `TASK_UNINTERRUPTIBLE`, and `TASK_KILLABLE`. Why does each exist?
**Difficulty:** Staff | **Category:** Conceptual

**Answer:**
1. **`TASK_INTERRUPTIBLE` (S state):**
   - Process sleeps until either the wait condition is satisfied OR a signal is delivered
   - Used for operations that can be safely interrupted (e.g., `sleep()`, `poll()`, `select()`, waiting for terminal input)
   - Most common sleep state — the vast majority of sleeping processes are in this state
2. **`TASK_UNINTERRUPTIBLE` (D state):**
   - Process sleeps until the wait condition is satisfied; signals are completely ignored
   - Used when interrupting the operation could corrupt kernel data structures (e.g., during disk I/O completion, page fault handling, certain mutex acquisitions)
   - The process CANNOT be killed, not even with `SIGKILL`
   - Normally transient (microseconds to milliseconds), but becomes problematic if the underlying I/O never completes (NFS hard mount, dead storage device)
3. **`TASK_KILLABLE` (also shows as D state):**
   - Introduced in Linux 2.6.25 as `TASK_WAKEKILL | TASK_UNINTERRUPTIBLE`
   - Behaves like `TASK_UNINTERRUPTIBLE` for most signals but will respond to fatal signals (`SIGKILL`)
   - Solves the "unkillable NFS process" problem
   - NFS client code and several other I/O paths have been converted to use this state
   - Identifiable by `killable` appearing in `/proc/<PID>/wchan` or `/proc/<PID>/stack`

---

## Category B: Scenario-Based Questions

### Q6. You receive an alert that a production server has 5000 zombie processes. Walk through your investigation and remediation.
**Difficulty:** Senior | **Category:** Scenario

**Answer:**
1. **Assess severity:** Check `cat /proc/sys/kernel/pid_max` and current PID count (`ls -d /proc/[0-9]* | wc -l`). If approaching limit, escalate immediately
2. **Identify zombie parents:**
   ```
   ps -eo ppid,stat | awk '$2=="Z"{print $1}' | sort | uniq -c | sort -rn | head
   ```
3. **Determine if parent is a single process or systemic issue** — single parent with thousands of zombies points to an application bug; many parents with a few zombies each suggests a systemic issue
4. **Inspect the parent:**
   - `strace -fp <PPID> -e trace=wait4` — is it calling wait()?
   - `cat /proc/<PPID>/status` — check thread count, state
   - Check if parent has `SIGCHLD` set to `SIG_IGN`
5. **Immediate remediation:**
   - Send `SIGCHLD` to parent: `kill -CHLD <PPID>` — may trigger a wait() call
   - Restart the parent process (zombies are re-parented to init and reaped)
   - If parent is unkillable, zombies will persist until reboot
6. **Root cause:** File bug with the application team — parent is not reaping children
7. **Prevention:** Container init process (tini/dumb-init), zombie monitoring alert, `pids.max` cgroup limit

---

### Q7. A container running in Kubernetes cannot spawn new processes (`fork: Resource temporarily unavailable`), but the host has plenty of resources. Diagnose.
**Difficulty:** Senior | **Category:** Scenario

**Answer:**
1. **Check cgroup PID limit:**
   ```
   cat /sys/fs/cgroup/pids/<pod-cgroup>/pids.max
   cat /sys/fs/cgroup/pids/<pod-cgroup>/pids.current
   ```
2. **If current is near max:** Count zombies inside the container — they consume PID slots
3. **Check container init process:** If PID 1 in the container is the application itself (not a proper init), it will not reap orphaned zombie children
4. **Check thread count:** Threads also consume PID slots in the cgroup. A Java application with 500 threads eats significantly into the limit
5. **Check ulimits:** `cat /proc/<PID>/limits | grep "Max processes"` — both ulimit and cgroup limits can apply
6. **Solution:**
   - Increase `pids.max` in pod spec if legitimately needed
   - Fix zombie leak if present
   - Use `shareProcessNamespace: true` in Kubernetes pod spec to enable cross-container PID visibility
   - Add `tini` as PID 1 in Dockerfile: `ENTRYPOINT ["/tini", "--"]`

---

### Q8. Explain what happens step-by-step when you type `ls | grep foo` in bash, from fork to exit.
**Difficulty:** Staff | **Category:** Scenario

**Answer:**
1. Bash calls `pipe()` — kernel creates a pipe, returns two file descriptors: `fd[0]` (read end) and `fd[1]` (write end)
2. Bash calls `fork()` for the first child (will run `ls`):
   - Child closes `fd[0]` (read end)
   - Child calls `dup2(fd[1], STDOUT_FILENO)` — redirects stdout to pipe write end
   - Child closes `fd[1]` (original is no longer needed after dup2)
   - Child calls `execvp("ls", ...)` — replaces process image with `ls`
3. Bash calls `fork()` for the second child (will run `grep`):
   - Child closes `fd[1]` (write end)
   - Child calls `dup2(fd[0], STDIN_FILENO)` — redirects stdin to pipe read end
   - Child closes `fd[0]`
   - Child calls `execvp("grep", ["grep", "foo"])` — replaces process image with `grep`
4. Bash (parent) closes both pipe FDs (critical — otherwise `grep` will never see EOF on the read end)
5. `ls` writes directory listing to stdout (which is the pipe), then calls `exit(0)` — enters zombie state
6. Pipe write end is closed (last writer gone), so `grep` sees EOF on stdin
7. `grep` reads from stdin (the pipe), filters lines, writes matches to its stdout (the terminal), calls `exit(0)` — enters zombie state
8. Bash calls `waitpid()` for each child, collects exit statuses, zombies are reaped
9. Bash stores `$?` from the last command in the pipeline (`grep`). With `set -o pipefail`, bash stores the rightmost non-zero exit code

---

### Q9. Your team's Go service is leaking goroutines, and the process has 50,000 threads. What is the system-level impact and how do you investigate?
**Difficulty:** Staff | **Category:** Scenario

**Answer:**
1. **System impact:**
   - Each OS thread consumes a PID slot (threads are tracked as `task_struct` with unique PIDs)
   - Each thread has a kernel stack (~16KB on x86_64) and thread-local storage
   - 50,000 threads = ~800 MB of kernel stack memory alone
   - Can hit `threads-max` limit (`cat /proc/sys/kernel/threads-max`)
   - Can exhaust PID space if other processes are also running
   - Context switch overhead increases proportionally
2. **Investigation:**
   ```
   cat /proc/<PID>/status | grep Threads   # confirm thread count
   ls /proc/<PID>/task/ | wc -l            # list all thread TIDs
   cat /proc/<PID>/task/<TID>/stack        # per-thread kernel stack
   ```
3. **Go-specific debugging:**
   - Send `SIGQUIT` to the process — Go runtime dumps all goroutine stacks to stderr
   - Use `pprof` endpoint: `curl http://localhost:6060/debug/pprof/goroutine?debug=2`
   - Look for goroutines blocked on channel operations, HTTP connections without timeouts, or mutexes
4. **Mitigation:**
   - Set `GOMAXPROCS` to limit the number of OS threads that can execute goroutines simultaneously
   - Fix goroutine leaks (add context cancellation, timeouts on HTTP clients, bounded worker pools)
   - Monitor goroutine count via Prometheus metrics or pprof

---

## Category C: Debugging Questions

### Q10. How do you determine what a process in `D` state is waiting for?
**Difficulty:** Senior | **Category:** Debugging

**Answer:**
1. `cat /proc/<PID>/wchan` — shows the kernel function the process is sleeping in
2. `cat /proc/<PID>/stack` — full kernel stack trace showing the entire call chain
3. `cat /proc/<PID>/status | grep State` — confirm the D state
4. Common wchan values and their meanings:
   - `io_schedule` — waiting for block I/O (disk)
   - `rpc_wait_bit_killable` — NFS RPC call pending
   - `blkdev_issue_flush` — disk flush operation
   - `mutex_lock` — kernel mutex contention
   - `page_fault` — waiting for memory page to be brought in
   - `vfs_fsync_range` — fsync/fdatasync in progress
5. Check block device status: `cat /sys/block/*/device/state` (look for `blocked`)
6. Check NFS status: `nfsstat -rc` for retransmission counts
7. Use `echo w > /proc/sysrq-trigger` to dump ALL D-state processes and their kernel stacks to the kernel ring buffer (`dmesg`)

---

### Q11. A process is consuming 100% of a CPU core but no output is being produced. How do you diagnose?
**Difficulty:** Senior | **Category:** Debugging

**Answer:**
1. **Determine if CPU time is user or system:**
   ```
   pidstat -p <PID> 1 5
   # Watch %usr vs %system columns over 5 seconds
   ```
2. **If mostly user-space (high %usr):** The process is in a tight loop in application code
   - `perf top -p <PID>` — see which function is consuming CPU
   - `perf record -g -p <PID> -- sleep 10 && perf report` — create a profile with call graphs
   - `strace -c -p <PID>` — if very few syscalls, it is a pure userspace spin
3. **If mostly kernel-space (high %system):** The process is spinning in kernel code
   - `cat /proc/<PID>/stack` — check kernel call chain
   - `perf top -p <PID>` — will show kernel function consuming CPU
   - May indicate spinlock contention, inefficient kernel module, or kernel bug
4. **Check if stuck in a futex spin (livelock):**
   - `strace -e futex -p <PID>` — repeated `futex(FUTEX_WAIT)` returning immediately indicates contention
5. **For interpreted/managed runtime processes:**
   - Java: `jstack <PID>` or async-profiler
   - Go: `SIGQUIT` for goroutine dump or pprof
   - Python: `py-spy top --pid <PID>`

---

### Q12. After deploying a new kernel, processes randomly receive SIGSEGV. How do you investigate?
**Difficulty:** Staff | **Category:** Debugging

**Answer:**
1. **Collect core dumps:** Ensure `ulimit -c unlimited` and verify `cat /proc/sys/kernel/core_pattern`
2. **Analyze with gdb:**
   ```
   gdb /path/to/binary /path/to/core
   (gdb) bt full        # full backtrace with local variables
   (gdb) info registers # check instruction pointer and flags
   ```
3. **Check kernel changelog:** Look for changes in memory management, ASLR, security hardening
4. **Compare sysctl settings:** `diff <(ssh old-kernel-host sysctl -a 2>/dev/null) <(sysctl -a 2>/dev/null)`
5. **Check new security features:** New kernel may enable SMEP (Supervisor Mode Execution Prevention) or SMAP (Supervisor Mode Access Prevention), which can expose latent bugs in kernel modules
6. **Check compiler and config differences:** Different `CONFIG_HARDENED_USERCOPY`, `CONFIG_STACKPROTECTOR_STRONG`, or glibc interactions
7. **Use `dmesg`:** Look for kernel messages about memory violations, fault addresses, whether fault is in kernel or user space
8. **Bisect:** If possible, test with intermediate kernel versions to narrow the regression window using `git bisect` on the kernel source

---

### Q13. How do you trace why a process is slow to start?
**Difficulty:** Senior | **Category:** Debugging

**Answer:**
1. **Trace all syscalls with timing:**
   ```
   strace -T -f -o /tmp/startup.log <command>
   ```
   Then find the slowest calls: sort the output by the time field in angle brackets
2. **Common slow-start culprits:**
   - `openat()` calls to network filesystems (NFS, CIFS) — look for calls with >100ms latency
   - DNS resolution during `connect()` — check `nsswitch.conf` and `/etc/resolv.conf` timeout settings
   - Shared library loading — excessive `mmap()` calls for `.so` files in large dependency trees
   - SELinux/AppArmor policy evaluation — visible in `access()` and `stat()` syscalls
   - Lock contention on shared files (e.g., lock files, PID files)
3. **Performance counter summary:**
   ```
   perf stat <command>
   # Shows total syscall count, context switches, CPU migrations, cache misses
   ```
4. **For systemd services specifically:**
   ```
   systemd-analyze blame          # per-unit startup times
   systemd-analyze critical-chain # dependency chain with timing
   ```

---

## Category D: Trick Questions

### Q14. Can a zombie process be killed with `kill -9`?
**Difficulty:** Senior | **Category:** Trick

**Answer:**
- **No.** A zombie is already dead. It has already called `exit()`. There is no running code to receive the signal
- The `Z` entry in the process table is just a placeholder holding the exit status until the parent calls `wait()`
- The only ways to remove a zombie:
  1. The parent calls `wait()` / `waitpid()` to collect the exit status
  2. The parent is killed — zombies are re-parented to init, which reaps them
  3. System reboot
- The PID consumed by the zombie IS released back to the pool after reaping
- Zombies consume no CPU, no memory (their address space is already freed), just a `task_struct` entry (~6 KB kernel memory) and one PID slot
- **Interview tip:** Many candidates attempt to "kill zombies" — the correct action is to fix or restart the parent

---

### Q15. If `fork()` returns 0, are you in the parent or child? What if it returns -1?
**Difficulty:** Senior | **Category:** Trick

**Answer:**
- Return value 0: **you are in the child process**
- Return value > 0: you are in the parent, and the return value is the child's PID
- Return value -1: `fork()` **failed** — no child was created. Common reasons:
  1. `EAGAIN`: PID limit reached (`pid_max`, `ulimit -u`, cgroup `pids.max`)
  2. `ENOMEM`: Insufficient memory for new `task_struct` or page tables
- **Why this design:** The child needs to know it is the child (to call `exec()`), while the parent needs the child's PID (to call `waitpid()` later). Returning 0 to the child and the child's PID to the parent elegantly solves both needs with a single return value
- **Common mistake:** Many candidates say "0 means parent" — it is the opposite

---

### Q16. Is it possible for a process to have PID 0? What about negative PIDs in `kill()`?
**Difficulty:** Principal | **Category:** Trick

**Answer:**
- **PID 0 — the idle/swapper task:**
  - The idle task (swapper) has PID 0 and is created by the kernel during boot, not via `fork()`
  - It runs only when no other process is schedulable (the CPU is idle)
  - On SMP systems, each CPU core has its own idle task, all with PID 0
  - Never visible in userspace process listings (`/proc/0` does not exist)
  - It is NOT a kernel thread — kernel threads have PIDs > 0 and are children of PID 2 (`kthreadd`)
- **Negative PIDs in `kill()`:**
  - `kill(0, sig)` — send signal to all processes in the caller's process group
  - `kill(-1, sig)` — send signal to all processes the caller has permission to signal (except PID 1)
  - `kill(-pgid, sig)` — send signal to all processes in process group `pgid`
  - These negative values are NOT PIDs — they are special addressing modes for the `kill()` syscall
- **Follow-up trap:** The kernel uses PID 0 internally for the idle task, but PID 0 is never allocated by the PID allocator. The first userspace-visible PID is 1 (init)

---

### Q17. What is the maximum number of processes a Linux system can run? What are all the limits that apply?
**Difficulty:** Staff | **Category:** Trick

**Answer:**
- Multiple limits apply, and the effective limit is the minimum of all of them:
  1. **`kernel.pid_max`** (`/proc/sys/kernel/pid_max`):
     - Default: 32768
     - Maximum: 4194304 (2^22) on 64-bit systems
     - This limits the PID number space, not directly the process count
  2. **`kernel.threads-max`** (`/proc/sys/kernel/threads-max`):
     - System-wide hard limit on total tasks (processes + threads)
     - Default is typically calculated as `mempages / (8 * THREAD_SIZE / PAGE_SIZE)`
  3. **Per-user limit (`ulimit -u` / `nproc`)**:
     - Set in `/etc/security/limits.conf` or PAM
     - Limits processes per UID (not per session)
  4. **Cgroup `pids.max`**:
     - Per-cgroup limit, commonly used in containers
     - Kubernetes `spec.containers[].resources` maps to this
  5. **Available memory:**
     - Each task_struct is ~6-8 KB of kernel (non-swappable) memory
     - Each thread needs a kernel stack (~16 KB on x86_64)
     - At 4M processes: ~96 GB just for task_struct + kernel stacks
  6. **`vm.max_map_count`** (`/proc/sys/vm/max_map_count`):
     - Limits memory map areas per process (affects heavily multi-threaded processes)
     - Default: 65530
- **Practical answer:** On a typical production server, `pid_max` (32768) or `ulimit -u` is the binding constraint unless deliberately raised

---

### Q18. Explain the double-fork technique for creating daemon processes. Why is it no longer recommended?
**Difficulty:** Staff | **Category:** Trick

**Answer:**
1. **The double-fork technique (traditional):**
   - First `fork()`: parent exits immediately, child continues (orphaned, adopted by init)
   - Child calls `setsid()` to become a session leader and detach from the controlling terminal
   - Second `fork()`: the session leader exits, grandchild continues
   - The grandchild is NOT a session leader, so it can never accidentally acquire a controlling terminal by opening a terminal device
   - The grandchild also closes stdin/stdout/stderr, opens `/dev/null`, and changes cwd to `/`
2. **Why it exists:** In the SysV init era, daemons needed to detach themselves from the terminal and parent shell. The double-fork ensured complete detachment
3. **Why it is no longer recommended:**
   - `systemd` (and other modern init systems) expect services to run in the foreground. They manage daemonization themselves via `Type=simple` or `Type=exec`
   - Double-forking makes it harder for systemd to track the service's main PID
   - `Type=forking` exists for compatibility but is considered legacy
   - Containers also expect processes to run in the foreground as PID 1
4. **Modern approach:** Run the service in the foreground, let systemd/container runtime handle process lifecycle, supervision, and logging (stdout/stderr capture)
5. **When double-fork is still relevant:** When writing a daemon that must work without systemd (e.g., embedded systems, minimal init environments)

---

## Scoring Guide

| Score | Level | Expectation |
|-------|-------|-------------|
| 12-14 correct | Senior | Solid process management knowledge, can handle most production issues |
| 15-16 correct | Staff | Deep kernel understanding, can debug complex multi-system interactions |
| 17-18 correct | Principal | Expert-level knowledge, can design systems and mentor on process internals |

---

*[Back to main guide](../01-process-management/process-management.md) | [Cheatsheet](../cheatsheets/01-process-management.md)*
