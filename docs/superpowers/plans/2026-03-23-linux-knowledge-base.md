# Linux Interview Knowledge Base — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a comprehensive Linux interview preparation knowledge base from 3 PDF source books, enriched with real-world production knowledge, for senior SRE/Cloud Engineer roles.

**Architecture:** Three-phase pipeline — Phase 0 extracts raw text from PDFs into searchable markdown. Phase 1 generates 12 topic files sequentially, each through a source-read + research + synthesis + review workflow. Phase 2 verifies each topic before committing. Each topic produces 3 files: main content (9 sections), cheatsheet, and interview questions.

**Tech Stack:** Python 3 + PyMuPDF for PDF extraction. Markdown for all output. Mermaid for diagrams.

**Spec:** `docs/superpowers/specs/2026-03-23-linux-interview-knowledge-base-design.md`

---

## Source Material Reference

### Book 1: How Linux Works (HLW) — 17 chapters, 465 pages
Path: `sources/How Linux Works_ What Every Superuser Should Know-No Starch Press (2021).pdf`

### Book 2: Linux Basics for Hackers (LBH) — 18 chapters, 267 pages
Path: `sources/Linux Basics for Hackers, 2nd Edition.pdf`

### Book 3: UNIX/Linux System Administration Handbook (ULSAH) — 31 chapters, 1885 pages
Path: `sources/UNIX and Linux System Administration Handbook-Addison-Wesley (2017).pdf`

### Topic-to-Chapter Source Map

| Topic | HLW Chapters | LBH Chapters | ULSAH Chapters |
|-------|-------------|-------------|----------------|
| 00-Fundamentals | Ch1 (Big Picture), Ch5 (Kernel Boots), Ch6 (User Space Starts) | Ch1 (Getting Started), Intro | Ch1 (Where to Start), Ch2 (Booting), Ch11 (Drivers/Kernel) |
| 01-Process Mgmt | Ch8 (Processes & Resources) | Ch6 (Process Management) | Ch4 (Process Control) |
| 02-CPU Scheduling | Ch8 (Resource Utilization) | — | Ch4 (nice/renice §4.5), Ch29 (Performance §29.4) |
| 03-Memory Mgmt | Ch8 (Resource Utilization) | — | Ch29 (Performance §29.6 memory checks) |
| 04-Filesystem | Ch3 (Devices), Ch4 (Disks/FS) | Ch10 (Filesystem/Storage) | Ch5 (The Filesystem), Ch20 (Storage §20.9-20.13) |
| 05-LVM | Ch4 (Disks/FS) | — | Ch20 (Storage §20.6-20.8 LVM/RAID) |
| 06-Networking | Ch9 (Network Config), Ch10 (Network Apps) | Ch3 (Networks) | Ch13 (TCP/IP), Ch15 (IP Routing), Ch16 (DNS) |
| 07-Kernel Internals | Ch17 (Virtualization) | Ch15 (Kernel/LKMs) | Ch11 (Drivers/Kernel), Ch25 (Containers §25.1 cgroups/ns) |
| 08-Perf/Debug | Ch8 (Resource Utilization) | — | Ch28 (Monitoring), Ch29 (Performance Analysis) |
| 09-Security | Ch7 (System Config) | Ch5 (Permissions), Ch13 (Secure/Anon) | Ch3 (Access Control), Ch27 (Security) |
| 10-SysDesign | Ch17 (Virtualization) | — | Ch9 (Cloud), Ch24 (Virtualization), Ch25 (Containers), Ch31 (DevOps) |
| 11-SRE Incidents | Cross-cutting | Cross-cutting | Ch29 (Performance), Ch28 (Monitoring), Ch27 (Security) |

---

## Phase 0: PDF Extraction & Setup

### Task 1: Adapt PDF extraction script for Linux books

**Files:**
- Create: `scripts/extract_pdfs.py` (adapted from `le-system-design/scripts/extract_pdfs.py`)

- [ ] **Step 1: Copy and adapt the extraction script**

Copy `extract_pdfs.py` from `le-system-design/scripts/` to `scripts/extract_pdfs.py`. Modify:
- Change `SOURCE_DIR` to `BASE_DIR / "sources"`
- Change `OUTPUT_DIR` to `BASE_DIR / "sources" / "extracted"`
- Replace the `BOOKS` list with:

