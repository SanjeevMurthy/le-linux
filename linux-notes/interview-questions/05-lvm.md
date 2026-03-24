# Interview Questions: 05 -- LVM & Disk Management (Logical Volumes, RAID, Partitioning)

> **Study guide for Senior SRE / Staff+ / Principal Engineer interviews**
> Full topic reference: [lvm.md](../05-lvm/lvm.md)
> Cheatsheet: [05-lvm.md](../cheatsheets/05-lvm.md)

---

## How to Use This File

- Questions are organized by category and tagged with difficulty level
- **Senior** = Expected knowledge for Senior SRE (L5/E5)
- **Staff** = Expected for Staff Engineer (L6/E6)
- **Principal** = Expected for Principal/Distinguished Engineer (L7+/E7+)
- Practice answering aloud. Time yourself: 2-3 minutes for conceptual, 3-5 minutes for scenario-based
- For scenario questions, structure your answer as: Symptoms -> Hypothesis -> Investigation commands -> Root cause -> Fix -> Prevention

---

## Category 1: LVM Architecture & Internals

### Q1. Explain the LVM abstraction layers. What are PVs, VGs, LVs, and how do PEs/LEs map between them?

**Difficulty:** Senior | **Category:** LVM Fundamentals

**Answer:**

1. **Physical Volume (PV):** A block device (disk, partition, or RAID array) initialized with `pvcreate`. Contains an LVM label (sector 1), a metadata area (first 1 MiB), and a data area divided into Physical Extents (PEs).

2. **Volume Group (VG):** A pool of storage formed by aggregating one or more PVs via `vgcreate`. The VG is the unit of PE size (default 4 MiB, set at creation, immutable). All PVs in a VG share this PE size.

3. **Logical Volume (LV):** A virtual block device carved from a VG's PE pool via `lvcreate`. The LV appears as `/dev/VG_NAME/LV_NAME` (symlink to `/dev/mapper/VG_NAME-LV_NAME`, which is a device-mapper device `/dev/dm-N`).

4. **PE/LE Mapping:**
   - Every LV is divided into Logical Extents (LEs), each exactly the same size as the VG's PE size
   - Each LE maps to exactly one PE on some PV in the VG
   - **Linear mapping** (default): LEs map sequentially to PEs on one PV, then continue on the next PV
   - **Striped mapping**: LEs are interleaved round-robin across multiple PVs
   - The mapping table is stored in LVM metadata (text format, replicated on every PV in the VG) and translated into device-mapper tables at activation time

5. **The key insight:** LVM itself does no I/O. The `lvm2` userspace tools construct device-mapper mapping tables. The kernel's `dm_mod` module handles all I/O routing based on these tables.

---

### Q2. What role does the Linux device mapper play in LVM? How would you inspect the actual mapping table of an LV?

**Difficulty:** Senior | **Category:** Device Mapper

**Answer:**

1. **Device mapper is the kernel engine beneath LVM:**
   - LVM2 is a userspace configuration tool; the kernel's device-mapper framework (`dm_mod`) implements the actual block I/O routing
   - Every activated LV becomes a device-mapper device (`/dev/dm-N`)
   - LVM constructs a mapping table that specifies which device-mapper target to use and how to route sectors

2. **Key device-mapper targets used by LVM:**
   - `dm-linear`: maps a sector range to another device + offset (default for simple LVs)
   - `dm-striped`: round-robin I/O across N devices (for striped LVs)
   - `dm-snapshot` / `dm-snapshot-origin`: copy-on-write snapshots
   - `dm-thin`: thin provisioning with shared data pools
   - `dm-mirror` / `dm-raid`: mirroring and RAID within LVM

3. **Inspecting the mapping table:**
   ```bash
   dmsetup table /dev/mapper/vg_prod-lv_data
   # Output: 0 209715200 linear /dev/sda1 2048
   # Meaning: starting at sector 0, 209715200 sectors, using dm-linear,
   #          backed by /dev/sda1 starting at sector 2048
   ```

4. **For multi-segment LVs (spanning PVs), you see multiple lines:**
   ```
   0 104857600 linear /dev/sda1 2048
   104857600 104857600 linear /dev/sdb1 2048
   ```

5. **Additional inspection tools:**
   - `dmsetup ls --tree` shows device-mapper dependency tree
   - `dmsetup status` shows runtime state (useful for snapshot fill percent, thin pool usage)
   - `dmsetup info -c` shows open count, target count per dm device

---

### Q3. Compare classic LVM snapshots with thin snapshots. When would you use each?

