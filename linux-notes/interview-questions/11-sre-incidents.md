# Interview Questions 11: Real-World SRE Incidents

> FAANG / Staff+ SRE interview preparation. All answers structured with bullets/numbered lists.
> Full notes: [SRE Incidents](../11-real-world-sre-usecases/sre-incidents.md)

---

## Q1: Describe a time you led incident response for a P1 outage. What was your decision-making process?

- **Use the STAR framework:**
  1. **Situation:** Identify the service, scale of impact (users, revenue), and when you were engaged
  2. **Task:** Your specific role -- Incident Commander, on-call engineer, subject matter expert
  3. **Action:** Walk through the timeline:
     - How you triaged: checked dashboards, identified blast radius
     - How you communicated: opened incident channel, posted status updates every 30 minutes
     - How you chose mitigation over root cause: rolled back first, investigated after service was restored
     - How you coordinated: pulled in the database team when you identified the dependency
  4. **Result:** Time to mitigate, user impact, post-mortem outcomes, action items completed

- **Key signals interviewers look for:**
  - Calm under pressure -- followed the runbook or adapted rationally
  - Clear communication -- stakeholders kept informed with facts, not speculation
  - Bias toward action -- made decisions with incomplete information
  - Blameless mindset -- describes systemic failures, not individual blame

---

## Q2: How do you conduct a blameless post-mortem? What makes a post-mortem effective?

- **Structure of an effective post-mortem:**
  1. **Timeline:** Minute-by-minute reconstruction from detection to resolution
  2. **Root cause analysis:** "5 Whys" or fault tree analysis -- go beyond the proximate cause
  3. **Contributing factors:** Monitoring gaps, process failures, architectural weaknesses that allowed this
  4. **Impact assessment:** Duration, users affected, revenue impact, SLO budget consumed
  5. **Action items:** Each item is specific, assigned an owner, has a deadline, tracked to completion
  6. **Lessons learned:** What went well (prevented worse outcome) and what did not go well

- **Blameless means:**
  - Focus on systems, not individuals: "The deployment pipeline lacked a canary phase" not "John deployed without testing"
  - Assume people acted rationally given the information they had
  - Separate decision quality from outcome quality
  - Reward transparency -- the person who reports a mistake should be thanked, not punished

- **What makes it effective:**
  - Action items are tracked to completion (not written and forgotten)
  - Shared broadly so other teams learn from your incidents
  - Repeat incidents are flagged -- if the same failure class recurs, previous action items were insufficient

---

## Q3: How do you decide between mitigating immediately vs. investigating root cause during an incident?

- **Always mitigate first. The hierarchy is:**
  1. **Mitigate user impact** -- rollback, failover, traffic shed, feature flag disable (target: <15 min)
  2. **Stabilize the system** -- ensure mitigation is durable, not a 10-minute band-aid
  3. **Investigate root cause** -- only after mitigation is confirmed stable

- **The exception:**
  - If mitigation risks data corruption or data loss, limited investigation may be warranted first
  - Example: rolling back a database migration might lose writes -- understand state before acting

- **Decision framework:**
  - Recent deployment + rollback is safe: roll back immediately, investigate later
  - Cause unknown: apply most reversible mitigation (drain traffic, disable feature flag) and investigate in parallel
  - System is self-healing (auto-scaler replacing nodes): monitor 5 min before intervening

---

## Q4: Walk through how you would diagnose a cascading OOM failure across a microservice fleet.

1. **Identify blast radius:** Check monitoring for which services are OOMing and the timeline of propagation
2. **Check dependency graph:** Use service mesh or tracing to identify the upstream trigger for the cascade
3. **On an affected pod:**
   - `dmesg -T | grep "Out of memory"` -- confirm OOM kills, see which process was killed
   - `cat /sys/fs/cgroup/memory/memory.stat` -- check RSS, cache, swap within the cgroup
   - `ss -tnp | wc -l` -- count open connections (connection pileup causes memory growth)
