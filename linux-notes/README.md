# Linux Interview Preparation Knowledge Base

**Target audience:** Senior SRE / Staff / Principal Cloud Engineer (10+ years experience)

**Source materials:** Synthesized from 3 books on Linux internals, systems programming, and SRE practice, combined with real-world production knowledge from operating large-scale infrastructure.

---

## Topic Index

| # | Topic | Notes | Interview Qs | Cheatsheet |
|---|-------|-------|-------------|------------|
| 00 | Fundamentals (Boot, Kernel, Syscalls) | [fundamentals.md](00-fundamentals/fundamentals.md) | [questions](interview-questions/00-fundamentals.md) | [cheatsheet](cheatsheets/00-fundamentals.md) |
| 01 | Process Management | [process-management.md](01-process-management/process-management.md) | [questions](interview-questions/01-process-management.md) | [cheatsheet](cheatsheets/01-process-management.md) |
| 02 | CPU Scheduling | [cpu-scheduling.md](02-cpu-scheduling/cpu-scheduling.md) | [questions](interview-questions/02-cpu-scheduling.md) | [cheatsheet](cheatsheets/02-cpu-scheduling.md) |
| 03 | Memory Management | [memory-management.md](03-memory-management/memory-management.md) | [questions](interview-questions/03-memory-management.md) | [cheatsheet](cheatsheets/03-memory-management.md) |
| 04 | Filesystem and Storage | [filesystem-and-storage.md](04-filesystem-and-storage/filesystem-and-storage.md) | [questions](interview-questions/04-filesystem-and-storage.md) | [cheatsheet](cheatsheets/04-filesystem-and-storage.md) |
| 05 | LVM and Disk Management | [lvm.md](05-lvm/lvm.md) | [questions](interview-questions/05-lvm.md) | [cheatsheet](cheatsheets/05-lvm.md) |
| 06 | Networking (TCP/IP, DNS, Netfilter) | [networking.md](06-networking/networking.md) | [questions](interview-questions/06-networking.md) | [cheatsheet](cheatsheets/06-networking.md) |
| 07 | Kernel Internals (Modules, cgroups, Namespaces) | [kernel-internals.md](07-kernel-internals/kernel-internals.md) | [questions](interview-questions/07-kernel-internals.md) | [cheatsheet](cheatsheets/07-kernel-internals.md) |
| 08 | Performance and Debugging | [performance-and-debugging.md](08-performance-and-debugging/performance-and-debugging.md) | [questions](interview-questions/08-performance-and-debugging.md) | [cheatsheet](cheatsheets/08-performance-and-debugging.md) |
| 09 | Security (SELinux, PAM, Hardening) | [security.md](09-security/security.md) | [questions](interview-questions/09-security.md) | [cheatsheet](cheatsheets/09-security.md) |
| 10 | System Design Scenarios | [system-design-scenarios.md](10-system-design-scenarios/system-design-scenarios.md) | [questions](interview-questions/10-system-design-scenarios.md) | [cheatsheet](cheatsheets/10-system-design-scenarios.md) |
| 11 | Real-World SRE Incidents | [sre-incidents.md](11-real-world-sre-usecases/sre-incidents.md) | [questions](interview-questions/11-sre-incidents.md) | [cheatsheet](cheatsheets/11-sre-incidents.md) |

---

## Quick Links

- [Interview Questions Bank](interview-questions/README.md) -- 229 questions across all topics
- [Cheatsheets Quick Reference](cheatsheets/README.md) -- command references and debugging workflows

---

## Study Paths

### 1-Week Crash Course (Highest Interview Weight)

Focus on the four topics that appear most frequently in SRE interviews. Spend 1-2 days per topic.

| Day | Topic | Why |
|-----|-------|-----|
| 1-2 | [01 - Process Management](01-process-management/process-management.md) | fork/exec, zombies, signals -- asked in nearly every interview |
| 3 | [03 - Memory Management](03-memory-management/memory-management.md) | OOM, page cache, RSS vs VSZ -- top production debugging topic |
| 4-5 | [06 - Networking](06-networking/networking.md) | TCP states, DNS, conntrack -- the other half of every SRE interview |
| 6-7 | [08 - Performance and Debugging](08-performance-and-debugging/performance-and-debugging.md) | USE method, perf, eBPF, flame graphs -- how you prove your operational depth |

### 2-Week Deep Dive (All Core Topics)

Cover all foundational and systems topics (00-09). Work through one topic per day, then use remaining days for the interview question banks.

| Week | Topics |
|------|--------|
| Week 1 | 00 Fundamentals, 01 Process Management, 02 CPU Scheduling, 03 Memory Management, 04 Filesystem and Storage |
| Week 2 | 05 LVM, 06 Networking, 07 Kernel Internals, 08 Performance and Debugging, 09 Security |

### 4-Week Comprehensive (Full Preparation)

All 12 topics plus dedicated practice time. This path is for Principal-level interviews or when you want no gaps.

| Week | Focus |
|------|-------|
| Week 1 | Topics 00-03 (Fundamentals, Process, CPU, Memory) |
| Week 2 | Topics 04-07 (Filesystem, LVM, Networking, Kernel Internals) |
| Week 3 | Topics 08-11 (Performance, Security, System Design, SRE Incidents) |
| Week 4 | Practice all interview question banks. Do timed mock answers (2-3 min conceptual, 3-5 min scenario). Review cheatsheets daily. |

---

## Topic Template (9-Section Structure)

Every topic follows a consistent 9-section structure designed for progressive depth:

| Section | Purpose |
|---------|---------|
| 1. Concept | Senior-level understanding of the core ideas |
| 2. Internal Working | Kernel-level deep dive -- data structures, code paths, algorithms |
| 3. Commands | Production toolkit -- the commands you actually use |
| 4. Debugging | Systematic methodology for diagnosing issues |
| 5. Real-World Scenarios | Production incidents mapped to investigation workflows |
| 6. Interview Questions | 15-20 questions per topic with full answers |
| 7. Common Pitfalls | Misconceptions that trip up even experienced engineers |
| 8. Pro Tips | Expert techniques from 15+ years of production experience |
| 9. Cheatsheet | Quick reference for rapid recall |

---

## How to Use This Repository

1. **Read the topic notes** for deep understanding (Sections 1-2)
2. **Practice the commands** on a test system (Section 3)
3. **Study the debugging workflows** (Section 4-5)
4. **Answer interview questions aloud** -- time yourself (Section 6 + question bank)
5. **Review cheatsheets** daily during the final week before interviews
6. **Focus on "why" not "what"** -- interviewers care about your mental model, not memorized commands