**Difficulty:** Staff | **Category:** Snapshots

**Answer:**

1. **Classic snapshots (dm-snapshot):**
   - Require a fixed-size COW (copy-on-write) exception store allocated from the VG
   - Every write to the origin triggers: read-old-block -> write-old-block-to-COW -> write-new-block (3 I/Os per write)
   - Multiple snapshots multiply the write penalty (N snapshots = N+1 write operations)
   - If the COW store fills up, the snapshot is **permanently invalidated** and must be deleted
   - COW store fills even from writes to the *origin* (not just the snapshot)
   - Good for: short-lived backup windows (minutes), pre-upgrade safety nets you will delete immediately

2. **Thin snapshots (dm-thin):**
   - Both origin and snapshots reside in a shared thin pool (data LV + metadata LV)
   - Snapshots share unchanged blocks via reference counting -- no data duplication
   - Snapshots of snapshots are O(1) operations (flat metadata, not chain)
   - No fixed COW size; space consumed on demand from the pool
   - Over-provisioning is possible: total logical size can exceed pool physical size
   - Metadata overhead: separate metadata LV (2 MiB to 16 GiB) must be monitored
   - Good for: long-lived snapshots, development/test cloning, any scenario needing many snapshots

3. **Risks specific to thin snapshots:**
   - If the thin pool runs out of space, **all thin LVs freeze** (not just the snapshot)
   - Must configure `thin_pool_autoextend_threshold` and `thin_pool_autoextend_percent` in `/etc/lvm/lvm.conf`
   - Metadata corruption in the thin pool affects all thin LVs

4. **Decision rule:** Use thin snapshots for everything unless you have a specific reason not to. Classic snapshots are acceptable only for sub-minute backup operations where the simplicity of not managing a thin pool outweighs the performance cost.

---

### Q4. What happens internally when you run `lvextend -L +50G -r /dev/vg/lv`? Walk through every step.

**Difficulty:** Staff | **Category:** LVM Operations

**Answer:**

1. **LVM metadata read:** `lvextend` reads the VG metadata from `/etc/lvm/backup/` or from the PV metadata areas. It verifies the VG has >= 50 GiB of free PEs (50 GiB / 4 MiB PE = 12,800 PEs).

2. **PE allocation:** LVM selects 12,800 free PEs from available PVs. The allocation policy (normal, contiguous, anywhere) determines which PVs and which PE ranges are chosen.

3. **Metadata update:** LVM writes new VG metadata that includes the additional segment(s) for the LV. The metadata is written to the metadata areas on every PV in the VG (atomic via write + commit).

4. **Device-mapper table reload:**
   - LVM constructs a new mapping table with the additional sector range
   - Calls `dmsetup reload` to load the new table (does not interrupt in-flight I/O)
   - Calls `dmsetup resume` to activate the new table
   - The LV now has 50 GiB more sectors, but the filesystem does not yet know about them

5. **Filesystem resize (the `-r` flag):**
   - LVM detects the filesystem type (via `blkid` or `lsblk`)
   - For ext4: calls `resize2fs /dev/vg/lv` (online resize, no umount needed)
   - For XFS: calls `xfs_growfs /mountpoint` (must be mounted)
   - The filesystem extends its block group descriptors, inode tables, and free space bitmap to cover the new blocks

6. **Metadata archive:** LVM saves the old metadata to `/etc/lvm/archive/` for potential rollback.

7. **The entire operation is online** -- no umount, no downtime, no I/O pause (except a brief dm table swap measured in microseconds).

---

## Category 2: RAID

### Q5. You need to choose a RAID level for a production PostgreSQL server with 8 NVMe drives. Walk through your decision process.

**Difficulty:** Senior | **Category:** RAID Design

**Answer:**

1. **Requirements analysis for a production database:**
   - High random IOPS (both read and write) for OLTP workloads
   - Low write latency (PostgreSQL WAL commits are latency-sensitive)
   - Fault tolerance (at least 1 disk failure without data loss)
   - Fast rebuild time (minimize vulnerability window)

2. **Eliminate unsuitable levels:**
   - RAID 0: no redundancy -- unacceptable for any production data
   - RAID 5: single parity, 4x write penalty, slow rebuild, URE risk with large NVMe (dangerous with >2 TiB drives)
   - RAID 6: dual parity tolerates 2 failures, but 6x write penalty -- poor for write-heavy OLTP