4. **Check downstream dependency:** Is it slow (queuing requests in memory) or down (triggering retry loops)?
5. **Calculate memory budget:** `(concurrent_requests * memory_per_request) + heap + metaspace + thread_stacks` vs. cgroup limit
6. **Mitigate:**
   - Enable circuit breakers to shed load from failing dependency
   - Reduce client timeouts to release connection memory faster
   - Apply rate limiting at the entry point to reduce concurrent load

---

## Q5: A host has high load average but low CPU utilization. What is happening and how do you investigate?

- **Diagnosis: Processes in uninterruptible sleep (D state) -- usually I/O wait:**
  1. `vmstat 1 5` -- check `b` (blocked) column and `wa` (I/O wait) column
  2. `ps aux | awk '$8 ~ /D/ {print}'` -- list D-state processes
  3. `cat /proc/<pid>/stack` -- kernel stack of D-state process (what it is waiting on)
  4. `iostat -xz 1 3` -- check `await` (I/O latency) and `%util` (device saturation)
  5. `dmesg -T | grep -i "error\|reset\|timeout"` -- disk or controller errors

- **Common causes:**
  - Failing disk with high I/O latency (`smartctl -a /dev/sdX`)
  - NFS server unresponsive (stack shows `nfs4_call_sync`)
  - Disk I/O saturation from write storm (`iotop` to identify writer)
  - Kernel bug causing permanent D-state (check kernel version against known bugs)

---

## Q6: Explain SLI, SLO, SLA, and error budgets. How do they work together?

- **SLI (Service Level Indicator):**
  - Quantitative measure of service behavior from the user's perspective
  - Examples: request latency (p99), error rate (5xx / total), availability (successful / total)

- **SLO (Service Level Objective):**
  - Internal target for an SLI over a time window
  - Example: "99.9% of requests succeed with <200ms latency over a 30-day rolling window"

- **SLA (Service Level Agreement):**
  - External contract with consequences for missing the target
  - Always less aggressive than the SLO (SLO acts as a buffer)
  - Example: "99.5% availability, or customer receives service credits"

- **Error Budget:**
  - Calculated as: `100% - SLO`
  - For 99.9% availability SLO: error budget = 0.1% = 43.8 minutes/month of allowed downtime
  - Governs the balance between reliability and velocity:
    - Budget remaining: ship features, run experiments
    - Budget exhausted: feature freeze, invest in reliability

- **Burn rate alerting:**
  - Fast burn: >2% of monthly budget consumed in 1 hour = page immediately
  - Slow burn: >5% of monthly budget consumed in 6 hours = create investigation ticket

---

## Q7: How does the Linux OOM killer decide which process to kill? How would you influence it?

- **OOM killer scoring:**
  1. Kernel computes `oom_score` for each process (0-1000) based on: RSS usage, process age, CPU time, nice value
  2. Higher score = killed first
  3. `oom_score_adj` (-1000 to +1000) modifies the score
  4. Check: `cat /proc/<pid>/oom_score` and `cat /proc/<pid>/oom_score_adj`

- **Influencing the decision:**
  1. Protect critical services: `echo -1000 > /proc/<pid>/oom_score_adj` (or `OOMScoreAdjust=-1000` in systemd unit)
  2. Sacrifice expendable processes: `echo 1000 > /proc/<pid>/oom_score_adj`
  3. Cgroup isolation: set memory limits per cgroup to contain blast radius
  4. Nuclear option: `vm.panic_on_oom=1` reboots host instead of killing processes

- **In Kubernetes:**
  - QoS classes: Guaranteed (requests=limits) > Burstable > BestEffort (no requests/limits)
  - BestEffort pods are always killed first
  - Set `resources.requests == resources.limits` for critical pods

---

## Q8: Explain how you would design SLIs and SLOs for a payment processing service.

- **SLIs:**
  1. **Availability:** Proportion of requests returning a definitive response (success or known failure) vs. timeout/5xx
  2. **Latency:** p50, p95, p99 of end-to-end payment processing (measured at client, not server)
  3. **Correctness:** Proportion where debit matches authorized amount (detects silent corruption)
  4. **Durability:** Proportion of committed records retrievable after 24 hours

