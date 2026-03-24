# Interview Questions: 04 -- Filesystem & Storage (VFS, Inodes, Journaling, I/O Schedulers)

> **Study guide for Senior SRE / Staff+ / Principal Engineer interviews**
> Full topic reference: [filesystem-and-storage.md](../04-filesystem-and-storage/filesystem-and-storage.md)
> Cheatsheet: [04-filesystem-and-storage.md](../cheatsheets/04-filesystem-and-storage.md)

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

### Q1. Explain the Linux VFS layer. What problem does it solve and what are its four core objects?

**Difficulty:** Senior | **Category:** Filesystem Internals

**Answer:**

1. **Problem solved:** Linux needs to support dozens of filesystem types (ext4, XFS, Btrfs, NFS, procfs, tmpfs) through a single uniform interface so that userspace code does not need to know which filesystem backs a particular file
2. **The VFS provides:**
   - A common set of system calls (`open`, `read`, `write`, `stat`, `mmap`) that work identically regardless of underlying filesystem
   - A dispatch mechanism that routes calls to the correct filesystem driver
   - Caching layers (dentry cache, inode cache) that avoid repeated disk access
3. **Four core objects:**
   - **Superblock (`struct super_block`):** one per mounted filesystem; holds filesystem metadata (block size, inode count, mount flags), root dentry, and superblock operations (`statfs`, `sync_fs`)
   - **Inode (`struct inode`):** one per file/directory/device; holds metadata (mode, uid, gid, size, timestamps, link count), operation vectors (`i_op` for create/lookup/unlink, `i_fop` for read/write), and page cache mapping
   - **Dentry (`struct dentry`):** maps a pathname component to an inode; cached in the dcache (hash table) for fast lookup; can be positive (valid inode), negative (caches "not found"), or unused (valid but reclaimable)
   - **File (`struct file`):** one per `open()` call; holds current offset (`f_pos`), access flags, file operations pointer; shared by `fork()` and `dup()`
4. **Traversal example for `read(fd, buf, count)`:**
   - fd → file descriptor table → `struct file` → `f_op->read_iter()` → filesystem-specific read → page cache check → block I/O if cache miss → data copied to userspace

---

### Q2. What is the difference between a hard link and a symbolic link at the inode level?

**Difficulty:** Senior | **Category:** Filesystem Fundamentals

**Answer:**

1. **Hard link:**
   - An additional directory entry (name → inode number mapping) pointing to the same inode
   - No new inode is created; the inode's `i_nlink` reference count is incremented
   - All hard links to a file are indistinguishable from the "original" -- there is no concept of primary vs. secondary
   - Deleting one hard link decrements `i_nlink`; data persists until `i_nlink` reaches 0 AND no open file descriptors remain
   - Restrictions: cannot cross filesystem boundaries; cannot link to directories (prevents cycles)
2. **Symbolic link:**
   - A separate inode of type `S_IFLNK` whose data is the target pathname (string)
   - Short targets (< 60 bytes on ext4) are stored inline in the inode's `i_block` field ("fast symlink")
   - Kernel resolves symlinks during path traversal by reading the stored path and restarting resolution
   - Can cross filesystem boundaries; can point to nonexistent targets (dangling)
   - Maximum symlink resolution depth: 40 (prevents infinite loops)
3. **Production implications:**
   - `ls -l` shows hard link count in column 2 -- useful for identifying files with multiple links
   - Package managers use hard links for atomic upgrades (dpkg)
   - `rsync --link-dest` creates hard links for space-efficient incremental backups
   - Dangling symlinks in `/etc` or service configs cause silent startup failures

---

### Q3. Explain the three ext4 journaling data modes and when you would use each.

**Difficulty:** Staff | **Category:** Filesystem Internals

**Answer:**

1. **`data=journal`:**
   - Both file data AND metadata are written to the journal before final location
   - Strongest crash consistency: after recovery, both data content and metadata are guaranteed consistent
   - Performance cost: up to 50% throughput reduction due to double-write of all data
   - Use case: financial audit logs, compliance-critical write paths