3. **RAID 10 is the correct choice:**
   - 8 drives in RAID 10 = 4 mirror pairs striped together
   - Write penalty: 2x (each write goes to 2 drives in a mirror pair)
   - Read performance: effectively 8x (reads spread across all drives)
   - Fault tolerance: survives 1 failure per mirror pair (up to 4 simultaneous failures if each is in a different pair)
   - Rebuild time: only the mirror partner needs to resync (~minutes for NVMe, not hours)
   - 50% capacity efficiency: 8 x 2 TiB = 8 TiB usable

4. **Implementation:**
   - Use `mdadm --create /dev/md0 --level=10 --raid-devices=8 /dev/nvme[0-7]n1p1`
   - Layer LVM on top: `pvcreate /dev/md0` -> `vgcreate vg_db /dev/md0` -> separate LVs for WAL, data, temp
   - Separate WAL on its own LV for isolation from data I/O
   - Configure `mdadm --monitor` with alerting

5. **Why not LVM RAID (`--type raid10`)?**
   - LVM RAID uses `dm-raid` which is built on the md kernel module -- functionally equivalent
   - mdadm has more mature tooling, better monitoring ecosystem, and more administrator familiarity
   - LVM RAID is acceptable if you prefer unified LVM management, but mdadm is the battle-tested choice

---

### Q6. Explain the RAID 5 write hole. Why is it dangerous, and what mitigations exist?

**Difficulty:** Staff | **Category:** RAID Internals

**Answer:**

1. **The write hole defined:**
   - RAID 5 updates data and parity blocks on different disks as separate I/O operations
   - If a crash occurs between writing the data block and updating the parity block, they become inconsistent
   - This inconsistency is **silent** -- normal reads return correct data directly from the data blocks
   - The corruption manifests only during rebuild after a disk failure: parity is used to reconstruct the missing disk, but the parity is wrong, so the reconstructed data is garbage

2. **Why it is dangerous in production:**
   - You will not detect the problem until a disk failure occurs -- possibly months after the inconsistency was introduced
   - The "reconstructed" data on the replacement disk will contain random corruption
   - There is no mechanism in standard RAID 5 to detect or correct this retroactively

3. **Mitigations:**
   - **Write-intent bitmap (mdadm):** Tracks which stripes have in-flight writes. After a crash, only those stripes are resynchronized. Does not prevent the hole but limits its blast radius.
   - **Battery-Backed Unit (BBU) or NVRAM on hardware RAID:** Completes in-flight writes from cache after power restoration, preventing the inconsistency.
   - **RAID scrubbing:** Periodic parity verification (`echo check > /sys/block/md0/md/sync_action`) detects mismatches, though it cannot determine which copy is correct.
   - **ZFS RAID-Z:** Uses variable-width stripes that are never updated in place, completely eliminating the write hole by design.
   - **The real mitigation:** Use RAID 10 instead of RAID 5 for production data. Mirrors do not have parity, so there is no write hole.

---

### Q7. What is the practical risk of Unrecoverable Read Errors (URE) during RAID 5 rebuild with modern large disks?

**Difficulty:** Senior | **Category:** RAID Reliability

**Answer:**

1. **URE rate specification:**
   - Consumer SATA/NAS drives: 10^14 bits per URE (1 error per 12.5 TiB read)
   - Enterprise SAS drives: 10^15 bits per URE (1 error per 125 TiB read)

2. **Data read during rebuild:**
   - RAID 5 rebuild reads every block on every surviving disk
   - For a 5-disk array with 10 TiB drives: rebuild reads 4 x 10 TiB = 40 TiB
   - Probability of at least one URE on consumer drives: 1 - (1 - 40/12.5) is approximated as ~96% (simplified; actual probability uses: 1 - e^(-40/12.5) = ~96%)
   - Even with enterprise drives: 1 - e^(-40/125) = ~27%

3. **Impact of URE during rebuild:**
   - If a URE occurs on a surviving disk during reconstruction, that sector's data cannot be reconstructed
   - mdadm will mark the rebuild as failed or will fill the sector with zeros
   - The rebuilt disk has corrupted data, and the array may remain degraded

4. **Why RAID 5 is considered deprecated for large disks:**
   - With drives exceeding 2 TiB, the probability of a successful rebuild drops below acceptable levels
   - Rebuild times of 12-48 hours for large arrays leave extended vulnerability windows
   - RAID 6 doubles the parity (requires 2 simultaneous UREs on different disks) -- dramatically safer
   - RAID 10 only needs to read from one mirror partner -- reads the size of one disk, not N-1 disks

