# Interview Questions Bank

> 229 questions across 12 topics. Designed for Senior SRE / Staff / Principal Engineer interviews.

---

<!-- toc -->
## Table of Contents

- [Question Files](#question-files)
- [Questions by Difficulty](#questions-by-difficulty)
  - [Senior (L5/E5) -- Foundations](#senior-l5e5----foundations)
  - [Staff (L6/E6) -- Deep Internals and Production Expertise](#staff-l6e6----deep-internals-and-production-expertise)
  - [Principal (L7+/E7+) -- Architecture and Deep Kernel Knowledge](#principal-l7e7----architecture-and-deep-kernel-knowledge)
- [Questions by Type](#questions-by-type)
  - [Conceptual (Test your mental model)](#conceptual-test-your-mental-model)
  - [Scenario (Test your debugging approach)](#scenario-test-your-debugging-approach)
  - [Debugging (Test your command-line skills)](#debugging-test-your-command-line-skills)
  - [Trick Questions (Test precision under pressure)](#trick-questions-test-precision-under-pressure)
- [Recommended Study Order](#recommended-study-order)
- [Top 10 Most Likely to Be Asked](#top-10-most-likely-to-be-asked)

<!-- toc stop -->

## Question Files

| # | Topic | Questions | Link |
|---|-------|-----------|------|
| 00 | Fundamentals (Boot, Kernel, Syscalls) | 18 | [00-fundamentals.md](00-fundamentals.md) |
| 01 | Process Management | 18 | [01-process-management.md](01-process-management.md) |
| 02 | CPU Scheduling | 21 | [02-cpu-scheduling.md](02-cpu-scheduling.md) |
| 03 | Memory Management | 20 | [03-memory-management.md](03-memory-management.md) |
| 04 | Filesystem and Storage | 20 | [04-filesystem-and-storage.md](04-filesystem-and-storage.md) |
| 05 | LVM and Disk Management | 19 | [05-lvm.md](05-lvm.md) |
| 06 | Networking (TCP/IP, DNS, Netfilter) | 18 | [06-networking.md](06-networking.md) |
| 07 | Kernel Internals (Modules, cgroups, Namespaces) | 20 | [07-kernel-internals.md](07-kernel-internals.md) |
| 08 | Performance and Debugging | 20 | [08-performance-and-debugging.md](08-performance-and-debugging.md) |
| 09 | Security (SELinux, PAM, Hardening) | 18 | [09-security.md](09-security.md) |
| 10 | System Design Scenarios | 17 | [10-system-design-scenarios.md](10-system-design-scenarios.md) |
| 11 | Real-World SRE Incidents | 20 | [11-sre-incidents.md](11-sre-incidents.md) |
| | **Total** | **229** | |

---

## Questions by Difficulty

### Senior (L5/E5) -- Foundations

Expected knowledge for any Senior SRE role. These test core understanding and operational competence.

| Topic | Question | Link |
|-------|----------|------|
| 00 | Monolithic vs. microkernel -- why did Linux choose monolithic? | [Q1](00-fundamentals.md#q1-explain-the-difference-between-a-monolithic-kernel-and-a-microkernel-why-did-linux-choose-monolithic-and-what-are-the-modern-mitigations-for-its-downsides) |
| 01 | What happens to children when a parent dies? Orphan handling. | [Q2](01-process-management.md#q2-what-happens-to-a-processs-children-when-the-parent-dies-describe-the-complete-orphan-handling-mechanism) |
| 02 | Load average vs. CPU utilization -- why can load be 50 on 16 cores? | [Q1](02-cpu-scheduling.md#q1-explain-the-difference-between-load-average-and-cpu-utilization-why-can-you-have-a-load-average-of-50-on-a-16-core-system-with-5-cpu-utilization) |
| 03 | RSS vs. VSZ vs. PSS vs. USS -- which for capacity planning? | [Q3](03-memory-management.md#q3-explain-the-relationship-between-rss-vsz-pss-and-uss-which-metric-should-you-use-for-capacity-planning) |
| 04 | Hard link vs. symbolic link at the inode level | [Q2](04-filesystem-and-storage.md#q2-what-is-the-difference-between-a-hard-link-and-a-symbolic-link-at-the-inode-level) |
| 05 | LVM abstraction layers -- PVs, VGs, LVs, and PE/LE mapping | [Q1](05-lvm.md#q1-explain-the-lvm-abstraction-layers-what-are-pvs-vgs-lvs-and-how-do-pesles-map-between-them) |
| 06 | TCP lifecycle: all state transitions from SYN to TIME_WAIT | [Q1](06-networking.md#q1-walk-through-the-complete-lifecycle-of-a-tcp-connection-including-all-state-transitions-what-happens-at-each-stage-in-the-kernel) |
| 07 | cgroups v2 unified hierarchy vs. v1 | [Q3](07-kernel-internals.md#q3-explain-cgroups-v2-unified-hierarchy-how-does-it-differ-from-v1-and-why-does-kubernetes-require-it) |
| 08 | Systematic slow-server debugging methodology | [Q1](08-performance-and-debugging.md#q1-walk-me-through-how-you-would-debug-a-slow-server-what-is-your-systematic-methodology) |
| 09 | DAC vs. MAC -- when to deploy SELinux | [Q1](09-security.md#q1-explain-dac-vs-mac-in-linux-when-would-you-choose-to-deploy-selinux-over-standard-permissions) |
| 10 | kubectl run to running container -- map to Linux primitives | [Q2](10-system-design-scenarios.md#q2-explain-the-complete-chain-from-kubectl-run-to-a-running-container-process-map-each-step-to-a-linux-primitive) |
| 11 | SLI, SLO, SLA, and error budgets | [Q6](11-sre-incidents.md#q6-explain-sli-slo-sla-and-error-budgets-how-do-they-work-together) |

### Staff (L6/E6) -- Deep Internals and Production Expertise

Expected for Staff Engineer roles. These test kernel-level understanding and complex debugging.

| Topic | Question | Link |
|-------|----------|------|
| 00 | vDSO: what it is, why it exists, which syscalls it accelerates | [Q2](00-fundamentals.md#q2-what-is-the-vdso-and-why-does-it-exist-name-the-specific-syscalls-it-accelerates-and-explain-the-mechanism) |
| 01 | Copy-on-Write in fork() -- performance implications | [Q3](01-process-management.md#q3-explain-copy-on-write-in-fork-what-are-the-performance-implications-for-memory-intensive-applications) |
| 02 | EEVDF scheduler -- how it improves upon CFS | [Q3](02-cpu-scheduling.md#q3-explain-eevdf-and-how-it-improves-upon-cfs-what-specific-problems-did-cfs-have-that-eevdf-solves) |
| 03 | Container using 4G limit OOM-killed with only 2G heap | [Q8](03-memory-management.md#q8-a-container-running-with-memorymax4g-is-being-oom-killed-but-the-application-inside-reports-using-only-2-gib-of-heap-what-is-consuming-the-other-2-gib) |
| 04 | Three-table relationship: fd, open file descriptions, inodes | [Q4](04-filesystem-and-storage.md#q4-describe-the-three-table-relationship-between-file-descriptors-open-file-descriptions-and-inodes-what-happens-during-fork-and-dup) |
| 05 | RAID 5 write hole -- danger and mitigations | [Q6](05-lvm.md#q6-explain-the-raid-5-write-hole-why-is-it-dangerous-and-what-mitigations-exist) |
| 06 | Conntrack: what it is, why it matters, how to tune it | [Q5](06-networking.md#q5-what-is-conntrack-and-why-does-it-matter-in-production-how-do-you-size-and-tune-it) |
| 07 | Seccomp-BPF and Docker's default seccomp profile | [Q9](07-kernel-internals.md#q9-what-is-seccomp-bpf-and-how-does-dockers-default-seccomp-profile-work) |
| 08 | eBPF architecture -- why it is safe in production kernels | [Q4](08-performance-and-debugging.md#q4-explain-the-ebpf-architecture-why-is-it-safe-to-run-in-the-production-kernel) |
| 09 | Linux audit framework for SOC2/PCI compliance | [Q6](09-security.md#q6-explain-the-linux-audit-framework-how-would-you-configure-it-for-soc2pci-compliance) |
| 10 | Design a fleet-wide kernel upgrade for 50,000 hosts | [Q5](10-system-design-scenarios.md#q5-design-a-fleet-wide-kernel-upgrade-process-for-50000-hosts-with-zero-user-facing-downtime) |
| 11 | Diagnosing cascading OOM across a microservice fleet | [Q4](11-sre-incidents.md#q4-walk-through-how-you-would-diagnose-a-cascading-oom-failure-across-a-microservice-fleet) |

### Principal (L7+/E7+) -- Architecture and Deep Kernel Knowledge

Expected for Principal and Distinguished Engineer roles. These test design judgment and expert-level depth.

| Topic | Question | Link |
|-------|----------|------|
| 00 | What happens at the CPU level during a syscall on x86_64 | [Q3](00-fundamentals.md#q3-walk-through-exactly-what-happens-at-the-cpu-level-when-a-user-space-process-makes-a-system-call-on-x86_64) |
| 00 | Power-on to login prompt -- maximum detail | [Q8](00-fundamentals.md#q8-describe-what-happens-from-power-on-to-a-login-prompt-at-the-maximum-level-of-detail) |
| 01 | Maximum number of processes -- all limits that apply | [Q17](01-process-management.md#q17-what-is-the-maximum-number-of-processes-a-linux-system-can-run-what-are-all-the-limits-that-apply) |
| 02 | SCHED_DEADLINE: runtime, deadline, period, admission control | [Q5](02-cpu-scheduling.md#q5-describe-the-three-parameters-of-sched_deadline-runtime-deadline-period-and-how-the-kernels-admission-control-works) |
| 03 | NUMA latency regression after kernel upgrade | [Q9](03-memory-management.md#q9-your-team-runs-a-service-on-numa-aware-hardware-after-a-kernel-upgrade-p99-latency-doubles-memory-usage-and-cpu-usage-appear-unchanged-where-do-you-look) |
| 04 | Complete I/O path from write() to NVMe persistence | [Q13](04-filesystem-and-storage.md#q13-explain-the-complete-io-path-from-a-userspace-write-to-data-persisting-on-an-nvme-ssd) |
| 05 | Design storage layout for HA database cluster (LVM+RAID) | [Q16](05-lvm.md#q16-explain-how-you-would-design-the-storage-layout-for-a-high-availability-database-cluster-using-lvm-and-raid) |

---

## Questions by Type

### Conceptual (Test your mental model)

These ask you to explain how something works. Structure your answer: definition, internal mechanism, why it matters.

- [00-Q1](00-fundamentals.md): Monolithic vs. microkernel
- [01-Q1](01-process-management.md): PID vs. TGID
- [02-Q2](02-cpu-scheduling.md): How CFS calculates time slices
- [03-Q1](03-memory-management.md): Page cache vs. buffer cache
- [04-Q1](04-filesystem-and-storage.md): VFS layer and its four core objects
- [06-Q1](06-networking.md): TCP connection lifecycle
- [07-Q3](07-kernel-internals.md): cgroups v2 unified hierarchy
- [08-Q2](08-performance-and-debugging.md): USE method vs. RED method
- [09-Q1](09-security.md): DAC vs. MAC

### Scenario (Test your debugging approach)

These give you a production situation and ask you to investigate. Structure: symptoms, hypothesis, commands, root cause, fix, prevention.

- [00-Q7](00-fundamentals.md): 10,000 nodes with 3-minute boot times (SLO: 45s)
- [01-Q6](01-process-management.md): 5,000 zombie processes on production server
- [02-Q9](02-cpu-scheduling.md): Container throughput 30% lower than bare-metal
- [03-Q8](03-memory-management.md): Container OOM-killed with half its memory limit in heap
- [04-Q7](04-filesystem-and-storage.md): df shows 100% full, du shows 60% used
- [06-Q18](06-networking.md): 5-second DNS timeouts in Kubernetes
- [07-Q10](07-kernel-internals.md): Container cannot reach the network
- [08-Q9](08-performance-and-debugging.md): Load average 64, CPU 10% -- what is happening?
- [10-Q12](10-system-design-scenarios.md): Intermittent OOM kills on Kubernetes nodes
- [11-Q12](11-sre-incidents.md): 2-second service call, 5ms downstream response

### Debugging (Test your command-line skills)

These focus on the specific tools and commands you would use.

- [01-Q10](01-process-management.md): What is a D-state process waiting for?
- [02-Q11](02-cpu-scheduling.md): Using `perf sched` for scheduling latency
- [03-Q12](03-memory-management.md): Investigating a kernel slab memory leak
- [04-Q11](04-filesystem-and-storage.md): "Too many open files" diagnosis
- [06-Q15](06-networking.md): Intermittent packet loss in a cloud environment
- [08-Q5](08-performance-and-debugging.md): Generating and interpreting a CPU flame graph
- [08-Q12](08-performance-and-debugging.md): D-state process debugging
- [09-Q2](09-security.md): SELinux troubleshooting when access is denied
- [11-Q13](11-sre-incidents.md): Slow network vs. slow application

### Trick Questions (Test precision under pressure)

These have counterintuitive answers. Know them cold -- interviewers use these to separate strong from exceptional candidates.

- [01-Q14](01-process-management.md): Can a zombie process be killed with `kill -9`? (No.)
- [02-Q15](02-cpu-scheduling.md): Load average 4 on 8 cores -- under/over/properly loaded? (Depends.)
- [02-Q16](02-cpu-scheduling.md): Nice -20 means "all the CPU"? (No.)
- [03-Q15](03-memory-management.md): 20 GiB VSZ, 50 MiB RSS -- excessive memory? (No.)
- [03-Q16](03-memory-management.md): swappiness=0 means Linux never swaps? (No.)
- [04-Q16](04-filesystem-and-storage.md): sync vs. fsync() vs. fdatasync()
- [05-Q17](05-lvm.md): /dev/mapper/vg-lv vs. /dev/vg/lv vs. /dev/dm-N
- [08-Q7](08-performance-and-debugging.md): What does %util in iostat actually measure? (Misleading on NVMe.)

---

## Recommended Study Order

Follow this order to build concepts progressively. Each topic depends on the ones before it.

```
00 Fundamentals          (foundation for everything)
  |
  +-> 01 Process Management    (builds on kernel architecture)
  +-> 03 Memory Management     (builds on virtual memory from 00)
  |
  +-> 02 CPU Scheduling        (builds on process states from 01)
  +-> 04 Filesystem & Storage  (builds on kernel I/O from 00)
  |
  +-> 05 LVM                   (builds on storage from 04)
  +-> 06 Networking            (builds on kernel internals from 00)
  |
  +-> 07 Kernel Internals      (builds on all of 00-06)
  +-> 09 Security              (builds on kernel internals from 07)
  |
  +-> 08 Performance           (uses all previous topics)
  |
  +-> 10 System Design         (applies everything at scale)
  +-> 11 SRE Incidents         (real-world application of all topics)
```

---

## Top 10 Most Likely to Be Asked

These are the questions that come up most frequently across SRE interviews at major tech companies. Know these first.

| Rank | Question | Topic | Link |
|------|----------|-------|------|
| 1 | Walk through debugging a slow server -- systematic methodology | 08 Performance | [Q1](08-performance-and-debugging.md) |
| 2 | What happens from power-on to login prompt? | 00 Fundamentals | [Q8](00-fundamentals.md) |
| 3 | Explain the difference between load average and CPU utilization | 02 CPU Scheduling | [Q1](02-cpu-scheduling.md) |
| 4 | Explain RSS, VSZ, PSS, USS -- which for capacity planning? | 03 Memory | [Q3](03-memory-management.md) |
| 5 | Walk through the TCP connection lifecycle | 06 Networking | [Q1](06-networking.md) |
| 6 | TIME_WAIT vs. CLOSE_WAIT -- why is CLOSE_WAIT a bug? | 06 Networking | [Q2](06-networking.md) |
| 7 | df shows 100% full but du shows 60% used -- investigate | 04 Filesystem | [Q7](04-filesystem-and-storage.md) |
| 8 | Why can SIGKILL fail to kill a process? | 01 Process Mgmt | [Q4](01-process-management.md) |
| 9 | Explain SLI, SLO, SLA, and error budgets | 11 SRE Incidents | [Q6](11-sre-incidents.md) |
| 10 | What is the OOM killer? How does the kernel choose? | 08 Performance | [Q18](08-performance-and-debugging.md) |