- **SLOs:**
  1. Availability: 99.99% (4.38 min/month -- payment is critical path)
  2. Latency: p99 < 500ms, p50 < 100ms over 30-day window
  3. Correctness: 100% (zero tolerance -- any failure is SEV1)
  4. Durability: 99.999999% (eight nines)

- **Error budget policy:**
  - Budget > 50%: ship features, run chaos tests
  - Budget < 25%: feature freeze, reliability-only engineering
  - Budget exhausted: mandatory post-mortem, executive review, deployment freeze

---

## Q9: You discover 0.01% of reads from your storage cluster return corrupted data. Walk through your investigation.

1. **Quantify:** Confirm rate with integrity audit; identify affected hosts, time range, data pattern
2. **Application layer:** Compare source data with stored data immediately after write to rule out application bugs
3. **Storage hardware:**
   - `smartctl -a /dev/sdX` -- check Reallocated_Sector_Ct, Current_Pending_Sector
   - `cat /proc/mdstat` -- RAID health (degraded?)
   - RAID controller BBU status
4. **Filesystem:**
   - `xfs_repair -n /dev/sdX` -- dry-run integrity check
   - Cross-reference kernel version with known filesystem bugs
   - `dmesg -T | grep -i "error\|corrupt\|checksum"`
5. **Bit-rot detection:**
   - XFS/ext4: no built-in checksumming -- corruption is silent
   - ZFS: `zpool scrub` detects and reports; Btrfs: `btrfs scrub`
6. **Memory (ECC errors cause corruption during writes):**
   - `edac-util -s` -- ECC error counters
   - `cat /var/log/mcelog` -- machine check exceptions
7. **Network (if data traverses network):**
   - TCP checksums are weak (16-bit) -- can miss corruption
   - `ethtool -S eth0 | grep error` -- NIC errors

---

## Q10: Explain MTTD, MTTM, MTTR, and MTBF. Which matters most for SRE?

- **MTTD (Mean Time to Detect):** Time from incident start to team awareness
  - Reduced by: better monitoring, tighter SLO alerting, synthetic probes

- **MTTM (Mean Time to Mitigate):** Time from detection to user impact resolved
  - Reduced by: runbooks, automation, rollback capabilities, circuit breakers

- **MTTR (Mean Time to Resolve):** Time from detection to full resolution (root cause fixed)
  - Reduced by: faster post-mortems, better tooling, architectural improvements

- **MTBF (Mean Time Between Failures):** Time between incidents
  - Increased by: chaos engineering, testing, architectural redundancy

- **Which matters most: MTTM.** Users care about when the pain stops. A team with consistent sub-15-minute MTTM is far more effective than one that prevents incidents but takes hours to mitigate.

---

## Q11: How would you implement a circuit breaker pattern to prevent cascading failures?

- **Three states:** Closed (normal) -> Open (failing) -> Half-Open (testing recovery)

- **State transitions:**
  1. **Closed -> Open:** Failure count exceeds threshold in time window (e.g., 50% failures in 10s)
  2. **Open behavior:** Return fallback immediately; start timeout timer (e.g., 30s)
  3. **Open -> Half-Open:** After timeout, allow a single probe request
  4. **Half-Open -> Closed:** Probe succeeds -- resume normal traffic
  5. **Half-Open -> Open:** Probe fails -- restart timeout

- **Implementation considerations:**
  - Per-destination breakers (not global) -- one failing endpoint should not break all
  - Retries happen inside the circuit breaker, not outside
  - Fallback must be meaningful: cached data, degraded response, not generic 500
  - Monitor breaker state as an SLI -- frequent Opens indicate reliability problems

---

## Q12: A distributed trace shows a 2-second service call, but downstream logs show 5ms response. Where is the 1,995ms?

