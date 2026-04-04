# Cheatsheet 10: System Design Scenarios (Infrastructure, Containers, Fleet Management)

> Quick reference for senior SRE/Cloud Engineer interviews and production work.
> Full notes: [System Design Scenarios](../10-system-design-scenarios/system-design-scenarios.md)

---

<!-- toc -->
## Table of Contents

- [Container Runtime Chain](#container-runtime-chain)
- [cgroupv2 Management](#cgroupv2-management)
- [Memory Hierarchy (cgroupv2)](#memory-hierarchy-cgroupv2)
- [Namespace Operations](#namespace-operations)
- [Networking for Containers](#networking-for-containers)
- [Fleet-Wide Operations](#fleet-wide-operations)
- [Isolation Spectrum](#isolation-spectrum)
- [SRE Quick Reference](#sre-quick-reference)
- [Log Pipeline Architecture](#log-pipeline-architecture)
- [Fleet Kernel Upgrade Checklist](#fleet-kernel-upgrade-checklist)
- [Critical Gotchas](#critical-gotchas)

<!-- toc stop -->

## Container Runtime Chain

```bash
# kubectl -> API Server -> Scheduler -> kubelet -> containerd -> runc -> Linux primitives
# Every container is: clone() + pivot_root() + cgroups + seccomp-bpf + overlayfs

# Kubernetes node inspection
kubectl get nodes -o wide                          # Node status, kernel, runtime
kubectl describe node <node>                       # Resources, taints, conditions
kubectl top nodes                                  # CPU/memory per node
kubectl debug node/<node> -it --image=busybox      # Debug shell on node

# Container runtime (crictl -- talks to containerd via CRI)
crictl ps                                          # Running containers
crictl pods                                        # Pod sandboxes
crictl inspect <id> | jq '.info.runtimeSpec.linux' # Namespace + cgroup config
crictl stats                                       # Container resource usage
crictl images                                      # Pulled images

# Low-level OCI runtime
runc list                                          # Containers under runc
runc state <id>                                    # PID, cgroup path, status
runc events <id>                                   # Live resource metrics
```

## cgroupv2 Management

```bash
# Hierarchy
/sys/fs/cgroup/                                    # Root
  kubepods.slice/                                  # All Kubernetes pods
    kubepods-burstable.slice/                      # Burstable QoS
      kubepods-burstable-pod<uid>.slice/           # Individual pod
        cri-containerd-<id>.scope/                 # Individual container

# Key files per cgroup
cat cpu.max                                        # Hard CPU limit (quota period)
cat cpu.weight                                     # Proportional CPU share (1-10000)
cat cpu.stat                                       # nr_throttled, throttled_usec
cat memory.max                                     # Hard memory limit (OOM)
cat memory.high                                    # Throttle point (before OOM)
cat memory.min                                     # Guaranteed (never reclaimed)
cat memory.low                                     # Best-effort protection
cat memory.current                                 # Current usage
cat memory.events                                  # oom, oom_kill, high, max counters
cat memory.stat                                    # Detailed breakdown (anon, file, slab)
cat pids.max                                       # Process limit (fork bomb defense)
cat pids.current                                   # Current process count
cat io.max                                         # Hard IOPS/BW limit per device
cat io.weight                                      # Proportional I/O share
cat io.pressure                                    # I/O PSI (some, full averages)
cat cpu.pressure                                   # CPU PSI
cat memory.pressure                                # Memory PSI

# Manual cgroup creation
mkdir /sys/fs/cgroup/mygroup
echo "+cpu +memory +io +pids" > /sys/fs/cgroup/mygroup/cgroup.subtree_control
echo "200000 100000" > /sys/fs/cgroup/mygroup/cpu.max         # 2 CPUs
echo "4294967296" > /sys/fs/cgroup/mygroup/memory.max          # 4 GiB
echo "2147483648" > /sys/fs/cgroup/mygroup/memory.high         # 2 GiB throttle
echo "1073741824" > /sys/fs/cgroup/mygroup/memory.min          # 1 GiB guaranteed
echo "500" > /sys/fs/cgroup/mygroup/pids.max                   # 500 processes
echo $$ > /sys/fs/cgroup/mygroup/cgroup.procs                  # Move shell into cgroup

# Find pods with OOM kills
find /sys/fs/cgroup/kubepods.slice -name memory.events -exec sh -c \
  'oom=$(grep oom_kill "$1" | awk "{print \$2}"); [ "$oom" -gt 0 ] && echo "$1: $oom"' _ {} \;
```

## Memory Hierarchy (cgroupv2)

```
memory.min  ---- Hard guarantee (kernel NEVER reclaims)
     |
memory.low  ---- Soft protection (kernel avoids reclaim, but will under extreme pressure)
     |
memory.high ---- Throttle (triggers direct reclaim, slows allocation, NO OOM kill)
     |
memory.max  ---- Hard limit (triggers OOM killer scoped to this cgroup)

Production example (Java 4G heap):
  memory.min  = 4G    # JVM heap guaranteed
  memory.high = 5G    # Throttle triggers GC before OOM
  memory.max  = 5.5G  # Safety net -- should never reach
```

## Namespace Operations

```bash
# Inspect namespaces
lsns                                               # All namespaces system-wide
lsns -t net                                        # Network namespaces only
ls -la /proc/<pid>/ns/                             # Namespace inodes for a process
readlink /proc/<pid>/ns/net                        # Namespace ID

# Enter container namespaces
nsenter -t <pid> -n ip addr show                   # Network namespace
nsenter -t <pid> -m -p ps aux                      # Mount + PID namespace
nsenter -t <pid> -a                                # All namespaces

# Create namespaces manually
unshare --mount --pid --fork --mount-proc bash     # New mount + PID ns
ip netns add testns                                # New network namespace
ip netns exec testns ip link                       # Run in network ns

# Correlate host PID to container PID
grep NSpid /proc/<host-pid>/status                 # Shows [host-PID, ns-PID]
```

## Networking for Containers

```bash
# Bridge networking (single host)
ip link add name cni0 type bridge                  # Create bridge
ip addr add 10.244.1.1/24 dev cni0                # Assign subnet
ip link set cni0 up

# veth pair (connect container to bridge)
ip link add veth0 type veth peer name veth0-c      # Create pair
ip link set veth0 master cni0                      # Attach to bridge
ip link set veth0-c netns <pid>                    # Move to container ns
nsenter -t <pid> -n ip addr add 10.244.1.2/24 dev veth0-c
nsenter -t <pid> -n ip link set veth0-c up

# VXLAN overlay (cross-host)
ip link add vxlan0 type vxlan id 42 dstport 4789 dev eth0
ip addr add 10.244.0.1/16 dev vxlan0
ip link set vxlan0 up
ip route add 10.244.2.0/24 via <host2-ip> dev vxlan0

# Conntrack (critical at scale)
conntrack -C                                       # Current entries
sysctl net.netfilter.nf_conntrack_max              # Max entries
sysctl net.netfilter.nf_conntrack_count            # Current count
# If dropping packets: increase nf_conntrack_max or use Cilium (bypasses conntrack)
```

## Fleet-Wide Operations

```bash
# Ansible ad-hoc (fleet inspection)
ansible all -m shell -a "uname -r"                     # Kernel versions
ansible all -m shell -a "cat /proc/pressure/cpu"        # CPU pressure fleet-wide
ansible all -m shell -a "systemctl is-active kubelet"   # kubelet health
ansible all -m shell -a "dmesg --level=err | tail -5"   # Recent kernel errors
ansible all -m shell -a "sysctl -a | sha256sum"         # Config drift detection

# kexec (fast kernel reboot -- skips BIOS)
kexec -l /boot/vmlinuz-6.6 --initrd=/boot/initramfs-6.6 --reuse-cmdline
kexec -e                                                # Execute loaded kernel

# Pre-kexec: set GRUB fallback
grub2-set-default 0                                     # Old kernel as fallback
grub2-editenv list                                      # Verify saved entry

# Drain Kubernetes node before maintenance
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data --timeout=300s
# After maintenance:
kubectl uncordon <node>
```

## Isolation Spectrum

| Level | Mechanism | Startup | Density | Kernel Shared? |
|---|---|---|---|---|
| Bare Metal | Physical | Minutes | 1/host | N/A |
| VM (KVM) | Hypervisor | Seconds | 10-50/host | No |
| Container | NS + cgroup | Milliseconds | 100-1000/host | Yes |
| Container-on-VM | Both | Seconds | Nested | No (per VM) |
| Kata/gVisor | MicroVM | ~100ms | 50-200/host | No |

## SRE Quick Reference

```
SLI = What you measure          (p99 latency, error rate, throughput)
SLO = What you target           (p99 < 200ms for 99.9% of windows)
SLA = What you contractually promise  (99.95% monthly, breach = credit)
Error Budget = 1 - SLO          (99.9% SLO = 43.2 min/month)

Budget healthy  --> Ship features, run chaos experiments, do upgrades
Budget low      --> Freeze deployments, invest in reliability
Budget burned   --> Full stop, postmortem, fix before shipping
```

## Log Pipeline Architecture

```
Host Layer:        journald + app logs --> Fluent Bit (10 MB RSS per host)
                                              |
Aggregation:       200x Vector/Fluentd nodes (parse, enrich, route)
                                              |
Buffer:            Kafka (3x replication, partitioned by host hash)
                                              |
Storage:           Hot: OpenSearch/ES (NVMe, 30 days)
                   Warm: SSD (90 days)
                   Cold: S3/GCS (1 year, Parquet)
                                              |
Query:             Grafana / Kibana dashboards + alerting
```

## Fleet Kernel Upgrade Checklist

```
[ ] Kernel built + signed in CI
[ ] QEMU boot test passed
[ ] Out-of-tree modules compiled (GPU, NIC drivers)
[ ] Canary: 0.1% fleet, mixed workloads, 48-72h soak
[ ] GRUB fallback configured (old kernel = default)
[ ] kexec tested on all hardware platforms
[ ] Circuit breaker: halt if >1% fail post-boot
[ ] AZ-aware: max 33% per AZ simultaneously
[ ] PDB-respected during kubectl drain
[ ] Staged: 1% -> 10% -> 50% -> 100%
[ ] Monitoring: dmesg errors, workload SLIs, OOM rate
[ ] Rollback tested: reboot -> falls back to old kernel
[ ] Error budget checked before starting rollout
```

## Critical Gotchas

```
cgroupv1/v2 mismatch     --> App misdetects memory, OOM-killed
conntrack table full      --> Packets dropped silently (dmesg: table full)
overlayfs inode exhaust   --> df shows space but df -i shows 100%
kexec + GPU/IOMMU         --> Devices not reinitialized, bad state
memory.high throttling    --> p99 spikes (not OOM, but slowdown)
DNS bootstrap race        --> Container starts before DNS pod ready
tmpfs in memory cgroup    --> /dev/shm counts against pod memory limit
```