```python
BOOKS = [
    {
        "pdf": SOURCE_DIR / "How Linux Works_ What Every Superuser Should Know-No Starch Press (2021).pdf",
        "output_dir": OUTPUT_DIR / "how-linux-works",
        "short_name": "HLW",
        "full_name": "How Linux Works: What Every Superuser Should Know (2021)",
        "has_toc": True,
    },
    {
        "pdf": SOURCE_DIR / "Linux Basics for Hackers, 2nd Edition.pdf",
        "output_dir": OUTPUT_DIR / "linux-basics-hackers",
        "short_name": "LBH",
        "full_name": "Linux Basics for Hackers, 2nd Edition",
        "has_toc": True,
    },
    {
        "pdf": SOURCE_DIR / "UNIX and Linux System Administration Handbook-Addison-Wesley (2017).pdf",
        "output_dir": OUTPUT_DIR / "ulsah",
        "short_name": "ULSAH",
        "full_name": "UNIX and Linux System Administration Handbook, 5th Edition (2017)",
        "has_toc": True,
    },
]
```

- Change Phase 0 gate from `books_succeeded >= 4` to `books_succeeded >= 3` (all 3 must succeed)
- Update print strings to reference "Linux Knowledge Base" instead of "System Design"

- [ ] **Step 2: Verify PyMuPDF is installed**

Run: `python3 -c "import fitz; print(fitz.__version__)"`
Expected: version >= 1.23.0. If not installed: `pip install pymupdf`

- [ ] **Step 3: Run extraction**

Run: `python3 scripts/extract_pdfs.py`
Expected: All 3 books extract successfully, manifest.json generated in `sources/extracted/`

- [ ] **Step 4: Validate extraction quality**

Check:
- `sources/extracted/how-linux-works/` contains ~17 chapter files
- `sources/extracted/linux-basics-hackers/` contains ~18 chapter files
- `sources/extracted/ulsah/` contains ~31 chapter files
- `manifest.json` shows `phase1_gate: true`
- Spot-check 2-3 files per book for content quality (not just headers)

Run: `cat sources/extracted/manifest.json`
Run: `wc -l sources/extracted/how-linux-works/*.md`
Run: `wc -l sources/extracted/ulsah/*.md`

- [ ] **Step 5: Commit extraction setup**

```bash
git add scripts/extract_pdfs.py
git commit -m "feat: add PDF extraction script adapted for Linux books"
```

Note: Do NOT commit the extracted markdown files (they are derived/generated content). Add `sources/extracted/` to `.gitignore`.

---

### Task 2: Create folder structure

**Files:**
- Create: `linux-notes/` directory tree
- Create: `.gitignore` updates

- [ ] **Step 1: Create the full directory structure**

```bash
mkdir -p linux-notes/{00-fundamentals,01-process-management,02-cpu-scheduling,03-memory-management,04-filesystem-and-storage,05-lvm,06-networking,07-kernel-internals,08-performance-and-debugging,09-security,10-system-design-scenarios,11-real-world-sre-usecases,cheatsheets,interview-questions}
```

- [ ] **Step 2: Update .gitignore**

Add to `.gitignore`:
```
sources/extracted/
.superpowers/
```

- [ ] **Step 3: Commit folder structure**

```bash
git add linux-notes/ .gitignore
git commit -m "feat: create linux-notes folder structure for knowledge base"
```

---

## Phase 1: Topic Generation (Sequential)

> **Each task below follows the same workflow:** Read source chapters → Web research → Synthesize 9-section markdown → Generate cheatsheet → Generate interview questions → Review → User approval → Commit.
>
> **Quality gates per topic (from spec §6):**
> - All 9 sections present and substantive
> - At least 2 Mermaid diagrams in Section 2 (all diagrams must be Mermaid — no ASCII art)
> - Mermaid debugging flowchart in Section 4
> - Minimum incident count met (5 for high-weight, 3 for medium-weight)
> - Minimum 15 interview questions across 4 categories
> - All syscalls, kernel structures, commands, and paths verified
> - Cross-references to related topics using relative markdown links
> - Target: 3,000-8,000 words (excluding code/diagrams)

---

### Task 3: Topic 00 — Fundamentals (Boot Process, Kernel Architecture, System Calls)

**Files:**
- Create: `linux-notes/00-fundamentals/fundamentals.md`
- Create: `linux-notes/cheatsheets/00-fundamentals.md`
- Create: `linux-notes/interview-questions/00-fundamentals.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch01-*.md` (The Big Picture)
- `sources/extracted/how-linux-works/ch05-*.md` (How the Linux Kernel Boots)
- `sources/extracted/how-linux-works/ch06-*.md` (How User Space Starts)
- `sources/extracted/ulsah/ch01-*.md` (Where to Start)
- `sources/extracted/ulsah/ch02-*.md` (Booting and System Management Daemons)
- `sources/extracted/ulsah/ch11-*.md` (Drivers and the Kernel)
- `sources/extracted/linux-basics-hackers/ch01-*.md` (Getting Started)