- **Systematic elimination:**
  1. **Network latency:** `ping`, `traceroute` between hosts -- high RTT or packet loss?
  2. **Connection establishment:** New TCP connection (3-way handshake) vs. pool reuse? Check `ss -tnp`, pool metrics
  3. **DNS resolution:** `strace -e trace=network -T` -- check `getaddrinfo` duration
  4. **Load balancer queuing:** Check proxy logs for upstream time vs. total time
  5. **Client-side queuing:** Thread pool saturated? Check thread pool metrics, `jstack` for blocked threads
  6. **Kernel TCP buffers:** `ss -tnp -m` -- check send buffer saturation
  7. **Garbage collection:** GC logs around the timestamp for stop-the-world pauses
  8. **Clock skew:** Are both hosts NTP-synchronized? If not, timestamps are unreliable

---

## Q13: How do you differentiate between a slow network and a slow application?

- **Layer-by-layer isolation:**
  1. **Client-side:** Browser Network tab -- check TTFB vs. content download time
     - High TTFB + fast download = slow application (server processing)
     - Low TTFB + slow download = slow network (bandwidth)
  2. **Load balancer:** Check upstream response time in LB access logs
     - Fast upstream + slow client = network between LB and client
  3. **Server-side:** Application latency metrics (p50, p95, p99)
     - Fast server metrics = slowness is in the network path
  4. **Network diagnostics:**
     - `mtr -rn <destination>` -- check per-hop loss and latency
     - `tcpdump -w capture.pcap` -- analyze retransmissions, window size in Wireshark
     - `ss -ti` -- TCP RTT, retransmits, congestion window for active connections

---

## Q14: Your Kubernetes cluster is healthy but pods are stuck in Pending. What do you investigate?

1. `kubectl describe pod <pod>` -- read Events section for scheduler message
2. **Insufficient resources:** "0/N nodes available: insufficient cpu/memory"
   - Check `kubectl top nodes`, consider increasing node pool or reducing requests
3. **Affinity/taints:** "didn't match node selector, had taint..."
   - Check pod spec nodeSelector, affinity rules, and node taints/tolerations
4. **PVC binding:** "unbound PersistentVolumeClaims"
   - Check `kubectl get pvc`, storage provisioner logs
5. **Resource quotas:** "exceeded quota"
   - Check `kubectl describe resourcequota -n <namespace>`
6. **PDB blocking evictions:** Check `kubectl get pdb`
7. **Scheduler health:** `kubectl get pods -n kube-system | grep scheduler`
8. **Priority preemption:** Higher-priority pods may be evicting lower-priority ones

---

## Q15: Describe your approach to reducing toil on an SRE team.

1. **Measure:** Classify operational work -- if manual, repetitive, automatable, reactive, and scales linearly, it is toil
2. **Quantify:** Track percentage of time on toil. Google target: <50%
3. **Prioritize by ROI:**
   - High-frequency, low-complexity: automate first (cert renewal, disk cleanup)
   - Low-frequency, high-complexity: write runbooks first, automate later
4. **Automation strategies:**
   - Self-healing: auto-restart, auto-scale, auto-remediate known failures
   - ChatOps: common operations as Slack commands with approval workflows
   - GitOps: infrastructure changes via PRs, eliminating manual kubectl/ssh
5. **Organizational:**
   - Embed SRE in development: shared ownership reduces toil at the source
   - Toil budgets per team: too much ops toil earns engineering allocation to fix it
   - Regular toil reviews in sprint planning

---

## Q16: How would you handle a post-mortem where the root cause was a colleague's mistake?

- **The incident is never one person's fault. A blameless post-mortem asks:**
  1. What system allowed the mistake to have impact? (Missing guardrails, no canary, no rollback)
  2. What information was the person missing? (Poor docs, unclear process)
  3. What automation would have caught this? (Tests, linting, policy-as-code)
  4. What pressure contributed? (Deadline pressure to skip review)

- **In the document:**
  - Never name individuals in root cause analysis
  - Use role-based language: "the deployer" not "John"
  - Action items are systemic: "Add canary phase" not "Train John to deploy correctly"

- **If the pattern repeats:**
  - Escalate the systemic issue, not the individual
  - Invest in tooling and guardrails -- these scale; human vigilance does not

---