2. **`data=ordered`** (default):
   - Only metadata is journaled
   - Data blocks are flushed to their final location BEFORE the metadata commit record is written
   - Prevents "stale data exposure": a crash cannot leave metadata pointing to blocks containing old data from a different file
   - Good balance of performance and safety for most workloads
3. **`data=writeback`:**
   - Only metadata is journaled; no ordering guarantee between data and metadata writes
   - After crash: files may contain stale/garbage data in recently allocated blocks (potential security issue in multi-tenant)
   - Highest performance because the kernel can reorder data and metadata writes freely
   - Use case: databases with their own WAL (PostgreSQL, MySQL/InnoDB), temporary scratch filesystems
4. **Decision guidance:**
   - Default to `ordered` unless you have a measured performance need AND understand the trade-offs
   - `writeback` for databases: the database's own transaction log provides data consistency, so filesystem-level ordering is redundant
   - `journal` is rarely used; if end-to-end data integrity is needed, consider Btrfs or ZFS with built-in checksums instead

---

### Q4. Describe the three-table relationship between file descriptors, open file descriptions, and inodes. What happens during fork() and dup()?

**Difficulty:** Staff | **Category:** Kernel Internals

**Answer:**

1. **Per-process file descriptor table** (inside `struct files_struct`):
   - Array indexed by small integers (fd 0, 1, 2, ...)
   - Each entry contains: pointer to an open file description + close-on-exec flag
   - Unique to each process (though `fork()` copies it)
2. **Open file description** (`struct file`, system-wide):
   - Created once per `open()` system call
   - Contains: `f_pos` (current file offset), `f_flags` (O_RDONLY, O_APPEND, etc.), `f_op` (filesystem-specific operations)
   - Points to the dentry/inode
   - Can be shared across processes and file descriptors
3. **Inode** (`struct inode`, per-filesystem):
   - Contains file metadata and data block mapping
   - Shared by ALL opens of the same file (regardless of which process)
4. **`fork()` behavior:**
   - Child receives a copy of the parent's fd table (new array of pointers)
   - Both parent and child point to the SAME open file descriptions
   - Consequence: they share `f_pos` -- if child reads, parent's offset advances too
5. **`dup(fd)` / `dup2(fd, newfd)` behavior:**
   - Creates a new fd in the same process's table pointing to the SAME open file description
   - Both fds share offset and flags
   - Closing one does not affect the other (but both still point to same `struct file`)
6. **Independent `open()` calls:**
   - Two processes opening the same file get separate `struct file` objects with independent offsets
   - Both `struct file` objects point to the same inode

---

### Q5. Compare ext4 and XFS for a database server workload with 10+ TB of data. Justify your choice.

**Difficulty:** Staff | **Category:** Architecture

**Answer:**

1. **Recommendation: XFS for most database workloads at this scale**
2. **XFS advantages:**
   - Dynamic inode allocation: never runs out of inodes regardless of file count or size
   - Per-allocation-group (AG) locking: parallel writes from multiple database threads do not contend on a single lock
   - Superior large file handling: extent-based from inception, B+ tree metadata for O(log n) operations
   - Delayed allocation batches allocation decisions until flush, producing better contiguous extents
   - Default on RHEL/CentOS, which most database infrastructure runs on
3. **ext4 advantages:**
   - Can shrink the filesystem (XFS cannot -- only grow)
   - Simpler, more forgiving recovery tools (`e2fsck` vs. `xfs_repair`)
   - Slightly lower memory overhead
   - Longer track record of production stability
4. **When ext4 is still a valid choice:**
   - PostgreSQL with its own WAL on ext4 `data=writeback,noatime` performs well
   - Team has deep ext4 expertise and limited XFS experience
   - Need for occasional filesystem shrink operations
5. **Mount options for either:**
   - `noatime` (eliminates atime write amplification)
   - `nobarrier` only with battery-backed RAID write cache
   - XFS: `allocsize=64k` for better pre-allocation

---

### Q6. What are the four multi-queue I/O schedulers in modern Linux? When do you use each?

**Difficulty:** Staff | **Category:** Performance

**Answer:**

