# Interview Questions 10: System Design Scenarios (Infrastructure, Containers, Fleet Management)

> FAANG / Staff+ SRE interview preparation. All answers structured with bullets/numbered lists.
> Full notes: [System Design Scenarios](../10-system-design-scenarios/system-design-scenarios.md)

---

## Q1: You are designing a log aggregation pipeline for 50,000 Linux hosts. Walk through your architecture and Linux-specific decisions.

1. **Collection layer (per host):**
   - Fluent Bit agent on every host (~10 MB RSS vs ~60 MB for Fluentd)
   - `systemd` input plugin reads journald with cursor-based tracking (exactly-once delivery)
   - `tail` input plugin for application log files using inotify-based file watching
   - `kmsg` input captures kernel ring buffer for hardware errors and OOM kills

2. **Transport:**
   - TLS-encrypted TCP from Fluent Bit to aggregation tier
   - 50,000 hosts x 10 KB/s = ~500 MB/s aggregate throughput
   - Consistent hash on hostname distributes to 200 aggregator nodes

3. **Aggregation:**
   - Vector or Fluentd instances parse (grok/regex), enrich (add `/etc/machine-id`, kernel version, cgroup path), filter (drop debug logs), and route to sinks
   - Disk-backed queues survive downstream outages

4. **Buffering:**
   - Kafka cluster with 3x replication, partitioned by host hash
   - Decouples ingest rate from indexing rate
   - 7-day retention enables replay for backfill or reprocessing

5. **Storage:**
   - Hot tier: Elasticsearch/OpenSearch on NVMe (30 days, searchable)
   - Warm tier: SSD (90 days)
   - Cold tier: Object storage (S3/GCS) in Parquet format (1 year, compliance)

6. **Linux-specific decisions:**
   - `journald.conf`: `RateLimitIntervalSec=0` (no log suppression during incidents), `SystemMaxUse=2G` (prevent journal filling root fs)
   - `logrotate` with `copytruncate` for applications holding file descriptors open
   - Fluent Bit local disk buffer (1 GB limit) survives aggregator outages

---

## Q2: Explain the complete chain from `kubectl run` to a running container process. Map each step to a Linux primitive.

1. **API Server:** Validates, authenticates, runs admission controllers, writes Pod spec to etcd
2. **Scheduler:** Evaluates node resources (from cgroup-reported allocatable), affinity, taints. Binds Pod to node.
3. **kubelet:** Watches API server for pods bound to this node. Calls containerd via CRI gRPC `RunPodSandbox`.
4. **containerd:** Pulls image layers (HTTP GET from OCI registry), stores in content-addressable filesystem. Prepares overlayfs mount (read-only image layers as `lowerdir`, writable `upperdir`).
5. **runc:** Reads OCI runtime-spec `config.json`. Calls `clone()` with `CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWCGROUP`.
6. **Namespaces created:** Private PID space (container PID 1), private network stack (veth pair), private mount table (`pivot_root()`), private hostname (UTS).
7. **cgroup attachment:** Creates `/sys/fs/cgroup/kubepods.slice/.../` directory. Writes `cpu.max`, `memory.max`, `pids.max`. Moves container PID into cgroup via `cgroup.procs`.
8. **seccomp-bpf:** Applies syscall filter via `prctl(PR_SET_SECCOMP)`. Default Kubernetes profile blocks ~44 dangerous syscalls.
9. **exec:** `execve()` the container entrypoint. Process runs as PID 1 inside PID namespace, constrained by cgroups and seccomp, with overlayfs rootfs.

---

## Q3: Compare bare metal, VMs, containers, and containers-on-VMs. When would you recommend each?

- **Bare metal:**
  - Use for: HPC, GPU/ML training, latency-critical workloads, regulatory dedicated-hardware requirements
  - Isolation: Physical (strongest)
  - Startup: Minutes (PXE + OS install)
  - Density: 1 workload per host
  - Linux relevance: Direct hardware access, custom kernel tuning (IRQ affinity, hugepages, `sysctl`)