5. **Production recommendation:**
   - Drives <= 1 TiB: RAID 5 is still statistically acceptable (though RAID 10 is still preferred)
   - Drives > 2 TiB: RAID 5 is **not acceptable**; use RAID 6 or RAID 10
   - Always use enterprise drives (10^15 URE rate) in RAID arrays
   - Schedule weekly scrubs to detect and repair UREs proactively, before they become critical during a rebuild

---

## Category 3: Partitioning & Disk Management

### Q8. When would you choose GPT over MBR, and what are the practical implications for server environments?

**Difficulty:** Senior | **Category:** Partitioning

**Answer:**

1. **Default to GPT in all modern environments.** MBR is legacy and should only be used when forced by ancient BIOS hardware.

2. **GPT advantages for servers:**
   - Supports disks larger than 2 TiB (MBR maximum)
   - Up to 128 partitions (MBR: 4 primary, or 3 primary + 1 extended with logical partitions)
   - Redundant partition table (primary at start of disk, backup at end) -- recoverable if primary is damaged
   - CRC32 checksums on partition table entries -- detects corruption
   - 16-byte GUID partition type IDs -- no ambiguity or collision

3. **MBR still appears in practice:**
   - Legacy BIOS-only systems that cannot boot GPT
   - Some cloud VM images ship with MBR for broad compatibility
   - Recovery situations where you boot from old media
   - Virtual machines where the hypervisor emulates legacy BIOS

4. **Server partitioning best practices:**
   - Use GPT with a single partition per data disk (type `8e00` for LVM)
   - For boot disks: GPT with an EFI System Partition (ESP, type `ef00`, 512 MiB, FAT32) for UEFI boot
   - Always partition disks even when using LVM on the whole disk -- a partition table makes the disk recognizable to recovery tools and prevents accidental overwrite
   - Use `sgdisk` for scriptable GPT operations: `sgdisk -Z /dev/sdX && sgdisk -n 1:0:0 -t 1:8e00 /dev/sdX`

---

### Q9. How do you resize a cloud EBS volume attached to a running EC2 instance without downtime? What are the layers involved?

**Difficulty:** Senior | **Category:** Cloud Storage

**Answer:**

1. **Three layers must be resized (in this order):**
   - Layer 1: Cloud block device (EBS volume)
   - Layer 2: Partition table (if the disk is partitioned)
   - Layer 3: Filesystem (or LVM PV + LV + filesystem)

2. **Step-by-step procedure:**
   ```
   a. aws ec2 modify-volume --volume-id vol-XXX --size NEW_SIZE
   b. Wait for volume modification to complete (aws ec2 describe-volumes-modifications)
   c. growpart /dev/xvdf 1           # Extend partition 1 to fill the larger disk
   d. If LVM: pvresize /dev/xvdf1    # Inform LVM the PV is larger
   e. If LVM: lvextend -l +100%FREE -r /dev/vg/lv
   f. If no LVM: resize2fs /dev/xvdf1 (ext4) or xfs_growfs /mountpoint (xfs)
   ```

3. **Key considerations:**
   - EBS volume modification has a cooldown period (6 hours) before another modification
   - The volume enters an "optimizing" state after modification; I/O continues but may be slower
   - NVMe-backed instances (Nitro) use `/dev/nvmeXn1` device names, not `/dev/xvdf`
   - `growpart` requires the `cloud-utils-growpart` package
   - All operations are online -- no unmount or reboot needed for ext4 and xfs growth

4. **LVM adds flexibility:**
   - You can add a second EBS volume and `vgextend` instead of resizing the existing one
   - `pvmove` lets you migrate data between EBS volumes of different types (gp3 -> io2) online
   - Thin provisioning on top of EBS allows over-provisioning within the VM

---

## Category 4: LVM Operations & Troubleshooting

### Q10. You arrive on-call and find a production server with every filesystem read-only and applications crashing. The root cause is a full VG. Walk through your emergency response.

**Difficulty:** Senior | **Category:** Incident Response

**Answer:**

1. **Immediate assessment (30 seconds):**
   ```
   vgs                    # Confirm VG has 0 free space
   lvs -a                 # Check for snapshots consuming space
   df -h                  # Confirm which filesystems are affected
   ```

2. **Quick win -- remove stale snapshots (if any):**
   - `lvs -a -o lv_name,snap_percent,origin` to find snapshots
   - `lvremove -f /dev/vg/snapshot_name` to immediately free COW space
   - This is the fastest way to reclaim space -- snapshots can be recreated later