1. **`none` (no scheduling):**
   - Passes requests directly to hardware queues without reordering
   - Best for NVMe devices: they have deep internal queues and sub-100us latency
   - The scheduler adds CPU overhead with no throughput benefit on fast devices
2. **`mq-deadline`:**
   - Sorts requests by sector, enforces per-request deadlines (read: 500ms, write: 5000ms)
   - Prevents starvation: no read or write can wait indefinitely
   - Best for HDDs, SATA SSDs, database workloads with mixed read/write
3. **`bfq` (Budget Fair Queueing):**
   - Proportional-share scheduling: guarantees each process gets a fair share of I/O bandwidth
   - Optimizes for interactive responsiveness over raw throughput
   - High per-I/O CPU overhead; not suitable for high-IOPS servers
   - Best for desktops, containers needing I/O fairness
4. **`kyber`:**
   - Token-based, latency-targeting scheduler for fast storage
   - Limits in-flight requests per latency class rather than sorting
   - Best for SSDs where latency matters more than throughput
5. **Rule of thumb:**
   - NVMe: `none`
   - HDD: `mq-deadline`
   - Desktop: `bfq`
   - Fast SSD with latency target: `kyber`
6. **How to set persistently:**
   - udev rule: `ACTION=="add|change", KERNEL=="nvme[0-9]*", ATTR{queue/scheduler}="none"`

---

## Category 2: Scenario-Based Debugging

### Q7. `df` shows disk is 100% full but `du` reports only 60% used. Walk through your investigation.

**Difficulty:** Senior | **Category:** Debugging

**Answer:**

1. **Primary hypothesis: deleted-but-open files**
   - `lsof +L1` -- lists files with link count < 1 (unlinked but still held open)
   - `lsof +L1 | awk '{sum+=$7} END {printf "%.1f GiB\n", sum/1073741824}'` -- total space consumed
   - Root cause: `logrotate` or manual `rm` deleted log files while Nginx/Java/etc. still has them open
   - Fix: `> /proc/<PID>/fd/<N>` to truncate, or signal process to reopen (`kill -USR1` for Nginx)
2. **Secondary causes to check:**
   - Stacked mount: `findmnt /path` -- another filesystem mounted on top, hiding data underneath
   - Reserved blocks: `tune2fs -l /dev/sdX | grep "Reserved block count"` -- ext4 reserves 5% by default for root; reduce with `tune2fs -m 1`
   - Filesystem metadata overhead: journal, superblock copies, inode tables
3. **Investigation sequence:**
   - `lsof +L1` -- quantify deleted-but-open space
   - `findmnt` -- check for stacked/overlapping mounts
   - `tune2fs -l /dev/sdX` -- check reserved blocks
   - `debugfs -R "stats" /dev/sdX` -- filesystem overhead

---

### Q8. A Kubernetes node reports "No space left on device" but df -h shows 45% disk free. What is wrong?

**Difficulty:** Senior | **Category:** Debugging

**Answer:**

1. **Most likely cause: inode exhaustion**
   - `df -i /` -- check inode usage (will show 100% IUse%)
   - `df -h` only shows block space, not inodes; these are independent resources
2. **Common root causes:**
   - Container image layers creating millions of metadata files in overlay2 storage driver
   - Application pods writing one file per request/event
   - Podman/Docker build cache accumulating inodes
3. **Investigation commands:**
   - `df -i /` to confirm inode exhaustion
   - `find / -xdev -type d -exec sh -c 'echo "$(find "$1" -maxdepth 1 -type f | wc -l) $1"' _ {} \; | sort -rn | head`
   - `docker system df` or `crictl stats`
4. **Immediate fix:**
   - Clean up offending directory: `find /path -type f -mtime +1 -delete`
   - `docker system prune -a` for container images
5. **Long-term prevention:**
   - Use XFS instead of ext4 (dynamic inode allocation)
   - For ext4: `mkfs.ext4 -i 4096` for higher inode density
   - kubelet eviction threshold: `--eviction-hard=nodefs.inodesFree<5%`
   - Monitor `node_filesystem_files_free` in Prometheus