**Research topics:**
- Linux boot sequence deep dive (BIOS/UEFI → GRUB → kernel → initramfs → systemd)
- Kernel architecture: monolithic vs microkernel trade-offs
- System call mechanism: int 0x80 vs syscall/sysenter, vDSO
- Interview experiences: "What happens when you type a command?" is the #1 Linux interview question
- Modern boot: systemd-boot, secure boot, measured boot

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/00-fundamentals/fundamentals.md`**

Must include:
- §1 Concept: Linux architecture layers, kernel design philosophy, trade-offs of monolithic design
- §2 Kernel Deep Dive: Boot sequence internals (BIOS/UEFI→bootloader→kernel→init), syscall mechanism (user→kernel transition via `syscall` instruction), key data structures. Mermaid `sequenceDiagram` for boot sequence. Mermaid `flowchart TD` for syscall path through kernel.
- §3 Commands: `dmesg`, `journalctl -b`, `systemd-analyze`, `strace`, `uname -a`, `/proc/cmdline`, `/proc/version`
- §4 Debugging: Boot failure triage flowchart (Mermaid `flowchart TD`). Using `systemd-analyze blame`, rescue mode, `rd.break`
- §5 Incidents: 5 scenarios (boot loop from GRUB misconfiguration, initramfs missing driver, systemd dependency cycle, kernel panic from bad module, slow boot from disk fsck)
- §6 Questions: 15+ across 4 categories
- §7 Pitfalls: "load average includes D-state processes", "init=/bin/bash bypasses all security"
- §8 Pro Tips: kernel cmdline tuning, systemd optimization
- §9 Cheatsheet: boot sequence reference, key `/proc` files

- [ ] **Step 4: Write `linux-notes/cheatsheets/00-fundamentals.md`**
- [ ] **Step 5: Write `linux-notes/interview-questions/00-fundamentals.md`**
- [ ] **Step 6: Dispatch review agent for technical accuracy**
- [ ] **Step 7: Present to user for approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/00-fundamentals/ linux-notes/cheatsheets/00-fundamentals.md linux-notes/interview-questions/00-fundamentals.md
git commit -m "feat: add 00-fundamentals topic (boot, kernel arch, syscalls)"
```

---

### Task 4: Topic 01 — Process Management

**Files:**
- Create: `linux-notes/01-process-management/process-management.md`
- Create: `linux-notes/cheatsheets/01-process-management.md`
- Create: `linux-notes/interview-questions/01-process-management.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch08-*.md` (Processes & Resource Utilization)
- `sources/extracted/linux-basics-hackers/ch06-*.md` (Process Management)
- `sources/extracted/ulsah/ch04-*.md` (Process Control)

**Research topics:**
- Process lifecycle: `fork()` → `exec()` → `wait()` → `exit()`, `clone()` for threads
- `task_struct` internals: PID, TGID, state, mm, files, signals
- Zombie and orphan processes in production
- Signals: SIGKILL vs SIGTERM, signal handling internals
- Namespaces and PID isolation in containers
- Interview focus: "What is a zombie process and how do you fix it?"
- FAANG incidents: fork bombs, PID exhaustion, zombie accumulation

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/01-process-management/process-management.md`**

Must include:
- §2: Mermaid `stateDiagram-v2` for process states (Running/Sleeping/Stopped/Zombie/Dead). Mermaid `classDiagram` for `task_struct` key fields.
- §4: Mermaid `flowchart TD` for "high number of zombie processes" debugging tree
- §5: 5 incidents (fork bomb DoS, zombie accumulation from buggy daemon, PID namespace leak in containers, SIGKILL not working on D-state process, process stuck in uninterruptible sleep)
- Cross-references: [Fundamentals](../00-fundamentals/fundamentals.md), [CPU Scheduling](../02-cpu-scheduling/cpu-scheduling.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/01-process-management/ linux-notes/cheatsheets/01-process-management.md linux-notes/interview-questions/01-process-management.md
git commit -m "feat: add 01-process-management topic"
```

---

### Task 5: Topic 02 — CPU Scheduling

**Files:**
- Create: `linux-notes/02-cpu-scheduling/cpu-scheduling.md`
- Create: `linux-notes/cheatsheets/02-cpu-scheduling.md`
- Create: `linux-notes/interview-questions/02-cpu-scheduling.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch08-*.md` (Resource Utilization — CPU sections)
- `sources/extracted/ulsah/ch04-*.md` (§4.5 nice/renice)
- `sources/extracted/ulsah/ch29-*.md` (Performance Analysis — §29.4 stolen CPU)