3. **If no snapshots -- free space inside filesystems:**
   - `du -xh /var/log | sort -rh | head -10` to find large log files
   - Truncate (do not delete) large log files: `> /var/log/large.log`
   - Check for deleted-but-open files: `lsof +L1` (space is not freed until file handle is closed)
   - Restart the process holding the deleted file to reclaim space

4. **If still stuck -- emergency disk addition:**
   - Attach a new disk (or EBS volume in cloud)
   - `pvcreate /dev/sdX && vgextend vg_name /dev/sdX`
   - Space is immediately available to all LVs in the VG

5. **Remount read-write:**
   - `mount -o remount,rw /` (if root went read-only)
   - Or `lvchange -ay /dev/vg/lv` if LV was deactivated

6. **Prevention:**
   - Alert on VG free space < 10% (`vgs -o vg_free`)
   - Keep OS and data in separate VGs
   - Autoextend thin pools in `/etc/lvm/lvm.conf`

---

### Q11. How does pvmove work internally? What happens if it is interrupted, and what are the risks?

**Difficulty:** Staff | **Category:** LVM Internals

**Answer:**

1. **pvmove mechanism:**
   - Creates a temporary mirrored LV (`[pvmove0]`) using `dm-mirror`
   - For each PE being moved: mirrors the PE from source to destination
   - After each PE (or batch of PEs) is mirrored, updates the LV metadata to point to the new PE location
   - Checkpoints progress in LVM metadata periodically

2. **I/O during pvmove:**
   - The LV remains fully accessible throughout the operation
   - Reads come from whichever copy is available (preferring the already-migrated copy)
   - Writes go to both the old and new locations (mirrored write)
   - This doubles write I/O and increases latency during the migration

3. **If pvmove is interrupted (power loss, crash):**
   - On next boot, `lvs -a` shows `[pvmove0]` still present
   - Running `pvmove` again (without arguments) resumes from the last checkpoint
   - `pvmove --abort` cancels the operation and reverts all PEs to their original locations
   - The LV data is consistent because the mirror ensures both copies exist until the metadata pointer is updated

4. **Risks:**
   - **Block size mismatch:** Moving from 512-byte to 4096-byte sector devices can cause silent filesystem corruption (documented Red Hat bug)
   - **VG space:** pvmove temporarily needs extra space in the VG for the mirror metadata
   - **Performance impact:** 2x write amplification during migration; not suitable during peak traffic
   - **Long duration for large volumes:** a 1 TiB pvmove at 200 MB/s takes ~85 minutes; power/network stability is critical

5. **Best practices:**
   - Verify block sizes match: `blockdev --getbsz /dev/source` vs `blockdev --getbsz /dev/dest`
   - Take a snapshot before pvmove for rollback safety
   - Run during maintenance windows for write-heavy volumes
   - Monitor with `lvs -a -o+copy_percent`

---

### Q12. Explain thin pool overprovisioning. What happens when a thin pool runs out of space?

**Difficulty:** Staff | **Category:** Thin Provisioning

**Answer:**

1. **Overprovisioning defined:**
   - A thin pool has a fixed physical data size (e.g., 500 GiB)
   - Thin LVs created in the pool can have virtual sizes totaling more than the pool (e.g., 10 x 200 GiB = 2 TiB of virtual storage in a 500 GiB pool)
   - Actual physical space is allocated only when data is written (demand allocation)
   - This is analogous to memory overcommit: works until everyone actually uses their allocation

2. **What happens when the pool fills:**
   - The `dm-thin` kernel target cannot allocate a new block for an incoming write
   - The I/O is **queued** (not errored) -- the process blocks waiting for space
   - If the pool has `error_if_no_space` mode: I/O returns EIO instead of blocking
   - All thin LVs in the pool are affected simultaneously -- this is a pool-wide event
   - If the pool's metadata LV also fills, all thin LVs become permanently damaged

3. **Mitigation hierarchy:**
   - **Autoextend (primary):** Configure in `/etc/lvm/lvm.conf`:
     ```
     thin_pool_autoextend_threshold = 70
     thin_pool_autoextend_percent = 20
     ```
     Requires free PEs in the VG for autoextend to succeed.
   - **Monitoring (secondary):** Alert on `lvs -o data_percent` and `metadata_percent` at 70%
   - **Manual extend:** `lvextend -L +100G VG/thinpool` adds space to the pool's data LV
   - **Metadata monitoring:** `lvs -o metadata_percent` -- if metadata hits 100%, the pool is unrecoverable without `thin_repair`

