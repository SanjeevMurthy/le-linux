# Cheatsheet 07: Kernel Internals (Modules, cgroups, Namespaces)

> Quick reference for senior SRE/Cloud Engineer interviews and production work.
> Full notes: [Kernel Internals](../07-kernel-internals/kernel-internals.md)

---

<!-- toc -->
## Table of Contents

- [Kernel Module Management](#kernel-module-management)
- [Kernel Tuning (sysctl)](#kernel-tuning-sysctl)
- [cgroups v2 Operations](#cgroups-v2-operations)
- [cgroup v2 Key Files Quick Reference](#cgroup-v2-key-files-quick-reference)
- [Namespace Operations](#namespace-operations)
- [Namespace Type Reference](#namespace-type-reference)
- [Container Security Primitives](#container-security-primitives)
- [Emergency Debugging](#emergency-debugging)

<!-- toc stop -->

## Kernel Module Management

```bash
lsmod                                      # List all loaded modules
lsmod | grep -i nvidia                     # Check specific module
modinfo e1000e                             # Full module details (deps, vermagic, signer)
modinfo -F depends bluetooth               # Dependencies only
modinfo -F vermagic ext4                   # ABI compatibility check
modinfo -F signer nvidia                   # Signing authority

sudo modprobe e1000e                       # Load module (resolves dependencies)
sudo modprobe -r snd_usb_audio             # Remove module (refcount must be 0)
sudo modprobe bonding mode=4 miimon=100    # Load with parameters
sudo depmod -a                             # Rebuild modules.dep after kernel update

# Module blacklisting
echo "blacklist nouveau" | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
echo "install nouveau /bin/true" | sudo tee -a /etc/modprobe.d/blacklist-nouveau.conf
sudo dracut --force                        # Rebuild initramfs (RHEL)
sudo update-initramfs -u                   # Rebuild initramfs (Debian/Ubuntu)

# Taint checking
cat /proc/sys/kernel/tainted               # 0 = clean kernel
# Key bits: 0=proprietary(P), 1=forced(F), 12=out-of-tree(O), 13=unsigned(E)

# Module signing (Secure Boot)
sudo kmodsign sha512 /path/private.pem /path/public.der module.ko
sudo mokutil --import /path/public.der     # Enroll signing key
```

## Kernel Tuning (sysctl)

```bash
sysctl -a                                  # List all tunable parameters
sysctl net.ipv4.ip_forward                 # Read specific parameter
sudo sysctl -w net.ipv4.ip_forward=1       # Set at runtime (non-persistent)
sudo sysctl -p /etc/sysctl.d/99-custom.conf  # Apply config file
sudo sysctl --system                       # Reload all sysctl.d/ files

# Key container-host sysctls
# kernel.pid_max = 4194304
# vm.overcommit_memory = 0
# vm.panic_on_oom = 0
# net.ipv4.ip_forward = 1
# net.bridge.bridge-nf-call-iptables = 1
# fs.inotify.max_user_instances = 8192
# fs.inotify.max_user_watches = 524288
```

## cgroups v2 Operations

```bash
# Check cgroup version
stat -fc %T /sys/fs/cgroup/                # cgroup2fs = v2, tmpfs = v1
mount | grep cgroup                        # Mount details

# View hierarchy
systemd-cgls                               # Full cgroup tree
systemd-cgls --unit nginx.service          # Specific service
systemd-cgtop                              # Real-time resource usage per cgroup

# Read cgroup state
cat /sys/fs/cgroup/system.slice/nginx.service/memory.current
cat /sys/fs/cgroup/system.slice/nginx.service/memory.max
cat /sys/fs/cgroup/system.slice/nginx.service/cpu.max
cat /sys/fs/cgroup/system.slice/nginx.service/cpu.stat     # nr_throttled
cat /sys/fs/cgroup/system.slice/nginx.service/pids.current
cat /sys/fs/cgroup/system.slice/nginx.service/pids.max
cat /sys/fs/cgroup/system.slice/nginx.service/memory.events # oom, oom_kill counts

# PSI (Pressure Stall Information) -- v2 only
cat /sys/fs/cgroup/system.slice/nginx.service/cpu.pressure
cat /sys/fs/cgroup/system.slice/nginx.service/memory.pressure
cat /sys/fs/cgroup/system.slice/nginx.service/io.pressure
# Output: some avg10=X avg60=Y avg300=Z total=T

# Manual cgroup creation
sudo mkdir -p /sys/fs/cgroup/myapp/worker
echo "+cpu +memory +pids" | sudo tee /sys/fs/cgroup/myapp/cgroup.subtree_control
echo "200000 100000" | sudo tee /sys/fs/cgroup/myapp/worker/cpu.max    # 2 CPUs
echo "536870912" | sudo tee /sys/fs/cgroup/myapp/worker/memory.max     # 512M
echo "512" | sudo tee /sys/fs/cgroup/myapp/worker/pids.max             # 512 procs
echo $$ | sudo tee /sys/fs/cgroup/myapp/worker/cgroup.procs            # Move self

# systemd resource control
sudo systemctl set-property nginx.service MemoryMax=2G
sudo systemctl set-property nginx.service CPUQuota=200%
sudo systemctl set-property nginx.service TasksMax=512

# Docker resource limits
docker run -d --name app \
  --memory=512m --memory-swap=1g \
  --cpus=2 --cpu-shares=512 \
  --pids-limit=256 \
  nginx:latest
```

## cgroup v2 Key Files Quick Reference

| File | Purpose | Example |
|------|---------|---------|
| `cgroup.controllers` | Available controllers | `cpu memory io pids` |
| `cgroup.subtree_control` | Enabled for children | Write: `+cpu +memory` |
| `cgroup.procs` | PIDs in this cgroup | Write PID to move |
| `cpu.max` | Bandwidth: quota period | `250000 100000` = 2.5 CPUs |
| `cpu.weight` | Proportional share | `1`-`10000`, default `100` |
| `cpu.stat` | Throttling counters | `nr_throttled`, `throttled_usec` |
| `memory.max` | Hard limit (OOM kill) | `536870912` (512M) |
| `memory.high` | Throttle threshold | `429496729` (~410M) |
| `memory.current` | Current usage (r/o) | bytes |
| `memory.events` | OOM counters | `oom`, `oom_kill` |
| `memory.pressure` | PSI metrics | `some avg10=...` |
| `memory.swap.max` | Swap limit | `0` = no swap |
| `io.max` | Per-device BPS/IOPS | `8:0 rbps=10485760` |
| `pids.max` | Process limit | `512` |
| `pids.current` | Current count (r/o) | integer |

## Namespace Operations

```bash
# List namespaces
lsns                                       # All namespaces on system
lsns -t net                                # Network namespaces only
lsns -t pid                                # PID namespaces only
lsns -p <pid>                              # Namespaces for specific process

# View process namespaces
ls -la /proc/<pid>/ns/                     # Inode links
readlink /proc/<pid>/ns/net                # Compare: same inode = same NS

# Create namespaces with unshare
sudo unshare --pid --fork --mount-proc bash     # Isolated PID NS
sudo unshare --net bash                          # Isolated network NS
sudo unshare --uts bash                          # Isolated hostname NS
sudo unshare --mount bash                        # Isolated mount table
sudo unshare --user --map-root-user bash         # User NS (rootless)
sudo unshare --pid --fork --net --mount --uts --ipc --mount-proc bash  # Full isolation

# Enter existing namespaces with nsenter
nsenter -t <pid> --all -- /bin/sh          # Enter ALL namespaces of PID
nsenter -t <pid> -n                         # Network namespace only
nsenter -t <pid> -m                         # Mount namespace only
nsenter -t <pid> -p -r                      # PID namespace with root dir
nsenter -t <pid> -m -u -i -p -n            # All major namespaces

# Docker container namespace entry (without docker exec)
PID=$(docker inspect -f '{{.State.Pid}}' <container>)
sudo nsenter -t $PID --all -- /bin/sh

# Network namespace management (ip netns)
sudo ip netns add testns
sudo ip netns list
sudo ip netns exec testns ip link show
sudo ip netns exec testns bash
sudo ip netns delete testns

# Create veth pair for network namespace
sudo ip link add veth-host type veth peer name veth-ns
sudo ip link set veth-ns netns testns
sudo ip addr add 10.0.0.1/24 dev veth-host
sudo ip link set veth-host up
sudo ip netns exec testns ip addr add 10.0.0.2/24 dev veth-ns
sudo ip netns exec testns ip link set veth-ns up
sudo ip netns exec testns ip route add default via 10.0.0.1
```

## Namespace Type Reference

| Type | `unshare` | `nsenter` | Clone Flag | Isolates |
|------|-----------|-----------|------------|----------|
| Mount | `--mount` | `-m` | `CLONE_NEWNS` | Filesystem mounts |
| UTS | `--uts` | `-u` | `CLONE_NEWUTS` | Hostname, domain |
| IPC | `--ipc` | `-i` | `CLONE_NEWIPC` | SysV IPC, POSIX MQs |
| PID | `--pid --fork` | `-p` | `CLONE_NEWPID` | Process IDs |
| Network | `--net` | `-n` | `CLONE_NEWNET` | Network stack |
| User | `--user` | `-U` | `CLONE_NEWUSER` | UID/GID maps |
| Cgroup | `--cgroup` | `-C` | `CLONE_NEWCGROUP` | Cgroup root view |
| Time | `--time` | `-T` | `CLONE_NEWTIME` | Monotonic clock |

## Container Security Primitives

```bash
# View process capabilities
cat /proc/<pid>/status | grep Cap
capsh --decode=00000000a80425fb             # Decode hex capability mask
getpcaps <pid>                              # Human-readable capabilities

# Docker capability management
docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE nginx
docker run --cap-add=SYS_PTRACE myapp      # For debugging only

# Seccomp profile
docker run --security-opt seccomp=default.json myapp    # Custom profile
docker run --security-opt seccomp=unconfined myapp      # Disable (dangerous)

# Check seccomp status of process
cat /proc/<pid>/status | grep Seccomp
# 0=disabled, 1=strict, 2=filter (BPF)
```

## Emergency Debugging

```bash
# Container OOM investigation
dmesg | grep -i "oom\|killed" | tail -20
journalctl -k | grep -i oom
CGROUP=$(cat /proc/<pid>/cgroup | head -1 | cut -d: -f3)
cat /sys/fs/cgroup${CGROUP}/memory.events
cat /sys/fs/cgroup${CGROUP}/memory.pressure

# Container namespace debugging
lsns -p <pid>                              # What namespaces is it in?
nsenter -t <pid> -n ip addr show           # Network inside container
nsenter -t <pid> -n ss -tlnp               # Listening ports inside
nsenter -t <pid> -m cat /etc/resolv.conf   # DNS config inside

# Module / boot issues
cat /proc/sys/kernel/tainted               # Nonzero = investigate
dmesg | grep -i "module\|taint\|sig"
lsmod | wc -l                              # Module count
journalctl -u containerd -n 50 --no-pager

# cgroup version check
stat -fc %T /sys/fs/cgroup/                # cgroup2fs or tmpfs
systemd-cgls | head -30                    # Quick hierarchy view
```