**Research topics:**
- CFS (Completely Fair Scheduler): red-black tree, vruntime, weight calculation
- Real-time scheduling: SCHED_FIFO, SCHED_RR, SCHED_DEADLINE
- CPU affinity: `taskset`, `isolcpus`, NUMA awareness
- Load average deep dive: 1/5/15 min, includes D-state, comparison to CPU utilization
- Context switching overhead, voluntary vs involuntary
- cgroups v2 cpu controller: cpu.max, cpu.weight
- Interview: "Explain load average vs CPU usage" — one of the most common trick questions

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/02-cpu-scheduling/cpu-scheduling.md`**

Must include:
- §2: Mermaid `flowchart TD` for CFS scheduling decision path. Mermaid `graph TD` for run queue / red-black tree structure.
- §4: Mermaid `flowchart TD` for "high CPU / high load average" debugging decision tree
- §5: 5 incidents (CPU starvation from RT process, noisy neighbor in cgroups, load average spike with low CPU from I/O wait, context switch storm from thread pool misconfiguration, NUMA imbalance causing latency)
- Cross-references: [Process Management](../01-process-management/process-management.md), [Performance](../08-performance-and-debugging/performance-and-debugging.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/02-cpu-scheduling/ linux-notes/cheatsheets/02-cpu-scheduling.md linux-notes/interview-questions/02-cpu-scheduling.md
git commit -m "feat: add 02-cpu-scheduling topic"
```

---

### Task 6: Topic 03 — Memory Management

**Files:**
- Create: `linux-notes/03-memory-management/memory-management.md`
- Create: `linux-notes/cheatsheets/03-memory-management.md`
- Create: `linux-notes/interview-questions/03-memory-management.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch08-*.md` (Resource Utilization — memory sections)
- `sources/extracted/ulsah/ch29-*.md` (Performance Analysis — §29.6 memory checks)

**Research topics:**
- Virtual memory: page tables, TLB, MMU, huge pages (2MB/1GB)
- Physical memory zones: DMA, DMA32, Normal, HighMem
- Page cache vs buffer cache (unified since 2.4)
- OOM Killer: `oom_score`, `oom_score_adj`, cgroup OOM, earlyoom
- Memory overcommit: `vm.overcommit_memory`, `vm.overcommit_ratio`
- NUMA: node-local allocation, `numactl`, `numastat`
- Swap: swappiness, zswap, zram
- Memory reclaim: kswapd, direct reclaim, watermarks
- `/proc/meminfo` deep dive, `/proc/vmstat`, `/proc/buddyinfo`
- Interview: "Page cache vs buffer cache" is a classic senior-level question

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/03-memory-management/memory-management.md`**

Must include:
- §2: Mermaid `flowchart TD` for page fault handling (minor vs major). Mermaid `graph TD` for page table hierarchy (PGD→PUD→PMD→PTE). Mermaid `graph LR` for memory zones layout.
- §4: Mermaid `flowchart TD` for "OOM / high memory usage" debugging decision tree
- §5: 5 incidents (OOM killer targeting critical service, memory leak from page cache growth, NUMA imbalance causing latency spikes, swap storm from aggressive overcommit, transparent huge pages causing latency jitter)
- Cross-references: [Process Management](../01-process-management/process-management.md), [Kernel Internals](../07-kernel-internals/kernel-internals.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/03-memory-management/ linux-notes/cheatsheets/03-memory-management.md linux-notes/interview-questions/03-memory-management.md
git commit -m "feat: add 03-memory-management topic"
```

---

### Task 7: Topic 04 — Filesystem & Storage

**Files:**
- Create: `linux-notes/04-filesystem-and-storage/filesystem-and-storage.md`
- Create: `linux-notes/cheatsheets/04-filesystem-and-storage.md`
- Create: `linux-notes/interview-questions/04-filesystem-and-storage.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch03-*.md` (Devices)
- `sources/extracted/how-linux-works/ch04-*.md` (Disks and Filesystems)
- `sources/extracted/linux-basics-hackers/ch10-*.md` (Filesystem/Storage)
- `sources/extracted/ulsah/ch05-*.md` (The Filesystem)
- `sources/extracted/ulsah/ch20-*.md` (Storage — §20.9-20.13 Filesystems)

**Research topics:**
- VFS layer: `inode`, `dentry`, `superblock`, `file` structs
- Inode internals: direct/indirect blocks, extent trees (ext4)
- ext4 vs XFS vs Btrfs vs ZFS trade-offs in production
- Journaling: journal vs ordered vs writeback modes
- I/O schedulers: mq-deadline, BFQ, kyber, none
- `/proc/diskstats`, `iostat`, `blktrace`
- Hard links vs soft links: inode-level explanation
- File descriptor table → open file table → inode table path
- Interview: "What is an inode? What happens when you run out?"

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/04-filesystem-and-storage/filesystem-and-storage.md`**

Must include:
- §2: Mermaid `graph LR` for VFS architecture (userspace→VFS→ext4/XFS/NFS). Mermaid `graph TD` for inode structure with direct/indirect blocks.
- §4: Mermaid `flowchart TD` for "disk I/O bottleneck" debugging tree
- §5: 5 incidents (inode exhaustion from small files, journal corruption after power loss, I/O scheduler causing latency for database workload, filesystem full from deleted-but-open files, ext4 extent tree corruption)
- Cross-references: [LVM](../05-lvm/lvm.md), [Performance](../08-performance-and-debugging/performance-and-debugging.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/04-filesystem-and-storage/ linux-notes/cheatsheets/04-filesystem-and-storage.md linux-notes/interview-questions/04-filesystem-and-storage.md
git commit -m "feat: add 04-filesystem-and-storage topic"
```