4. **Recovery from full thin pool:**
   - If blocked (not error mode): `lvextend -L +SIZE VG/thinpool` unblocks queued I/Os immediately
   - If metadata damaged: `thin_check /dev/VG/thinpool_tmeta` and `thin_repair` to recover
   - Worst case: if metadata is irrecoverable, all thin LVs are lost

---

## Category 5: Scenario-Based Questions

### Q13. A developer reports their application is experiencing intermittent I/O errors and the disk usage shows 100% for /data. But `df` shows 80% used. What is happening?

**Difficulty:** Staff | **Category:** Debugging

**Answer:**

1. **Hypothesis 1: Inode exhaustion (filesystem full, but not by data):**
   - `df -i /data` -- check inode usage
   - If inodes are 100% used but data is 80%, the filesystem cannot create new files despite having free blocks
   - Common with millions of small files (mail spools, cache directories)
   - Fix: delete unnecessary files, or recreate filesystem with more inodes (`mkfs.ext4 -N`)

2. **Hypothesis 2: Reserved blocks for root:**
   - ext4 reserves 5% of blocks for root by default
   - If the application runs as non-root, it sees "disk full" at 95%, while `df` shows 5% free for root
   - Check: `tune2fs -l /dev/vg/lv | grep "Reserved block count"`
   - Fix: reduce reserved blocks: `tune2fs -m 1 /dev/vg/lv` (reduce to 1%)

3. **Hypothesis 3: Thin pool underlying the LV is full:**
   - `lvs -o+data_percent --select 'pool_lv!=""'`
   - If `data_percent` is 100%, the thin pool is exhausted even though the filesystem inside the LV has free space
   - The filesystem sees its virtual size but the thin pool cannot back new block allocations
   - Fix: `lvextend -L +SIZE VG/thinpool`

4. **Hypothesis 4: Deleted-but-open files:**
   - `lsof +L1 /data` -- shows files deleted from the directory but still held open by a process
   - The space is not freed until the process closes the file handle
   - Fix: restart the offending process, or truncate via `/proc/PID/fd/FD`

5. **Investigation order:** Check `df -i` first (1 second), then `lvs data_percent` (thin pool), then `lsof +L1`, then `tune2fs` reserved blocks.

---

### Q14. Your monitoring shows a RAID 10 array with 8 disks has been running in degraded mode for 6 hours, but no alert was triggered. How do you handle this?

**Difficulty:** Senior | **Category:** RAID Operations

**Answer:**

1. **Immediate actions:**
   - `cat /proc/mdstat` -- identify which disk(s) failed and array state
   - `mdadm --detail /dev/md0` -- get full state, active/failed/spare counts
   - `smartctl -a /dev/sdX` -- check SMART data on failed disk (and its mirror partner)
   - Determine if the failed disk's mirror partner is still healthy

2. **Risk assessment:**
   - RAID 10 with 1 failure: the failed disk's mirror partner is now a single point of failure
   - If the mirror partner fails, that stripe is lost and the array is destroyed
   - Priority: replace the failed disk immediately

3. **Replacement procedure:**
   - If hot-spare is configured: verify automatic rebuild started (`/proc/mdstat` shows resync percentage)
   - If no hot-spare: `mdadm --remove /dev/md0 /dev/sdX1` then `mdadm --add /dev/md0 /dev/sdY1`
   - Monitor rebuild: `watch cat /proc/mdstat`

4. **Fix the monitoring gap:**
   - Check why `mdadm --monitor` did not alert: is the daemon running? (`systemctl status mdmonitor`)
   - Check `/etc/mdadm/mdadm.conf` for `MAILADDR` or `PROGRAM` directives
   - Verify mail delivery works: `echo test | mail -s "test" oncall@company.com`
   - Add `/proc/mdstat` scraping to Prometheus/Nagios: `node_exporter` exposes `node_md_disks_active` metrics
   - Create PagerDuty alert rule for `node_md_state != "active"`

5. **Prevention:**
   - Configure hot spares: at least 1 per array
   - Schedule weekly RAID scrubs
   - Test alerting monthly by simulating a failure in staging
   - Document the RAID rebuild procedure in the team runbook

---

### Q15. You need to migrate a production server's data from local SATA SSDs to NVMe without any downtime. Describe your approach using LVM.

**Difficulty:** Staff | **Category:** Storage Migration

**Answer:**

1. **Prerequisites:**
   - Both old and new drives are PVs in the same VG (or the new drive can be added)
   - Verify block sizes match: `blockdev --getbsz /dev/sda1` vs `blockdev --getbsz /dev/nvme0n1p1`
   - Ensure VG has room for temporary mirror overhead

