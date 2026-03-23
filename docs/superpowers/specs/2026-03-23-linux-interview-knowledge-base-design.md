# Linux Interview Preparation Knowledge Base — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Primary use case:** Senior SRE / Cloud Engineer interview preparation
**Secondary use cases:** Team training material, production on-call reference

---

## 1. Overview

Generate a comprehensive Linux knowledge base synthesized from three source books, enriched with real-world production knowledge, modern SRE practices, kernel debugging techniques, and large-scale distributed systems experience.

**Target audience:** Experienced engineers (10+ years) preparing for senior SRE / Cloud Engineer roles at FAANG-level companies. Content assumes reader knows the basics — no beginner explanations.

**Source materials:**
- How Linux Works: What Every Superuser Should Know (2021)
- Linux Basics for Hackers, 2nd Edition
- UNIX and Linux System Administration Handbook, 5th Edition (2017)

---

## 2. Architecture — Three-Phase Pipeline

### Phase 0: PDF Extraction (Setup)

Adapt `extract_pdfs.py` from `le-system-design/scripts/` to target the 3 Linux books.

**Process:**
1. Modify book configuration to point at the 3 Linux PDFs in `sources/`
2. Extract each book chapter-by-chapter into `sources/extracted/{book-slug}/chNN-title.md`
3. Preserve tables, code blocks, and examples
4. Generate `manifest.json` for validation
5. Validate extraction quality (minimum content length, chapter count)
6. Verify TOC bookmarks exist in each PDF; fall back to font-size heuristic for books without TOC

**Phase 0 gate:** All 3 books must extract successfully (no redundancy margin with only 3 sources).

**Book mapping:**

| Book | Slug | Location |
|------|------|----------|
| How Linux Works (2021) | `how-linux-works` | `sources/How Linux Works*.pdf` |
| Linux Basics for Hackers (2nd Ed) | `linux-basics-hackers` | `sources/Linux Basics for Hackers*.pdf` |
| UNIX/Linux Sysadmin Handbook (2017) | `ulsah` | `sources/UNIX and Linux System Administration Handbook*.pdf` |

**Output:** `sources/extracted/` with ~65 raw chapter markdown files.

### Phase 1: Per-Topic Generation (Sequential)

Each of the 12 topics is processed through a 7-step workflow:

1. **Source Mapping** — Identify which extracted chapters from each book are relevant
2. **Deep Read** — Read relevant extracted chapters + go back to PDFs for precision (diagrams, tables, edge cases)
3. **Research Enrichment** — Web research for real-world FAANG incidents, interview experiences/testimonials, modern practices (eBPF, container runtimes, etc.)
4. **Synthesis** — Merge all 3 book sources + research into unified 9-section template. No book-by-book summaries — one opinionated, senior-level explanation.
5. **Cheatsheet + Questions** — Generate companion files in `cheatsheets/` and `interview-questions/`
6. **Review** — Dispatch code-review agent for technical accuracy verification
7. **User Approval** — User reviews generated topic. Only after approval: commit and move to next topic.

### Phase 2: Verification (Per Topic)

Each topic is verified before proceeding to the next. See Quality Standards (Section 6).

---

## 3. Folder Structure

```
linux-notes/
├── 00-fundamentals/              # Boot process, kernel arch, syscalls
├── 01-process-management/        # Processes, scheduling, signals
├── 02-cpu-scheduling/            # CFS, RT scheduling, CPU affinity
├── 03-memory-management/         # Paging, OOM, page cache, zones
├── 04-filesystem-and-storage/    # VFS, inodes, ext4, XFS
├── 05-lvm/                       # LVM, RAID, disk management
├── 06-networking/                # TCP/IP, DNS, netfilter, iptables
├── 07-kernel-internals/          # Modules, cgroups, namespaces
├── 08-performance-and-debugging/ # perf, eBPF, ftrace, strace
├── 09-security/                  # SELinux, PAM, hardening
├── 10-system-design-scenarios/   # Large-scale Linux infrastructure
├── 11-real-world-sre-usecases/   # Cross-cutting incident repository
├── cheatsheets/                  # Per-topic command references
└── interview-questions/          # Consolidated question bank
```

Each topic folder contains a single comprehensive markdown file (e.g., `01-process-management/process-management.md`).

---

## 4. Topic Execution Order

Topics ordered by interview frequency and dependency chain:

| # | Topic | Depends On | Interview Weight |
|---|-------|-----------|-----------------|
| 1 | Fundamentals (Boot, Kernel Arch, Syscalls) | None | High |
| 2 | Process Management | Fundamentals | Very High |
| 3 | CPU Scheduling | Processes | High |
| 4 | Memory Management | Fundamentals | Very High |
| 5 | Filesystem & Storage | Fundamentals | High |
| 6 | LVM & Disk Management | Filesystem | Medium |
| 7 | Networking (TCP/IP, DNS, Netfilter) | Fundamentals | Very High |
| 8 | Kernel Internals (Modules, cgroups, namespaces) | All prior | High |
| 9 | Performance & Debugging | All prior | Very High |
| 10 | Security (SELinux, PAM, Hardening) | Fundamentals, Networking | Medium-High |
| 11 | System Design Scenarios | All prior | High |
| 12 | Real-World SRE Incidents | All prior | High |