---

### Task 8: Topic 05 — LVM & Disk Management

**Files:**
- Create: `linux-notes/05-lvm/lvm.md`
- Create: `linux-notes/cheatsheets/05-lvm.md`
- Create: `linux-notes/interview-questions/05-lvm.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch04-*.md` (Disks/FS — partitioning sections)
- `sources/extracted/ulsah/ch20-*.md` (Storage — §20.6 Partitioning, §20.7 LVM, §20.8 RAID)

**Research topics:**
- LVM architecture: PV → VG → LV, PE/LE mapping
- LVM snapshots, thin provisioning, striping
- RAID levels: 0, 1, 5, 6, 10 — trade-offs for production
- mdadm vs hardware RAID vs LVM RAID
- GPT vs MBR partitioning
- Device mapper internals (dm-*)
- Cloud block storage: EBS, Persistent Disks
- Interview: "Explain LVM and when would you use it?"

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/05-lvm/lvm.md`**

Must include:
- §2: Mermaid `graph TD` for LVM layer stack (Physical Disk → PV → VG → LV → Filesystem). Mermaid `graph TD` for PE/LE mapping.
- §4: Mermaid `flowchart TD` for "disk space emergency" triage
- §5: 3 incidents + 2 composite (LV resize gone wrong, RAID degradation unnoticed, snapshot filling up root VG; composite: LVM + filesystem corruption, cloud EBS detach during I/O)
- Cross-references: [Filesystem](../04-filesystem-and-storage/filesystem-and-storage.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/05-lvm/ linux-notes/cheatsheets/05-lvm.md linux-notes/interview-questions/05-lvm.md
git commit -m "feat: add 05-lvm topic"
```

---

### Task 9: Topic 06 — Networking (TCP/IP, DNS, Netfilter)

**Files:**
- Create: `linux-notes/06-networking/networking.md`
- Create: `linux-notes/cheatsheets/06-networking.md`
- Create: `linux-notes/interview-questions/06-networking.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch09-*.md` (Network Config)
- `sources/extracted/how-linux-works/ch10-*.md` (Network Apps)
- `sources/extracted/linux-basics-hackers/ch03-*.md` (Analyzing Networks)
- `sources/extracted/ulsah/ch13-*.md` (TCP/IP Networking)
- `sources/extracted/ulsah/ch15-*.md` (IP Routing)
- `sources/extracted/ulsah/ch16-*.md` (DNS)

**Research topics:**
- TCP/IP stack in Linux kernel: socket → TCP → IP → netfilter → NIC driver
- TCP state machine: SYN, SYN-ACK, ESTABLISHED, TIME_WAIT, CLOSE_WAIT
- TCP tuning: `net.core.somaxconn`, `net.ipv4.tcp_tw_reuse`, `net.ipv4.tcp_max_syn_backlog`
- DNS resolution path: `/etc/nsswitch.conf` → `/etc/resolv.conf` → stub resolver → recursive → authoritative
- Netfilter/iptables/nftables: chains, tables, connection tracking
- Network namespaces, veth pairs, bridge networking
- `ss`, `ip`, `tcpdump`, `nstat`, `/proc/net/tcp`
- Interview: TCP 3-way handshake, TIME_WAIT explanation, DNS resolution steps

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/06-networking/networking.md`**

Must include:
- §2: Mermaid `stateDiagram-v2` for TCP state machine. Mermaid `sequenceDiagram` for DNS resolution flow. Mermaid `flowchart LR` for netfilter chain traversal.
- §4: Mermaid `flowchart TD` for "network latency / packet loss" debugging tree
- §5: 5 incidents (TIME_WAIT exhaustion under load, DNS resolution timeout causing cascading failures, conntrack table overflow dropping packets, SYN flood overwhelming backlog, MTU mismatch causing silent drops)
- Cross-references: [Fundamentals](../00-fundamentals/fundamentals.md), [Security](../09-security/security.md), [Performance](../08-performance-and-debugging/performance-and-debugging.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/06-networking/ linux-notes/cheatsheets/06-networking.md linux-notes/interview-questions/06-networking.md
git commit -m "feat: add 06-networking topic"
```