---

### Q9. After a power outage, an ext4 filesystem shows errors and remounts read-only. Walk through recovery.

**Difficulty:** Senior | **Category:** Recovery

**Answer:**

1. **Assess without writing:**
   - `dmesg | grep -i ext4` -- identify specific errors
   - `tune2fs -l /dev/sdX | grep "Filesystem state"` -- should show `ERROR`
   - `mount | grep ro` -- confirm read-only status
2. **Backup before repair:**
   - `dd if=/dev/sdX of=/backup/device-pre-repair.img bs=64K status=progress`
3. **Unmount and repair:**
   - If root filesystem: reboot to rescue/single-user mode
   - `umount /dev/sdX`
   - `e2fsck -fvy /dev/sdX` -- force check, verbose, auto-yes
4. **If journal replay fails:**
   - `tune2fs -O ^has_journal /dev/sdX` -- remove journal feature
   - `e2fsck -f /dev/sdX` -- full check without journal
   - `tune2fs -j /dev/sdX` -- recreate journal
5. **Post-repair verification:**
   - Check `lost+found/` for orphan files
   - Verify application data integrity (database consistency checks, file checksums)
   - `smartctl -a /dev/sdX` -- check for hardware errors
6. **Prevention:**
   - UPS with monitoring and auto-shutdown
   - `data=ordered` mode (not `writeback`) for crash safety
   - `barrier=1` (default) -- never disable write barriers without battery-backed cache

---

### Q10. A MySQL database on NVMe shows P99 latency 5x higher than P50 despite low average I/O utilization. Diagnose.

**Difficulty:** Staff | **Category:** Performance

**Answer:**

1. **Check I/O scheduler:**
   - `cat /sys/block/nvme0n1/queue/scheduler` -- if `bfq` or `mq-deadline`, that is the likely cause
   - BFQ adds per-I/O scheduling overhead that creates jitter on fast NVMe devices
   - NVMe has deep internal queues; external scheduling adds no value
2. **Verify with profiling:**
   - `blktrace -d /dev/nvme0n1 -o - | blkparse -i -` -- look at Q2C (queue-to-complete) distribution
   - `perf top` -- check for CPU time spent in `bfq_dispatch_request` or similar
3. **Check for dirty page writeback storms:**
   - `vmstat 1` -- look for periodic spikes in `bo` (blocks out) column
   - `cat /proc/vmstat | grep -E "nr_dirty|nr_writeback"` -- check dirty page accumulation
   - Reduce with `sysctl -w vm.dirty_ratio=5 vm.dirty_background_ratio=2`
4. **Fix:**
   - `echo none > /sys/block/nvme0n1/queue/scheduler` -- immediate relief
   - udev rule for persistence
   - Tune writeback: lower dirty ratios to prevent accumulation and sudden flush storms
5. **Prevention:**
   - Standard: NVMe devices always use scheduler `none`
   - P99 latency monitoring tied to scheduler configuration in runbooks

---

### Q11. A web server is showing "Too many open files" errors. How do you diagnose and fix this?

**Difficulty:** Senior | **Category:** Debugging

**Answer:**

1. **Check current limits:**
   - `cat /proc/<PID>/limits | grep "Max open files"` -- per-process limit
   - `cat /proc/sys/fs/file-nr` -- system-wide: (allocated, unused, max)
   - `ulimit -n` -- current shell limit
2. **Identify the consumer:**
   - `ls /proc/<PID>/fd | wc -l` -- count open fds for the process
   - `lsof -p <PID> | wc -l` -- same via lsof
   - `lsof -p <PID> | awk '{print $5}' | sort | uniq -c | sort -rn` -- breakdown by fd type (REG, IPv4, unix, etc.)
3. **Common root causes:**
   - Connection leak: application opens sockets but does not close them
   - File handle leak: opening files in a loop without closing
   - Epoll fd accumulation in event-driven servers
4. **Immediate fix:**
   - Increase per-process limit: `prlimit --pid <PID> --nofile=65536:65536`
   - Increase system-wide: `sysctl -w fs.file-max=2097152`