- **Virtual machines:**
  - Use for: Multi-tenant cloud platforms, mixed OS, workloads needing separate kernels
  - Isolation: Hypervisor (separate kernel per VM, kernel vulnerability isolated)
  - Startup: 5-30 seconds
  - Density: 10-50 VMs per host
  - Linux relevance: KVM turns Linux kernel into hypervisor. VMs are regular processes. `virtio` for near-native I/O.

- **Containers:**
  - Use for: Microservices, CI/CD pipelines, high-density stateless workloads
  - Isolation: Namespace + cgroup (shared kernel is the attack surface)
  - Startup: 50-500 ms
  - Density: 100-1000 per host
  - Linux relevance: `clone()`, `pivot_root()`, overlayfs, seccomp-bpf, capabilities

- **Containers-on-VMs (recommended default for production):**
  - Combines container density with VM isolation
  - Kernel vulnerability blast radius limited to one VM
  - Live migration at VM layer for host maintenance
  - Used by all major cloud providers for managed Kubernetes (GKE, EKS, AKS)

---

## Q4: How do cgroupv2 controllers provide multi-tenant resource isolation? Detail the specific controllers and their semantics.

1. **CPU controller:**
   - `cpu.weight` (1-10000): Proportional sharing during contention. Tenant A at 5000 gets 2x CPU of tenant B at 2500.
   - `cpu.max` (quota period): Hard ceiling. `200000 100000` = 2 CPUs max.
   - `cpu.stat`: Reports `nr_throttled` and `throttled_usec` -- SLI for CPU starvation.

2. **Memory controller:**
   - `memory.min`: Hard guarantee. Kernel never reclaims below this. Essential for guaranteed-tier tenants.
   - `memory.low`: Soft protection. Kernel avoids reclaim but will under extreme pressure.
   - `memory.high`: Throttle point. Exceeding triggers direct reclaim (slows, does not kill).
   - `memory.max`: Hard limit. Triggers OOM killer scoped to cgroup.
   - `memory.events`: Counters for `low`, `high`, `max`, `oom`, `oom_kill`. Monitor via inotify.

3. **I/O controller:**
   - `io.weight` (1-10000): Proportional I/O via BFQ scheduler.
   - `io.max`: Hard IOPS/bandwidth per device (`rbps`, `wbps`, `riops`, `wiops`).
   - `io.latency`: Target latency controller -- kernel throttles siblings to meet target.

4. **PIDs controller:**
   - `pids.max`: Limits process/thread count. Prevents fork bombs.

5. **Hierarchy:** cgroupv2 single unified hierarchy. Parent limits cap all children. Tenant slice `memory.max` bounds all pods regardless of individual limits.

---

## Q5: Design a fleet-wide kernel upgrade process for 50,000 hosts with zero user-facing downtime.

1. **Build and test:**
   - Custom kernel config in CI pipeline
   - QEMU boot test (kernel boots, modules load, basic syscall verification)
   - Regression suite: network, filesystem, cgroup, custom module compatibility
   - Kernel + initramfs signed (Secure Boot chain)
   - Out-of-tree modules (nvidia.ko, mlx5_core.ko) compiled against new headers

2. **Canary phase (0.1%, 50 hosts, 48-72 hours):**
   - Mix: Kubernetes nodes, database servers, GPU hosts
   - Monitor: `dmesg` error count, workload p99 latency, OOM kill rate, module load success
   - Circuit breaker: any regression halts rollout globally

3. **Staged rollout (1% -> 10% -> 50% -> 100%):**
   - Per host: `kubectl drain` (respect PDBs), `kexec -l` new kernel, `kexec -e` (skip BIOS), verify `uname -r`, `kubectl uncordon`
   - `kexec` reduces reboot from 3-5 min to 15-30 sec
   - AZ-aware: never exceed 33% per AZ simultaneously
   - Monitoring gate between each stage