---

### Task 10: Topic 07 — Kernel Internals (Modules, cgroups, Namespaces)

**Files:**
- Create: `linux-notes/07-kernel-internals/kernel-internals.md`
- Create: `linux-notes/cheatsheets/07-kernel-internals.md`
- Create: `linux-notes/interview-questions/07-kernel-internals.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch17-*.md` (Virtualization)
- `sources/extracted/linux-basics-hackers/ch15-*.md` (Kernel/LKMs)
- `sources/extracted/ulsah/ch11-*.md` (Drivers and the Kernel)
- `sources/extracted/ulsah/ch25-*.md` (Containers — cgroups/namespaces sections)

**Research topics:**
- Kernel modules: `insmod`, `modprobe`, `lsmod`, module signing
- cgroups v1 vs v2: hierarchy, controllers (cpu, memory, io, pids)
- Namespaces: mount, UTS, IPC, PID, network, user, cgroup
- How containers use cgroups + namespaces (Docker/containerd internals)
- Kernel compilation and configuration
- `/proc/cgroups`, `/sys/fs/cgroup/`, `systemd-cgls`
- seccomp, capabilities, AppArmor profiles
- Interview: "How do containers work at the kernel level?"

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/07-kernel-internals/kernel-internals.md`**

Must include:
- §2: Mermaid `graph LR` for cgroups v2 hierarchy. Mermaid `graph TD` for namespace isolation layers. Mermaid `flowchart TD` for kernel module loading path.
- §4: Mermaid `flowchart TD` for "container resource issue" debugging tree
- §5: 5 incidents (kernel module taint causing instability, cgroup memory limit OOM in container, PID namespace exhaustion, cgroups v1→v2 migration breaking monitoring, kernel panic from unsigned module)
- Cross-references: [Process Management](../01-process-management/process-management.md), [Memory](../03-memory-management/memory-management.md), [Security](../09-security/security.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/07-kernel-internals/ linux-notes/cheatsheets/07-kernel-internals.md linux-notes/interview-questions/07-kernel-internals.md
git commit -m "feat: add 07-kernel-internals topic"
```

---

### Task 11: Topic 08 — Performance & Debugging

**Files:**
- Create: `linux-notes/08-performance-and-debugging/performance-and-debugging.md`
- Create: `linux-notes/cheatsheets/08-performance-and-debugging.md`
- Create: `linux-notes/interview-questions/08-performance-and-debugging.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch08-*.md` (Resource Utilization)
- `sources/extracted/ulsah/ch28-*.md` (Monitoring)
- `sources/extracted/ulsah/ch29-*.md` (Performance Analysis)

**Research topics:**
- Brendan Gregg's USE method (Utilization, Saturation, Errors)
- Linux observability tools: the "60-second checklist"
- strace internals: ptrace syscall, overhead considerations
- perf: hardware counters, sampling, flame graphs
- eBPF: architecture, BCC tools, bpftrace one-liners
- ftrace, function_graph tracer, trace-cmd
- vmstat, iostat, mpstat, pidstat, sar — interpreting each column
- `/proc/pressure/` (PSI — Pressure Stall Information)
- kdump/crash for kernel panic analysis
- Interview: "Walk me through debugging a slow server" — the ultimate SRE interview question

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/08-performance-and-debugging/performance-and-debugging.md`**

Must include:
- §2: Mermaid `graph LR` for Linux observability tool landscape (categorized by subsystem). Mermaid `flowchart LR` for eBPF architecture (userspace BPF program → verifier → JIT → kernel hooks).
- §4: Mermaid `flowchart TD` — THE master debugging flowchart: "My server is slow" → CPU? Memory? Disk? Network? This is the capstone diagram.
- §5: 5 incidents (high CPU with no obvious process from short-lived forks, memory leak diagnosed with eBPF, disk latency from I/O scheduler misconfiguration, network microbursts causing packet drops, kernel soft lockup from spinlock contention)
- Cross-references: Every prior topic — this is the capstone chapter

- [ ] **Step 4: Write cheatsheet** (This is the most important cheatsheet — the "60-second checklist")
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/08-performance-and-debugging/ linux-notes/cheatsheets/08-performance-and-debugging.md linux-notes/interview-questions/08-performance-and-debugging.md
git commit -m "feat: add 08-performance-and-debugging topic"
```

---

### Task 12: Topic 09 — Security (SELinux, PAM, Hardening)