5. **Permanent fix:**
   - `/etc/security/limits.conf`: `* soft nofile 65536` and `* hard nofile 131072`
   - systemd service: `LimitNOFILE=65536` in unit file
   - Fix the application fd leak (the actual root cause)

---

## Category 3: Architecture & Design

### Q12. You are designing storage for a microservices platform on Kubernetes. How do you choose the filesystem for node root disks and persistent volumes?

**Difficulty:** Principal | **Category:** Architecture

**Answer:**

1. **Node root disks (ephemeral storage):**
   - XFS is preferred over ext4 for container infrastructure
   - Dynamic inode allocation handles overlay2 storage driver metadata
   - Per-AG parallelism supports concurrent container I/O
   - Default on RHEL/CentOS, well-tested with kubelet and containerd
2. **Persistent volumes for databases:**
   - ext4 or XFS depending on team expertise
   - Mount with `noatime`, appropriate journaling mode
   - For PostgreSQL/MySQL: `data=writeback` is acceptable (database WAL handles consistency)
   - For critical data without application-level WAL: `data=ordered`
3. **Persistent volumes for object/blob storage:**
   - XFS: proven at scale by Ceph (OSD backing store), OpenStack Swift
   - Large file performance and parallel write throughput
4. **Backup and snapshot storage:**
   - Btrfs: in-tree kernel support, CoW snapshots, send/receive for replication
   - ZFS: superior data integrity with checksums, but out-of-tree module (licensing concern)
5. **Factors to weigh:**
   - Team operational expertise trumps theoretical superiority
   - Kernel integration status matters for patching and support contracts
   - Vendor support: Red Hat supports XFS/ext4, SUSE supports Btrfs, Ubuntu supports ext4/ZFS
   - Performance testing with actual workload is mandatory before committing

---

### Q13. Explain the complete I/O path from a userspace write() to data persisting on an NVMe SSD.

**Difficulty:** Principal | **Category:** I/O Architecture

**Answer:**

1. **Userspace:** `write(fd, buf, count)` system call
2. **VFS layer:** fd → `struct file` → `f_op->write_iter()` dispatches to filesystem
3. **Filesystem (e.g., ext4):**
   - Allocates page cache pages for the write range
   - Copies data from userspace buffer into page cache pages
   - Marks pages dirty in the `address_space` radix tree
   - Updates inode metadata (size, mtime) -- journals the metadata change
   - Returns to userspace (write appears complete to the application)
4. **Writeback path (asynchronous unless fsync):**
   - Triggered by: `vm.dirty_background_ratio` threshold, timer (`dirty_expire_centisecs`), explicit `fsync()`, or memory pressure
   - `writepages()` callback converts dirty page ranges into block I/O
5. **Block layer:**
   - Filesystem creates `struct bio` with physical block numbers and page references
   - I/O scheduler (for NVMe, typically `none`) may merge adjacent bios
   - `struct request` is formed and submitted to the NVMe driver
6. **NVMe driver:**
   - Writes NVMe command to the submission queue (SQ) ring buffer in host memory
   - Rings the SQ doorbell register via MMIO write
   - NVMe controller DMA-reads the command from host memory
7. **NVMe controller hardware:**
   - Performs DMA read of data from host memory
   - Writes data to NAND flash (through FTL -- flash translation layer)
   - Posts completion entry to completion queue (CQ) in host memory
   - Raises MSI-X interrupt
8. **Completion path:**
   - Interrupt handler processes CQ entry
   - `bio` is completed, page cache pages marked clean
   - If `fsync()` was pending, the blocked process is woken up

---

### Q14. When would you choose Btrfs or ZFS over ext4/XFS in production, and what are the risks?

**Difficulty:** Principal | **Category:** Architecture

**Answer:**

1. **Choose Btrfs when:**
   - Need native snapshots for fast backup/rollback (CoW snapshots are instant and space-efficient)
   - Need transparent compression (zstd reduces storage cost by 30-50% for compressible data)
   - Need send/receive for incremental replication between servers
   - Running on SUSE (fully supported, default filesystem)
   - RAID 0/1/10 workloads (RAID 5/6 is still not production-ready)