4. **Rollback:**
   - GRUB default set to old kernel before kexec
   - If post-boot checks fail, standard reboot falls back automatically
   - Time to rollback: < 5 minutes per host
   - `panic=10` kernel param: auto-reboot on kernel panic

5. **Stateful hosts:** Live migration (VMs), kernel live patching (`kpatch`/`livepatch`) for security-only, or scheduled maintenance windows.

---

## Q6: What is the difference between `memory.min`, `memory.low`, `memory.high`, and `memory.max`? Design a config for a production Java service.

- **`memory.min`**: Hard guarantee. Kernel will NEVER reclaim below this, even under extreme global pressure. Use for guaranteed-tier tenants and critical services.
- **`memory.low`**: Soft guarantee. Kernel avoids reclaim but will if no other option. Use for best-effort protection of file cache.
- **`memory.high`**: Throttle point. Exceeding triggers direct reclaim (slows allocation, does not OOM-kill). Provides a warning zone for GC to run.
- **`memory.max`**: Hard limit. Exceeding triggers OOM killer scoped to this cgroup. Final safety net.

- **Production configuration (Java, 4 GiB heap):**
  ```
  memory.min  = 4 GiB    # JVM heap guaranteed, never reclaimed
  memory.low  = 4.5 GiB  # Soft protection for JVM file cache (mmap'd JARs)
  memory.high = 5 GiB    # Throttle triggers GC pressure before OOM
  memory.max  = 5.5 GiB  # OOM kill -- JVM should never reach here if high works
  ```
- **Rationale:** Gap between `high` and `max` gives JVM time to GC. Gap between `min` and `low` protects page cache for mmap'd files.

---

## Q7: How would you detect and remediate configuration drift across 10,000 Linux hosts?

1. **Detection:**
   - CM dry-run: `ansible-playbook --check --diff` fleet-wide. Report hosts where changes would be applied.
   - File integrity: `aide --check` or `osquery` comparing `/etc/`, `/boot/`, sysctl values against golden baseline
   - Kernel parameter drift: `sysctl -a | sha256sum` per host, compare fleet-wide
   - Package version drift: `rpm -qa --qf '%{NAME}-%{VERSION}\n' | sort | sha256sum` per host

2. **Remediation:**
   - **Convergent:** CM runs every 30 minutes, enforces desired state, reverts manual changes
   - **Immutable:** Build new image, rolling-replace hosts. Drift impossible by construction.
   - **Hybrid:** Immutable base OS + convergent management for runtime config (certs, DNS, feature flags)

3. **Prevention:**
   - Disable SSH for humans in production (all changes via automation)
   - `auditd` rules on `/etc/` for unauthorized modifications
   - Break-glass procedure with mandatory post-incident CM sync

---

## Q8: Design the networking layer for a container platform. How do containers on different hosts communicate?

1. **Single-host networking:**
   - Linux bridge (`ip link add cni0 type bridge`) with per-host subnet (e.g., 10.244.1.0/24)
   - veth pair per container: one end in container network namespace, other attached to bridge
   - NAT via iptables/nftables for egress

2. **Cross-host connectivity (overlay):**
   - VXLAN: `ip link add vxlan0 type vxlan id 42 dstport 4789 dev eth0`
   - Per-host pod subnet (host1=10.244.1.0/24, host2=10.244.2.0/24)
   - Host routing: `ip route add 10.244.2.0/24 via <host2-ip> dev vxlan0`
   - MTU: VXLAN adds 50-byte overhead. Inner MTU = 1450 if outer = 1500.

3. **eBPF-based (Cilium):**
   - Replaces iptables with eBPF at TC hooks: O(1) policy lookup vs O(n) iptables
   - Transparent encryption (WireGuard/IPsec at kernel level)
   - L7 visibility (HTTP, gRPC, DNS) without sidecars