**Files:**
- Create: `linux-notes/09-security/security.md`
- Create: `linux-notes/cheatsheets/09-security.md`
- Create: `linux-notes/interview-questions/09-security.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch07-*.md` (System Configuration)
- `sources/extracted/linux-basics-hackers/ch05-*.md` (Permissions)
- `sources/extracted/linux-basics-hackers/ch13-*.md` (Secure and Anonymous)
- `sources/extracted/ulsah/ch03-*.md` (Access Control)
- `sources/extracted/ulsah/ch27-*.md` (Security)

**Research topics:**
- DAC vs MAC: traditional UNIX permissions vs SELinux/AppArmor
- SELinux: contexts, policies, booleans, `audit2allow`, troubleshooting
- PAM: module stack, `/etc/pam.d/`, authentication flow
- Linux capabilities: `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, dropping privileges
- SSH hardening: key-based auth, `PermitRootLogin`, `AllowUsers`, fail2ban
- Firewall: iptables/nftables rules for server hardening
- Audit framework: `auditd`, `ausearch`, `aureport`
- CIS benchmarks for Linux hardening
- Interview: "How would you harden a Linux server for production?"

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/09-security/security.md`**

Must include:
- §2: Mermaid `flowchart TD` for PAM authentication flow. Mermaid `graph LR` for SELinux context decision path. Mermaid `graph LR` for Linux permission bits layout.
- §4: Mermaid `flowchart TD` for "SELinux denying access" troubleshooting tree
- §5: 3 incidents + 2 composite (SELinux blocking application after update, PAM misconfiguration locking out all users, SSH brute force with weak key; composite: capability escalation + container escape, audit log overflow masking intrusion)
- Cross-references: [Fundamentals](../00-fundamentals/fundamentals.md), [Networking](../06-networking/networking.md), [Kernel Internals](../07-kernel-internals/kernel-internals.md)

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/09-security/ linux-notes/cheatsheets/09-security.md linux-notes/interview-questions/09-security.md
git commit -m "feat: add 09-security topic"
```

---

### Task 13: Topic 10 — System Design Scenarios

**Files:**
- Create: `linux-notes/10-system-design-scenarios/system-design-scenarios.md`
- Create: `linux-notes/cheatsheets/10-system-design-scenarios.md`
- Create: `linux-notes/interview-questions/10-system-design-scenarios.md`

**Source chapters to read:**
- `sources/extracted/how-linux-works/ch17-*.md` (Virtualization)
- `sources/extracted/ulsah/ch09-*.md` (Cloud Computing)
- `sources/extracted/ulsah/ch24-*.md` (Virtualization)
- `sources/extracted/ulsah/ch25-*.md` (Containers)
- `sources/extracted/ulsah/ch31-*.md` (Methodology/DevOps)

**Research topics:**
- Designing highly available Linux infrastructure
- Container orchestration: Kubernetes node architecture, kubelet, CRI
- Bare metal vs VMs vs containers: decision framework
- Linux at scale: fleet management, configuration drift
- Capacity planning: CPU, memory, disk, network provisioning
- Disaster recovery: backup strategies, RPO/RTO
- Multi-tenancy with cgroups and namespaces
- Interview: "Design a system to deploy and manage 10,000 Linux servers"

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Research enrichment via web search**
- [ ] **Step 3: Write `linux-notes/10-system-design-scenarios/system-design-scenarios.md`**

Must include:
- §2: Mermaid `graph TD` for Kubernetes node architecture (kubelet→CRI→containerd→runc→namespaces/cgroups). Mermaid `graph LR` for bare metal → VM → container spectrum.
- §5: 5 scenarios (design a log aggregation pipeline, design auto-scaling infrastructure, design a container platform from scratch, design fleet-wide kernel upgrade rollout, design multi-tenant compute platform)
- Each scenario: requirements → architecture → Linux-specific decisions → failure modes → monitoring

- [ ] **Step 4: Write cheatsheet**
- [ ] **Step 5: Write interview questions (15+)**
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/10-system-design-scenarios/ linux-notes/cheatsheets/10-system-design-scenarios.md linux-notes/interview-questions/10-system-design-scenarios.md
git commit -m "feat: add 10-system-design-scenarios topic"
```

---

### Task 14: Topic 11 — Real-World SRE Incidents

**Files:**
- Create: `linux-notes/11-real-world-sre-usecases/sre-incidents.md`
- Create: `linux-notes/cheatsheets/11-sre-incidents.md`
- Create: `linux-notes/interview-questions/11-sre-incidents.md`

**Source chapters to read:**
- `sources/extracted/ulsah/ch28-*.md` (Monitoring)
- `sources/extracted/ulsah/ch29-*.md` (Performance Analysis)
- `sources/extracted/ulsah/ch27-*.md` (Security)

**Research topics:**
- Post-mortem culture and blameless reviews
- SRE practices: SLI/SLO/SLA, error budgets, toil reduction
- Real incident patterns from public post-mortems (Cloudflare, AWS, Google, Meta)
- On-call runbook design
- Cascading failure patterns
- Interview: "Tell me about a production incident you debugged"