## Q17: Explain the thundering herd problem. How do you prevent it in production?

- **The problem:** Multiple processes/services simultaneously attempt the same action, overwhelming the target
  - All instances restart simultaneously and flood the database with cold-cache queries
  - A cache entry expires and all servers fetch it from the origin at the same time
  - A service comes back online and all queued clients reconnect instantly

- **Prevention strategies:**
  1. **Rolling restarts:** Deploy in batches with delays between batches (`serial: 5, pause: 60s`)
  2. **Exponential backoff with jitter:** Retries use `min(base * 2^attempt + random_jitter, max_backoff)`
  3. **Cache stampede protection:** "Lock and populate" -- one thread refreshes, others wait or use stale value
  4. **Load balancer slow-start:** HAProxy `slowstart 60s` ramps traffic gradually to new backends
  5. **Startup readiness gates:** Kubernetes readiness probes that only pass after cache warming
  6. **Admission control:** Rate limiters at the entry point to cap concurrent load during recovery

---

## Q18: A network partition isolates part of your distributed system. How do you handle split-brain risk?

- **Immediate response:**
  1. Identify which nodes are on which side of the partition
  2. Verify consensus systems (etcd, ZooKeeper) -- does the majority partition have quorum?
  3. Clients in the minority partition should fail-safe (reject writes, serve stale reads with warning)

- **Split-brain prevention:**
  1. **Quorum-based consensus:** Raft, Paxos require majority agreement for writes
  2. **Fencing tokens:** Every lock/lease includes a monotonically increasing token; downstream services reject stale tokens
  3. **STONITH (Shoot The Other Node In The Head):** In HA clusters, the surviving side forces the other side offline
  4. **Client-side awareness:** Clients use cluster endpoints (not single-node), enforce linearizable reads

- **After partition heals:**
  1. Compare data on both sides for conflicts
  2. Apply conflict resolution (last-writer-wins, merge, manual resolution)
  3. Post-mortem: why did the partition occur, and how can clients fail-safe automatically?

---

## Q19: How do you protect against silent data corruption in a storage system?

1. **End-to-end checksums:** Application computes checksums at write time; verifies at read time
   - Do not rely solely on filesystem or hardware checksums
2. **Filesystem choice:** ZFS and Btrfs provide built-in data checksumming; XFS/ext4 do not
3. **Regular scrubbing:** `zpool scrub` (ZFS) or `btrfs scrub` (Btrfs) on a schedule
4. **ECC memory:** Detect and correct single-bit memory errors that would corrupt data in transit
   - Monitor with `edac-util -s` and `mcelog`
5. **RAID scrubbing:** `echo check > /sys/block/md0/md/sync_action` to verify parity consistency
6. **Application-level audits:** Periodic comparison of stored data against source-of-truth checksums
7. **Keep filesystems below 90% utilization:** Some kernel bugs only manifest under space pressure

---

## Q20: Describe how DNS failures can cascade into application outages and how to make DNS resilient.

- **Cascade path:**
  1. DNS server becomes unreachable or slow
  2. Applications making DNS lookups block on resolution (30-second default timeout)
  3. Thread pools exhaust as threads wait for DNS
  4. Application stops serving requests even though the application itself is healthy
  5. Health checks fail (they also need DNS), load balancer marks instances unhealthy
  6. Auto-scaler replaces instances; new instances also cannot resolve DNS -- cascade amplifies

- **Resilience strategies:**
  1. **Local caching resolver:** Run `systemd-resolved` or `dnsmasq` locally to cache resolutions
  2. **Short, respectful TTLs:** 30-60 seconds for critical failover paths
  3. **Application-level DNS caching:** JVM: set `networkaddress.cache.ttl=30`; disable nscd or match its TTL to DNS TTL
  4. **DNS health monitoring:** Alert when any host's DNS resolution fails or exceeds 100ms
  5. **Reduce DNS dependency:** Use IP-based service discovery (Consul, Kubernetes service) for inter-service traffic
  6. **Fail-open DNS:** If DNS is unavailable, use last-known-good resolution from local cache