2. **Step-by-step procedure:**
   ```
   a. Add new NVMe as PV:
      pvcreate /dev/nvme0n1p1
      vgextend vg_prod /dev/nvme0n1p1

   b. Take a precautionary snapshot:
      lvcreate -s -L 50G -n lv_data_premove /dev/vg_prod/lv_data

   c. Migrate with pvmove:
      pvmove /dev/sda1 /dev/nvme0n1p1
      # Monitor: lvs -a -o+copy_percent

   d. After completion, verify:
      lvs -o+devices /dev/vg_prod/lv_data    # Should show only nvme0n1p1
      pvs                                      # sda1 should show 0 used

   e. Remove old drive from VG:
      vgreduce vg_prod /dev/sda1
      pvremove /dev/sda1

   f. Remove snapshot:
      lvremove /dev/vg_prod/lv_data_premove
   ```

3. **Risk mitigation:**
   - Run during low-traffic period (pvmove doubles write I/O)
   - Ensure UPS is healthy (interrupted pvmove can cause corruption)
   - Have `pvmove --abort` ready as a rollback command
   - Monitor disk latency during migration: `iostat -x 1` on both devices

4. **Alternative for cross-VG migration (different VG or different machine):**
   - Cannot use pvmove across VGs
   - Use `dd`, `rsync`, or filesystem-level tools (xfsdump/xfsrestore)
   - For cross-machine: set up new LVM on target, use rsync + final sync with brief downtime

---

### Q16. Explain how you would design the storage layout for a high-availability database cluster using LVM and RAID.

**Difficulty:** Principal | **Category:** Storage Architecture

**Answer:**

1. **Physical layout (per node, assuming 12 NVMe drives):**
   - 2 drives: RAID 1 (mdadm) for OS (`/`, `/boot`, swap)
   - 2 drives: RAID 1 for WAL (`pg_wal`): separate physical I/O path for write-ahead log
   - 8 drives: RAID 10 for data (tablespaces, indexes)
   - Rationale: WAL is sequential write, data is random I/O; separate RAID arrays prevent I/O contention

2. **LVM layer:**
   - `vg_os` on md0 (RAID 1 OS): `lv_root` (50G), `lv_var` (100G), `lv_swap` (32G)
   - `vg_wal` on md1 (RAID 1 WAL): `lv_pgwal` (100G)
   - `vg_data` on md2 (RAID 10 data): `lv_pgdata` (remaining space, grow as needed)
   - Separate VGs ensure OS stability even if data VG is stressed

3. **Filesystem choices:**
   - ext4 for OS volumes (shrinkable, mature)
   - XFS for data volumes (excellent large-file performance, online grow)
   - Mount options: `noatime,nodiratime` (reduce metadata writes); `data=writeback` for ext4 on WAL (PostgreSQL handles its own journal)

4. **Monitoring:**
   - RAID: `mdadm --monitor` -> PagerDuty; weekly scrubs via systemd timer
   - LVM: VG free space, thin pool percentage if used
   - Filesystem: df percentage, inode usage
   - Disk health: SMART via `smartd`, alert on reallocated sectors

5. **Capacity planning:**
   - Start LVs at 60% of available VG space
   - Leave 40% free in each VG for emergency extension and snapshot operations
   - Set up automated growth alerts at 80% LV usage
   - Document the lvextend procedure in the runbook for on-call engineers

---

### Q17. What is the difference between `/dev/mapper/vg-lv`, `/dev/vg/lv`, and `/dev/dm-N`? Which should you use in fstab?

**Difficulty:** Senior | **Category:** Device Naming

**Answer:**

1. **The three paths are all the same block device:**
   - `/dev/dm-N` (e.g., `/dev/dm-3`): the actual device node created by the device-mapper kernel subsystem. The number N is assigned at activation time and is **not stable** across reboots.
   - `/dev/mapper/vg_name-lv_name`: a symlink created by udev/device-mapper. Uses the VG-LV naming convention with hyphens doubled (e.g., `vg-prod` becomes `vg--prod`). **Stable across reboots.**
   - `/dev/vg_name/lv_name`: a symlink created by LVM's udev rules. Human-readable path. **Stable across reboots.**

2. **For `/etc/fstab`, use none of the above directly. Use the UUID:**
   ```
   UUID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  /data  xfs  defaults  0 2
   ```
   - UUID is embedded in the filesystem and is completely stable regardless of device naming
   - Survives VG renames, hardware changes, and boot order variations
   - Find it with: `blkid /dev/vg_name/lv_name`