- [ ] **Step 1: Read all mapped source chapters**
- [ ] **Step 2: Deep research — public post-mortems and incident reports**
- [ ] **Step 3: Write `linux-notes/11-real-world-sre-usecases/sre-incidents.md`**

Must include:
- 10+ cross-cutting incidents spanning multiple Linux subsystems:
  1. Cascading OOM across microservices (memory + cgroups + networking)
  2. Kernel live-patch failure during rolling upgrade (kernel + process mgmt)
  3. DNS TTL caching causing stale endpoints after failover (networking + DNS)
  4. Thundering herd on service restart exhausting CPU (scheduling + networking)
  5. Silent data corruption from filesystem bug (filesystem + storage)
  6. Network partition causing split-brain in distributed system (networking + system design)
  7. Log volume explosion filling disk and cascading to OOM (filesystem + memory)
  8. Container escape via kernel vulnerability (security + kernel + containers)
  9. Clock skew causing distributed system inconsistency (fundamentals + networking)
  10. NIC firmware bug causing intermittent packet loss (networking + debugging)
- Each with full investigation template from spec
- Mermaid `sequenceDiagram` for at least 3 incident timelines

- [ ] **Step 4: Write cheatsheet** (incident response runbook template)
- [ ] **Step 5: Write interview questions (15+)** (behavioral + technical incident questions)
- [ ] **Step 6: Review**
- [ ] **Step 7: User approval**
- [ ] **Step 8: Commit**

```bash
git add linux-notes/11-real-world-sre-usecases/ linux-notes/cheatsheets/11-sre-incidents.md linux-notes/interview-questions/11-sre-incidents.md
git commit -m "feat: add 11-real-world-sre-incidents topic"
```

---

## Phase 2: Final Consolidation

### Task 15: Consolidate interview question bank and create index

**Files:**
- Create: `linux-notes/interview-questions/README.md` (consolidated index with difficulty levels)
- Create: `linux-notes/cheatsheets/README.md` (master cheatsheet index)
- Create: `linux-notes/README.md` (top-level navigation and study guide)

- [ ] **Step 1: Create master interview question index**

`linux-notes/interview-questions/README.md` should:
- Link to all 12 topic question files
- Categorize questions by difficulty (Senior / Staff / Principal)
- Tag questions by type (Conceptual / Scenario / Debugging / Trick)
- Provide a recommended study order

- [ ] **Step 2: Create master cheatsheet index**

`linux-notes/cheatsheets/README.md` should:
- Link to all 12 topic cheatsheets
- Include the "60-second server debugging checklist" from Topic 08
- Provide a "most important commands" quick reference

- [ ] **Step 3: Create top-level README**

`linux-notes/README.md` should:
- Describe the knowledge base purpose and target audience
- Link to all 12 topic folders
- Provide recommended study paths (1-week crash course, 2-week deep dive, 4-week comprehensive)
- Link to cheatsheets and interview questions

- [ ] **Step 4: Review all cross-references**

Verify every relative markdown link across all files resolves correctly:
```bash
grep -r '\](\.\./' linux-notes/ | while read line; do
  # extract the link path and verify it exists
  echo "$line"
done
```

- [ ] **Step 5: Final commit**

```bash
git add linux-notes/
git commit -m "feat: add consolidated indexes and top-level README for knowledge base"
```

---

## Execution Summary

| Task | Topic | Est. Incidents | Est. Questions | Weight |
|------|-------|---------------|----------------|--------|
| 1-2 | Phase 0: Extraction + Setup | — | — | Setup |
| 3 | 00-Fundamentals | 5 | 15+ | High |
| 4 | 01-Process Management | 5 | 15+ | Very High |
| 5 | 02-CPU Scheduling | 5 | 15+ | High |
| 6 | 03-Memory Management | 5 | 15+ | Very High |
| 7 | 04-Filesystem & Storage | 5 | 15+ | High |
| 8 | 05-LVM | 3+2 | 15+ | Medium |
| 9 | 06-Networking | 5 | 15+ | Very High |
| 10 | 07-Kernel Internals | 5 | 15+ | High |
| 11 | 08-Performance & Debugging | 5 | 15+ | Very High |
| 12 | 09-Security | 3+2 | 15+ | Medium-High |
| 13 | 10-System Design Scenarios | 5 | 15+ | High |
| 14 | 11-SRE Incidents | 10+ | 15+ | High |
| 15 | Phase 2: Consolidation | — | — | Finalization |

**Total estimated output:** 12 topic files + 12 cheatsheets + 12 question banks + 3 indexes = **39 markdown files**