4. **Network policy:**
   - Default deny all ingress/egress per namespace
   - Explicit allowlists via NetworkPolicy/CiliumNetworkPolicy
   - Critical for multi-tenant isolation

---

## Q9: What is an error budget and how does it drive infrastructure decisions? Give concrete examples.

1. **Definition:** Error budget = 1 - SLO. If SLO is 99.9% availability, error budget is 0.1% = ~43.2 minutes/month.

2. **Decision framework:**
   - Budget available: Ship features, run chaos experiments, perform kernel upgrades
   - Budget near exhaustion: Freeze deployments, prioritize reliability engineering
   - Budget exceeded: All effort to reliability restoration. No new features. Postmortem required.

3. **Concrete infrastructure examples:**
   - Kernel upgrade: each host reboot = brief unavailability. Consumes error budget. Schedule when budget is healthy.
   - Chaos engineering: killing nodes, injecting latency funded by error budget. Stop when budget is low.
   - Overcommit ratio: aggressive 8:1 CPU overcommit increases noisy-neighbor risk, consuming budget through latency violations.
   - Deployment rollout: canary failure burns budget. Rollback quickly to preserve remaining budget.

4. **Measurement infrastructure:**
   - Probe-based SLIs (synthetic requests), log-based SLIs (5xx/total from access logs)
   - Per-tenant error budgets tracked independently
   - Grafana dashboard with burn-down chart showing remaining budget

---

## Q10: Explain PSI (Pressure Stall Information). How would you use it for fleet-wide capacity planning?

1. **What PSI measures:**
   - `/proc/pressure/cpu`: Time tasks stalled waiting for CPU
   - `/proc/pressure/memory`: Time tasks stalled in memory reclaim or swap
   - `/proc/pressure/io`: Time tasks stalled on I/O
   - Two metrics: `some` (at least one task stalled) and `full` (all tasks stalled)
   - Reported as 10s, 60s, 300s moving averages

2. **Why PSI is superior to utilization:**
   - CPU at 90% with 0% PSI = high throughput, no stalling, healthy
   - CPU at 50% with 30% PSI = CFS bandwidth throttling, users impacted
   - PSI directly measures user-visible impact, not just consumption

3. **Capacity planning:**
   - Export via node_exporter to Prometheus
   - Alert: `some > 25%` sustained 5 min (early overcommit warning)
   - Alert: `full > 10%` for 1 min (critical: host unusable)
   - Fleet heatmap: PSI values by cluster/AZ/tenant
   - Trend: if median CPU `some` rising 2%/week, add capacity before alert threshold

4. **Per-cgroup PSI:** Available at tenant/pod level for per-tenant capacity decisions

---

## Q11: How would you build a container from scratch using only Linux primitives?

1. **Prepare rootfs:** `debootstrap --variant=minbase bookworm /rootfs` or extract Alpine tarball

2. **Create namespaces via `clone()`:**
   - `CLONE_NEWPID` -- private PID space (entrypoint sees PID 1)
   - `CLONE_NEWNS` -- private mount table
   - `CLONE_NEWUTS` -- private hostname
   - `CLONE_NEWNET` -- private network stack
   - `CLONE_NEWIPC` -- private IPC
   - `CLONE_NEWCGROUP` -- private cgroup view

3. **Inside the new process:**
   - `sethostname("container")` -- set hostname
   - `mount("proc", "/rootfs/proc", "proc", 0, NULL)` -- mount procfs
   - `pivot_root("/rootfs", "/rootfs/.old_root")` -- switch root
   - `umount2("/.old_root", MNT_DETACH)` -- detach host root
   - `mount("tmpfs", "/tmp", "tmpfs", 0, "size=64M")` -- writable /tmp

4. **Attach cgroups:** `mkdir /sys/fs/cgroup/mycontainer`, write `cpu.max`, `memory.max`, `pids.max`, write PID to `cgroup.procs`