3. **If you must use a device path in fstab:**
   - `/dev/mapper/vg_name-lv_name` is the most portable and commonly used
   - `/dev/vg_name/lv_name` also works but is slightly less standard
   - **Never use** `/dev/dm-N` -- the number can change between reboots

4. **In scripts and configuration management:**
   - Use `/dev/mapper/vg_name-lv_name` for consistency
   - Use `blkid` to resolve UUIDs programmatically

---

### Q18. How would you recover an LVM volume group where the metadata on one PV is corrupted but the other PVs are intact?

**Difficulty:** Staff | **Category:** Recovery

**Answer:**

1. **Diagnosis:**
   ```
   pvs                          # Shows [unknown] for corrupted PV or errors
   pvck --dump headers /dev/sdX # Verify PV label integrity
   pvck --dump metadata /dev/sdX # Try to read metadata from the PV
   vgdisplay --partial vg_name  # Show VG with missing PV info
   ```

2. **Key fact: VG metadata is replicated on every PV in the VG.**
   - If `/dev/sda1` has corrupted metadata but `/dev/sdb1` (another PV in the same VG) is intact, the VG metadata can be read from `/dev/sdb1`
   - LVM also automatically backs up metadata to `/etc/lvm/backup/` and `/etc/lvm/archive/`

3. **Recovery procedure:**
   ```
   # List available backups
   ls -lt /etc/lvm/archive/vg_name*

   # Restore metadata to the corrupted PV
   vgcfgrestore -f /etc/lvm/archive/vg_name_NNNNN.vg vg_name

   # If the PV UUID on the corrupted device has changed:
   vgcfgrestore --force -f /etc/lvm/archive/vg_name_NNNNN.vg vg_name

   # Reactivate
   vgchange -ay vg_name

   # Verify
   pvck /dev/sdX
   lvs vg_name
   ```

4. **If automatic backups are also lost:**
   - `pvck --dump metadata /dev/sdb1` (intact PV) can extract the metadata text
   - Copy this metadata to a file and use `vgcfgrestore -f` with it
   - As absolute last resort: `dd` the metadata area from an intact PV to the corrupted PV (matching offsets), but this is dangerous and requires exact knowledge of metadata area layout

5. **Prevention:**
   - Regular `vgcfgbackup` to an off-disk location (not just `/etc/lvm/archive/`)
   - Include `/etc/lvm/` in your backup strategy
   - Use VGs with 3+ PVs to increase metadata redundancy
   - Monitor for `pvck` errors in periodic health checks

---

### Q19. What is the Linux device mapper `dm-cache` target, and how would you use it to accelerate a slow HDD-backed volume with an SSD?

**Difficulty:** Principal | **Category:** Advanced LVM

**Answer:**

1. **dm-cache overview:**
   - Device-mapper target that uses a fast device (SSD/NVMe) as a cache for a slow device (HDD)
   - Three components: origin LV (slow), cache data LV (fast), cache metadata LV (fast)
   - Supports writeback (writes go to SSD first, flushed to HDD later) and writethrough (writes go to both simultaneously) policies
   - The `smq` (Stochastic Multi-Queue) policy is the default and recommended cache policy

2. **Setup with LVM:**
   ```bash
   # Assume: vg_data has both HDD PV (/dev/sda1) and SSD PV (/dev/sdb1)

   # Create the slow origin LV on HDD
   lvcreate -L 1T -n lv_data vg_data /dev/sda1

   # Create cache pool on SSD
   lvcreate --type cache-pool -L 100G -n lv_cache vg_data /dev/sdb1

   # Attach cache to origin
   lvconvert --type cache --cachevol lv_cache vg_data/lv_data

   # Verify
   lvs -a -o+cache_mode,cache_policy
   ```

3. **Cache modes:**
   - `writethrough`: safe, no data loss if SSD fails, but no write acceleration
   - `writeback`: fast writes, but SSD failure can lose dirty data
   - Production recommendation: `writethrough` unless SSD is itself on RAID 1

4. **Monitoring:**
   - `lvs -o+cache_dirty_blocks,cache_read_hits,cache_read_misses,cache_write_hits,cache_write_misses`
   - Calculate hit ratio; if below 80%, the cache is undersized or the workload is not cache-friendly

5. **When to use vs alternatives:**
   - dm-cache: best for mixed read/write workloads on existing HDD infrastructure
   - bcache: kernel-level alternative, but not integrated with LVM
   - Simply putting hot data on SSD LVs: simpler, but requires manual data placement decisions
   - Full NVMe migration: if budget allows, eliminate the caching complexity entirely
