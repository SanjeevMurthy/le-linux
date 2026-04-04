# Linux Interview Preparation Knowledge Base

**Target audience:** Senior SRE / Staff / Principal Cloud Engineer (10+ years experience)

**Source materials:** Synthesized from 3 books on Linux internals, systems programming, and SRE practice, combined with real-world production knowledge from operating large-scale infrastructure.

---

<!-- toc -->
## Table of Contents

- [Topic Index](#topic-index)
- [Quick Links](#quick-links)
- [Study Paths](#study-paths)
  - [1-Week Crash Course (Highest Interview Weight)](#1-week-crash-course-highest-interview-weight)
  - [2-Week Deep Dive (All Core Topics)](#2-week-deep-dive-all-core-topics)
  - [4-Week Comprehensive (Full Preparation)](#4-week-comprehensive-full-preparation)
- [Topic Template (9-Section Structure)](#topic-template-9-section-structure)
- [How to Use This Repository](#how-to-use-this-repository)

<!-- toc stop -->

## Topic Index

| # | Topic | Notes | Interview Qs | Cheatsheet |
|---|-------|-------|-------------|------------|
| 00 | Fundamentals (Boot, Kernel, Syscalls) | [fundamentals.md](linux-notes/00-fundamentals/fundamentals.md) | [questions](linux-notes/interview-questions/00-fundamentals.md) | [cheatsheet](linux-notes/cheatsheets/00-fundamentals.md) |
| 01 | Process Management | [process-management.md](linux-notes/01-process-management/process-management.md) | [questions](linux-notes/interview-questions/01-process-management.md) | [cheatsheet](linux-notes/cheatsheets/01-process-management.md) |
| 02 | CPU Scheduling | [cpu-scheduling.md](linux-notes/02-cpu-scheduling/cpu-scheduling.md) | [questions](linux-notes/interview-questions/02-cpu-scheduling.md) | [cheatsheet](linux-notes/cheatsheets/02-cpu-scheduling.md) |
| 03 | Memory Management | [memory-management.md](linux-notes/03-memory-management/memory-management.md) | [questions](linux-notes/interview-questions/03-memory-management.md) | [cheatsheet](linux-notes/cheatsheets/03-memory-management.md) |
| 04 | Filesystem and Storage | [filesystem-and-storage.md](linux-notes/04-filesystem-and-storage/filesystem-and-storage.md) | [questions](linux-notes/interview-questions/04-filesystem-and-storage.md) | [cheatsheet](linux-notes/cheatsheets/04-filesystem-and-storage.md) |
| 05 | LVM and Disk Management | [lvm.md](linux-notes/05-lvm/lvm.md) | [questions](linux-notes/interview-questions/05-lvm.md) | [cheatsheet](linux-notes/cheatsheets/05-lvm.md) |
| 06 | Networking (TCP/IP, DNS, Netfilter) | [networking.md](linux-notes/06-networking/networking.md) | [questions](linux-notes/interview-questions/06-networking.md) | [cheatsheet](linux-notes/cheatsheets/06-networking.md) |
| 07 | Kernel Internals (Modules, cgroups, Namespaces) | [kernel-internals.md](linux-notes/07-kernel-internals/kernel-internals.md) | [questions](linux-notes/interview-questions/07-kernel-internals.md) | [cheatsheet](linux-notes/cheatsheets/07-kernel-internals.md) |
| 08 | Performance and Debugging | [performance-and-debugging.md](linux-notes/08-performance-and-debugging/performance-and-debugging.md) | [questions](linux-notes/interview-questions/08-performance-and-debugging.md) | [cheatsheet](linux-notes/cheatsheets/08-performance-and-debugging.md) |
| 09 | Security (SELinux, PAM, Hardening) | [security.md](linux-notes/09-security/security.md) | [questions](linux-notes/interview-questions/09-security.md) | [cheatsheet](linux-notes/cheatsheets/09-security.md) |
| 10 | System Design Scenarios | [system-design-scenarios.md](linux-notes/10-system-design-scenarios/system-design-scenarios.md) | [questions](linux-notes/interview-questions/10-system-design-scenarios.md) | [cheatsheet](linux-notes/cheatsheets/10-system-design-scenarios.md) |
| 11 | Real-World SRE Incidents | [sre-incidents.md](linux-notes/11-real-world-sre-usecases/sre-incidents.md) | [questions](linux-notes/interview-questions/11-sre-incidents.md) | [cheatsheet](linux-notes/cheatsheets/11-sre-incidents.md) |

---

## Quick Links

- [Interview Questions Bank](linux-notes/interview-questions/README.md) -- 229 questions across all topics
- [Cheatsheets Quick Reference](linux-notes/cheatsheets/README.md) -- command references and debugging workflows

---

## Study Paths

### 1-Week Crash Course (Highest Interview Weight)

Focus on the four topics that appear most frequently in SRE interviews. Spend 1-2 days per topic.

| Day | Topic | Why |
|-----|-------|-----|
| 1-2 | [01 - Process Management](linux-notes/01-process-management/process-management.md) | fork/exec, zombies, signals -- asked in nearly every interview |
| 3 | [03 - Memory Management](linux-notes/03-memory-management/memory-management.md) | OOM, page cache, RSS vs VSZ -- top production debugging topic |
| 4-5 | [06 - Networking](linux-notes/06-networking/networking.md) | TCP states, DNS, conntrack -- the other half of every SRE interview |
| 6-7 | [08 - Performance and Debugging](linux-notes/08-performance-and-debugging/performance-and-debugging.md) | USE method, perf, eBPF, flame graphs -- how you prove your operational depth |

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