5. **Apply seccomp-bpf:** `prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog)` -- block dangerous syscalls

6. **Drop capabilities and exec:** Drop all caps except needed ones, `execve("/bin/sh")`

---

## Q12: You observe intermittent OOM kills on Kubernetes nodes. Investigate and resolve.

1. **Identify scope:** `dmesg | grep -i oom` -- per-pod (cgroup OOM) or system-wide?

2. **Check cgroup memory events:**
   ```bash
   find /sys/fs/cgroup/kubepods.slice -name memory.events -exec sh -c \
     'oom=$(grep oom_kill "$1" | awk "{print \$2}"); [ "$oom" -gt 0 ] && echo "$1: $oom"' _ {} \;
   ```

3. **Understand OOM victim selection:**
   - Guaranteed QoS: `oom_score_adj = -997` (almost never killed)
   - Burstable: `oom_score_adj = 2-999` (proportional)
   - BestEffort: `oom_score_adj = 1000` (killed first)

4. **Common root causes:**
   - `memory.max` too low for workload: increase limits in pod spec
   - Memory leak: profile with `jmap` (Java), `valgrind` (C), `go tool pprof` (Go)
   - Kernel memory not accounted: check `memory.stat` for `kernel` + `slab`
   - Node overcommit: sum of pods' limits > node allocatable
   - tmpfs (`/dev/shm`, secret volumes) counts against pod memory cgroup

5. **Prevention:**
   - Set `memory.high` below `memory.max` (throttle before kill)
   - VPA to right-size based on historical usage
   - Monitor `memory.events` for early `high`/`max` warnings

---

## Q13: Explain overlayfs and why it is critical for containers.