2. **Choose ZFS when:**
   - Maximum data integrity is non-negotiable (per-block checksums detect silent corruption)
   - Need built-in RAID (raidz1/z2/z3) with self-healing from redundant copies
   - Deduplication is required (e.g., backup storage, VM image repositories)
   - Need robust snapshot management and clones
3. **Risks of Btrfs:**
   - RAID 5/6 has known data loss bugs (the "write hole" is not fully solved)
   - CoW fragmentation under random-write workloads (databases) -- mitigated by `chattr +C` (nodatacow)
   - Less mature than ext4/XFS for edge cases under extreme load
4. **Risks of ZFS:**
   - Out-of-tree kernel module: CDDL license prevents inclusion in mainline Linux kernel
   - Must recompile or install DKMS module on every kernel update
   - ARC cache is memory-hungry: 16 TB pool with dedup can consume ~100 GB RAM
   - Not supported by Red Hat or Canonical (Ubuntu ships it but with caveats)
5. **When to stick with ext4/XFS:**
   - Vendor support is critical (Red Hat support contract)
   - Team has no Btrfs/ZFS operational expertise
   - Workload does not need snapshots, checksums, or compression
   - Simplicity and predictability are the priority

---

## Category 4: Quick-Fire / Trivia

### Q15. What does /proc/diskstats contain and how does iostat derive its metrics?

**Difficulty:** Staff

**Answer:**

1. `/proc/diskstats` provides per-device cumulative counters since boot:
   - Fields 1-3: major, minor, device name
   - Field 4: reads completed
   - Field 5: reads merged
   - Field 6: sectors read (1 sector = 512 bytes)
   - Field 7: time reading (ms)
   - Fields 8-11: corresponding write fields
   - Field 12: I/Os in progress (instantaneous, not cumulative)
   - Field 13: time doing I/O (ms, wall-clock when device had I/O in flight)
   - Field 14: weighted I/O time (ms)
2. iostat reads snapshots at intervals and computes deltas:
   - `r/s` = delta(reads completed) / interval
   - `await` = delta(total I/O time) / delta(total I/Os completed)
   - `%util` = delta(time doing I/O) / (interval_ms) * 100
   - `avgqu-sz` = delta(weighted I/O time) / (interval_ms)
3. Key insight: `%util = 100%` means "device had I/O every millisecond" -- for HDDs this means saturated, for NVMe it means nothing (parallel queues can serve many requests simultaneously)

---

### Q16. What is the difference between sync, fsync(), and fdatasync()?

**Difficulty:** Staff

**Answer:**

1. **`sync` (command / `sync()` syscall):**
   - Flushes ALL dirty buffers and page cache pages for ALL filesystems
   - May return before writes complete (implementation-dependent)
   - Use: pre-shutdown, pre-dd, snapshot preparation
2. **`fsync(fd)`:**
   - Flushes all dirty data AND all metadata for one specific file
   - Blocks until hardware confirms write completion (through the entire stack)
   - Metadata includes: file size, timestamps, extent tree, permissions
   - Use: database transaction commit, crash-safe file writes
3. **`fdatasync(fd)`:**
   - Like fsync but skips metadata not needed to read the data back correctly
   - Skips: atime, mtime updates (unless file size changed)
   - Does NOT skip: file size changes, extent/block mapping changes
   - Slightly faster than fsync when only data integrity matters
4. **The fsync dance for crash-safe file replacement:**
   - Write to temp file
   - `fsync(temp_fd)`
   - `rename(temp, target)`
   - `fsync(directory_fd)` -- ensures the rename is persisted

---

### Q17. What is the maximum number of hard links per file on ext4? On XFS?

**Difficulty:** Senior

**Answer:**

- **ext4:** 65,000 (16-bit `i_links_count`)
  - With `dir_nlink` feature (modern default): directories can exceed 65,000 subdirectories (link count set to 1 as sentinel)