Cheatsheets and interview questions are generated alongside each topic (not as a separate phase).

---

## 5. Per-Topic Template (9 Sections)

Every topic file follows this structure:

### Section 1: Concept (Senior-Level Understanding)
- No beginner explanations
- Explain like mentoring an experienced engineer
- Include trade-offs and design decisions
- Mermaid diagram: component/relationship overview

### Section 2: Internal Working (Kernel-Level Deep Dive)
- Syscalls involved
- Kernel data structures (with ASCII layout diagrams)
- Memory/process flow
- User-space vs kernel-space interactions
- Mermaid diagram: user-space <-> kernel-space flow

### Section 3: Commands + Practical Examples
- Real commands used in production
- Edge cases and gotchas
- `/proc`, `/sys`, cgroups, namespaces usage
- Example output with annotations

### Section 4: Advanced Debugging & Observability
- strace, ltrace, perf, eBPF
- vmstat, iostat, sar, lsof, netstat, ss
- HOW and WHY to use each tool
- Mermaid diagram: debugging decision tree/flowchart

### Section 5: Real-World Production Scenarios
- Minimum 5 FAANG-level incidents for high-weight topics (Process Management, Memory, Networking, Performance/Debugging)
- Minimum 3 incidents for medium-weight topics (LVM, Security), with remaining 2 optionally as composite/cross-cutting scenarios
- Each incident follows the template:
  - Incident Title
  - Context (scale, infra type, cloud/on-prem)
  - Symptoms + observability signals
  - Step-by-step investigation with commands
  - Root cause (kernel/system-level explanation)
  - Immediate mitigation + long-term fix
  - Prevention (monitoring/alerting improvements)

### Section 6: Advanced Interview Questions
- Minimum 15 questions across 4 categories:
  - Conceptual Deep Questions
  - Scenario-Based Questions
  - Debugging Questions
  - Trick Questions
- Each question includes a detailed answer

### Section 7: Common Pitfalls & Misconceptions
- What engineers usually misunderstand
- Subtle Linux behavior that trips people up

### Section 8: Pro Tips (From 15+ Years Experience)
- Performance tuning
- Kernel tuning
- Production stability insights

### Section 9: Cheatsheet
- Important commands with examples
- Debugging flowchart
- Key files (`/proc`, `/etc`, `/sys`)
- One-liners for common tasks

---

## 6. Quality Standards

### Accuracy Gates
- Syscall names verified (real kernel syscalls, not made-up)
- Kernel data structures referenced correctly (e.g., `task_struct`, `mm_struct`, `inode`)
- Command examples use correct flags and syntax
- `/proc` and `/sys` paths are real paths
- No hallucinated kernel versions or config parameters

### Content Depth Gates
- Section 1: No introductory-level content. Assumes reader knows fundamentals.
- Section 2: At least two Mermaid diagrams (one for data structures/architecture, one for flow)
- Section 5: Minimum 5 incidents for high-weight topics, minimum 3 for medium-weight topics (per Section 5 tiered requirement)
- Section 6: Minimum 15 questions across 4 categories with detailed answers

### Structural Gates
- All 9 sections present and substantive
- No book-by-book summaries — unified synthesis only
- Cross-references between related topics using relative markdown links (e.g., `[see Process Management](../01-process-management/process-management.md)`)
- Target size: 3,000-8,000 words per topic file (excluding code blocks and diagrams)

### Diagram Standards
- **Mermaid diagrams exclusively** — all diagrams must use Mermaid (no ASCII art)
- Use ```mermaid code blocks for all diagrams

| Context | Mermaid Type |
|---------|-------------|
| State machines (process states, TCP states) | `stateDiagram-v2` |
| Data flow (syscall path, packet flow) | `flowchart TD` |
| Component relationships (kernel subsystems) | `graph LR` |
| Timelines (boot sequence, incident timeline) | `sequenceDiagram` |
| Decision trees (debugging flowcharts) | `flowchart TD` with diamond nodes |
| Data structures (task_struct, page tables) | `classDiagram` or `graph TD` |

---

## 7. Review Process

For each generated topic:

1. **Automated review agent** checks technical accuracy, structural completeness, and diagram rendering
2. **User reviews** the complete topic file
3. **Approval required** before committing to repo and moving to next topic
4. If issues found: fix, re-review, repeat until zero errors

---

## 8. Research Sources for Enrichment

Beyond the 3 books, each topic is enriched with:
- Real-world FAANG incident patterns (post-mortems, blog posts)
- Linux interview experiences and testimonials (LinkedIn, Medium, engineering blogs)
- Modern practices: eBPF, container runtimes, systemd evolution
- Kernel documentation and source code references
- SRE best practices (Google SRE Book patterns applied to Linux)

---

## 9. Success Criteria

The knowledge base is complete when:
- All 12 topic files generated, reviewed, and approved
- All cheatsheets generated (one per topic)
- Interview question bank consolidated
- All Mermaid diagrams render correctly in standard markdown viewers
- Content reads like internal training material for senior engineers at Google/Netflix
- Zero technical errors in syscalls, commands, kernel structures, and file paths