1. **How it works:**
   - Merges multiple directory layers into single view
   - `lowerdir`: read-only layers (container image layers)
   - `upperdir`: read-write layer (container's changes)
   - `workdir`: internal scratch space for atomic operations
   - `mount -t overlay overlay -o lowerdir=layer3:layer2:layer1,upperdir=rw,workdir=work /merged`

2. **Operations:**
   - Read: kernel searches upperdir first, then lowerdirs top-to-bottom. First match wins.
   - Write (copy-on-write): file from lower layer copied to upperdir, then modified. Lower layer untouched.
   - Delete: "whiteout" file created in upperdir, masking the lower layer file.

3. **Why it matters:**
   - 100 containers from same image share base layers on disk (deduplication)
   - Container startup is fast: no full image copy needed
   - Layer caching: 10 images with same base layer (e.g., `ubuntu:22.04`) store it once
   - At 1000 containers/host, saves terabytes of storage

4. **Gotcha:** inode exhaustion on ext4 (fixed at mkfs). Use XFS (dynamic inode allocation) for `/var/lib/containerd`.

---

## Q14: Design a multi-tenant compute platform with strong resource isolation for 200 teams.

1. **Isolation stack per tenant:**
   - Kubernetes namespace per tenant with `ResourceQuota` and `LimitRange`
   - cgroupv2 slice: `cpu.weight` (proportional), `cpu.max` (ceiling), `memory.min` (guaranteed), `memory.max` (limit), `pids.max`
   - NetworkPolicy: default deny-all, explicit allowlists
   - SELinux MCS labels: unique `s0:c<N>,c<M>` per tenant (cross-tenant access blocked at MAC level)
   - seccomp-bpf: deny `mount`, `ptrace`, `kexec_load`, `init_module`
   - Pod Security Standards: `restricted` profile enforced

2. **Noisy neighbor prevention:**
   - CPU: `cpu.weight` for fair sharing + `cpu.max` for ceiling
   - Memory: `memory.min` guarantees, `memory.high` for throttling
   - I/O: `io.weight` via BFQ + `io.max` for hard limits
   - Network: eBPF traffic shaping (Cilium) or `tc htb` qdisc
   - PIDs: `pids.max` prevents fork bombs

3. **Quota enforcement:**
   - Admission webhook rejects pods exceeding tenant quota
   - Overcommit ratios: CPU 4:1, memory 1.5:1
   - Minimum pod size enforced to prevent scheduling abuse

4. **Monitoring SLOs:**
   - Per-tenant scheduling latency: 99% < 10 seconds
   - Cross-tenant impact: no tenant sees >5% latency degradation from co-tenants
   - Security: 0 cross-tenant data access incidents

---

## Q15: How does the shared kernel in containers create security risks? How do you mitigate them?

1. **Risks:**
   - Kernel vulnerability affects ALL containers on the host (unlike VMs)
   - Container escape via kernel exploit grants host access
   - `/proc` and `/sys` expose host info if not masked
   - Privileged containers = root on host

2. **Mitigation layers (defense in depth):**
   - **User namespaces:** Container root maps to unprivileged host UID
   - **seccomp-bpf:** Block ~44 dangerous syscalls, reduces kernel attack surface ~50%
   - **Linux capabilities:** Drop all, grant only needed. Never `CAP_SYS_ADMIN`.
   - **SELinux/AppArmor:** MAC confinement, MCS labels prevent cross-container access
   - **Read-only rootfs:** No filesystem writes except tmpfs-backed paths
   - **VM isolation layer:** Containers-on-VMs limits blast radius to one VM
   - **Kata Containers / gVisor:** Lightweight VM or user-space kernel per container

3. **Operational practices:**
   - Pod Security Standards (`restricted` profile) enforced via admission controller
   - No `hostPID`, `hostNetwork`, `hostIPC` for tenant workloads
   - Regular kernel patching (live patching or rolling upgrades)
   - Runtime threat detection (Falco, Tetragon) for anomalous syscalls

---

## Q16: Describe immutable infrastructure. How does it interact with Linux system management?

1. **Definition:**
   - Servers never modified after deployment
   - Changes = build new image + replace old host
   - No SSH, no manual patching, no drift by construction

2. **Linux implementation:**
   - Base OS image built by Packer/image-builder (packages, kernel, config baked in)
   - `cloud-init` / `ignition` for per-instance config (hostname, IP, secrets) on first boot
   - Root filesystem read-only or dm-verity for integrity
   - Updates: build new image, rolling-replace (blue/green or canary)

3. **What still needs runtime configuration:**
   - TLS certificates (rotated frequently)
   - DNS resolver config (network-dependent)
   - Feature flags and tuning parameters
   - Secrets (from vault, not baked into images)

4. **Trade-offs:**
   - Advantage: no drift, auditable, rollback = deploy previous image
   - Disadvantage: requires mature image pipeline; stateful services need persistent volumes
   - Hybrid: immutable base OS + convergent CM for runtime config

---

## Q17: Design capacity planning for a platform serving 200 teams on shared infrastructure.

1. **Data collection:**
   - Per-tenant: CPU, memory, I/O, network from cgroup metrics
   - PSI per tenant and node
   - Scheduling latency: pod creation to running
   - Growth trends: weekly moving averages

2. **Capacity model:**
   - Minimum: sum of all tenants' `memory.min` + CPU guarantees
   - Burst headroom: +30-50% above guaranteed
   - N+1 per AZ (survive one node failure)
   - Bin-packing efficiency: 70-85% (fragmentation waste)

3. **Planning process:**
   - Quarterly review with growth projections
   - Lead time: cloud VMs (minutes), bare metal (weeks) -- order ahead
   - Charge-back per tenant based on guaranteed allocations
   - Reduce overcommit if fleet `some` CPU pressure > 15%

4. **Automation:**
   - Cluster auto-scaler for pending-pod overflow
   - VPA for right-sizing recommendations
   - Spot/preemptible for batch workloads
   - Alerts at 30/60/90 day capacity projections