- **XFS:** no practical limit (64-bit link count)
- **Btrfs:** 65,535 (16-bit)
- **Production relevance:** systems that create millions of hard links (e.g., Bacula backup, dedup tools) can hit ext4 limits; XFS is immune

---

### Q18. How do you recover space from a 20 GiB log file that was deleted while Nginx still has it open?

**Difficulty:** Senior

**Answer:**

1. **Identify the file:**
   - `lsof +L1 | grep nginx` -- find the deleted-but-open file, note PID and FD number
2. **Truncate without restarting Nginx:**
   - `> /proc/<PID>/fd/<FD>` -- writes zero bytes to the open file description
   - This works because `/proc/PID/fd/N` is a kernel-managed symlink to the actual open file
3. **Alternative: signal Nginx to reopen:**
   - `kill -USR1 $(cat /var/run/nginx.pid)` -- Nginx reopens all log files
   - Space from the deleted file is reclaimed when the old fd is closed
4. **Verify:**
   - `df -h /` -- space should be reclaimed
   - `lsof +L1 | grep nginx` -- deleted file should no longer appear
5. **Prevention:**
   - Use `logrotate` with `postrotate kill -USR1` instead of `rm` + `touch`
   - Or use `copytruncate` directive (copies then truncates in-place)

---

### Q19. Explain the ext4 extent tree. Why is it better than the traditional indirect block mapping?

**Difficulty:** Staff

**Answer:**

1. **Traditional indirect block mapping (ext2/ext3):**
   - Inode stores 12 direct block pointers (48 KiB of data)
   - 1 single-indirect pointer → 1024 block pointers → 4 MiB
   - 1 double-indirect → 1024 single-indirect → 4 GiB
   - 1 triple-indirect → 4 TiB
   - Problem: each indirect level requires an extra disk read; a 1 GiB sequential file needs thousands of block pointers
2. **Extent tree (ext4):**
   - Each extent describes a contiguous run: (logical start, physical start, length)
   - One extent can cover up to 128 MiB (32,768 blocks at 4K each)
   - The inode's 60-byte `i_block` field holds an extent header + up to 4 extents (zero-depth tree)
   - Large/fragmented files use a B-tree of extents (depth 1, 2, rarely more)
3. **Advantages:**
   - A 1 GiB sequential file needs only ~8 extents vs. ~262,144 individual block pointers
   - Fewer metadata disk reads for large sequential files
   - Better metadata cache utilization
   - Faster file allocation and deletion
4. **The 60-byte i_block layout:**
   - 12 bytes: extent header (magic, entry count, max entries, depth)
   - 48 bytes: up to 4 extent entries (12 bytes each)
   - If more than 4 extents needed: header points to external blocks forming a B-tree

---

### Q20. What kernel tunables control dirty page writeback, and how would you tune them for a database server?

**Difficulty:** Staff

**Answer:**

1. **Key tunables:**
   - `vm.dirty_ratio` (default 20): percentage of total RAM that can be dirty before synchronous writeback is forced (process blocks on write)
   - `vm.dirty_background_ratio` (default 10): percentage of RAM that triggers background writeback (kworker threads start flushing)
   - `vm.dirty_expire_centisecs` (default 3000 = 30s): age threshold for dirty pages to become eligible for writeback
   - `vm.dirty_writeback_centisecs` (default 500 = 5s): interval at which the writeback thread checks for dirty pages
2. **For database servers, reduce dirty accumulation:**
   - `vm.dirty_ratio=5` -- prevent massive dirty page buildup that causes sudden flush storms
   - `vm.dirty_background_ratio=2` -- start background writeback earlier
   - This trades slightly more frequent small writes for avoiding P99 latency spikes during sudden flushes
3. **Why defaults are bad for databases:**
   - With 256 GiB RAM and default `dirty_ratio=20`: up to 51 GiB of dirty data can accumulate
   - When flushed, this creates a massive I/O burst causing write latency spikes
   - Databases are sensitive to tail latency; gradual writeback is much better
4. **Related tunable:**
   - `vm.vfs_cache_pressure` (default 100): controls reclaim aggressiveness for dcache/icache
   - Lower values keep more metadata cached (good for fileservers with many files)
