# Interview Questions 09: Security (SELinux, PAM, Hardening)

> FAANG / Staff+ SRE interview preparation. All answers structured with bullets/numbered lists.
> Full notes: [Security](../09-security/security.md)

---

<!-- toc -->
## Table of Contents

- [Q1: Explain DAC vs. MAC in Linux. When would you choose to deploy SELinux over standard permissions?](#q1-explain-dac-vs-mac-in-linux-when-would-you-choose-to-deploy-selinux-over-standard-permissions)
- [Q2: Walk through the SELinux troubleshooting process when a service is denied access.](#q2-walk-through-the-selinux-troubleshooting-process-when-a-service-is-denied-access)
- [Q3: Describe the PAM architecture. How would you implement MFA for SSH without breaking console access?](#q3-describe-the-pam-architecture-how-would-you-implement-mfa-for-ssh-without-breaking-console-access)
- [Q4: What are Linux capabilities? Why is CAP_SYS_ADMIN called "the new root"?](#q4-what-are-linux-capabilities-why-is-cap_sys_admin-called-the-new-root)
- [Q5: How does seccomp-bpf work? How do container runtimes use it?](#q5-how-does-seccomp-bpf-work-how-do-container-runtimes-use-it)
- [Q6: Explain the Linux audit framework. How would you configure it for SOC2/PCI compliance?](#q6-explain-the-linux-audit-framework-how-would-you-configure-it-for-soc2pci-compliance)
- [Q7: How would you harden an SSH server for a production bastion host?](#q7-how-would-you-harden-an-ssh-server-for-a-production-bastion-host)
- [Q8: What is the difference between iptables and nftables? Why is the industry moving to nftables?](#q8-what-is-the-difference-between-iptables-and-nftables-why-is-the-industry-moving-to-nftables)
- [Q9: How do user namespaces interact with Linux capabilities and security?](#q9-how-do-user-namespaces-interact-with-linux-capabilities-and-security)
- [Q10: Describe SUID/SGID security implications and how capabilities replace them.](#q10-describe-suidsgid-security-implications-and-how-capabilities-replace-them)
- [Q11: How does Fail2Ban work? What are its limitations at scale?](#q11-how-does-fail2ban-work-what-are-its-limitations-at-scale)
- [Q12: Explain CIS Benchmarks for Linux. How would you automate compliance?](#q12-explain-cis-benchmarks-for-linux-how-would-you-automate-compliance)
- [Q13: How would you investigate a suspected privilege escalation?](#q13-how-would-you-investigate-a-suspected-privilege-escalation)
- [Q14: What is the relationship between namespaces, cgroups, capabilities, and seccomp in container security?](#q14-what-is-the-relationship-between-namespaces-cgroups-capabilities-and-seccomp-in-container-security)
- [Q15: How would you design zero-trust SSH access for a large fleet?](#q15-how-would-you-design-zero-trust-ssh-access-for-a-large-fleet)
- [Q16: Explain immutable audit rules and why they matter for security.](#q16-explain-immutable-audit-rules-and-why-they-matter-for-security)
- [Q17: A container needs to run a process that binds to port 443. How do you do this securely?](#q17-a-container-needs-to-run-a-process-that-binds-to-port-443-how-do-you-do-this-securely)
- [Q18: How do SELinux booleans work? Give examples of commonly used booleans.](#q18-how-do-selinux-booleans-work-give-examples-of-commonly-used-booleans)

<!-- toc stop -->

## Q1: Explain DAC vs. MAC in Linux. When would you choose to deploy SELinux over standard permissions?

- **DAC (Discretionary Access Control):**
  - Resource owner sets permissions (chmod, chown, POSIX ACLs)
  - Kernel checks UID/GID of calling process against file mode bits
  - Root (UID 0) bypasses all DAC checks
  - Failure mode: user error leads to exposure (world-readable secrets, 777 directories)

- **MAC (Mandatory Access Control):**
  - System administrator defines security policies enforced by kernel
  - Even root is confined within the policy scope
  - Implemented via Linux Security Modules (LSM) framework
  - Deny-by-default: access only permitted if an explicit rule exists

- **Deploy SELinux when:**
  1. Running internet-facing services (httpd, named, nginx) that are frequent exploit targets
  2. Compliance mandates it (PCI-DSS, HIPAA, FedRAMP, SOC2)
  3. Operating multi-tenant systems where tenant isolation is critical
  4. Running containers -- SELinux provides per-container confinement independent of user namespaces

- **Practical approach:** Use RHEL's `targeted` policy -- ~150 daemons confined, user processes unconfined. 90% security benefit with 10% administration overhead.

---

## Q2: Walk through the SELinux troubleshooting process when a service is denied access.

1. **Confirm SELinux involvement:** `getenforce` shows Enforcing; `ausearch -m avc -ts recent` reveals AVC denials for the service
2. **Parse the AVC message:** Identify `scontext` (process domain), `tcontext` (target label), `tclass` (file, port, socket), denied permissions (read, write, open, connect)
3. **Check file context first:** `ls -Z <target>` -- if type is wrong (e.g., `default_t` instead of `httpd_sys_content_t`):
   - Fix: `restorecon -Rv <path>` or `semanage fcontext -a -t correct_type "/path(/.*)?"` then `restorecon`
4. **Check booleans:** `getsebool -a | grep <service>` -- many common access patterns are boolean-gated:
   - Example: `setsebool -P httpd_can_network_connect on`
5. **Check port labels:** `semanage port -l | grep <port>` -- custom ports need explicit labeling:
   - Fix: `semanage port -a -t http_port_t -p tcp 8443`
6. **Use audit2why:** Pipe AVC to `audit2why` for human-readable explanation and suggested fix
7. **Last resort -- audit2allow:** Generate custom policy module; always review `.te` file before loading
8. **Never acceptable:** `setenforce 0` in production; unreviewed `audit2allow` output

---

## Q3: Describe the PAM architecture. How would you implement MFA for SSH without breaking console access?

- **Architecture:**
  - PAM is a shared library (`libpam`) that applications link against
  - Configuration in `/etc/pam.d/<service>` (one file per service)
  - Four module types: `auth` (identity verification), `account` (account validity), `password` (credential changes), `session` (setup/teardown)
  - Control flags govern pass/fail logic:
    - `required`: must succeed, stack continues on fail
    - `requisite`: must succeed, aborts on fail
    - `sufficient`: success + no prior required fail = immediate success
    - `optional`: result only matters if sole module for type
  - Applications call `pam_authenticate()`, `pam_acct_mgmt()`, etc.

- **Implementing MFA for SSH only:**
  1. Edit `/etc/pam.d/sshd` (NOT `system-auth`) -- add `auth required pam_google_authenticator.so` after `pam_unix.so`
  2. Set `ChallengeResponseAuthentication yes` and `AuthenticationMethods publickey,keyboard-interactive` in `sshd_config`
  3. Each user runs `google-authenticator` to create TOTP secret before enforcement
  4. Leave `/etc/pam.d/login` (console) unchanged -- console uses password only
  5. Test from a second SSH session before closing the current one

- **Critical safeguards:**
  - Keep a rescue shell open during PAM changes
  - Use `nullok` option initially (allows login if user has not enrolled MFA)
  - Maintain out-of-band access (BMC/IPMI/serial console) independent of PAM
  - Version control `/etc/pam.d/`; deploy via configuration management

---

## Q4: What are Linux capabilities? Why is CAP_SYS_ADMIN called "the new root"?

- **Capabilities decompose root privilege into ~41 distinct capabilities:**
  - Instead of checking `uid == 0`, kernel checks for the specific capability needed
  - Allows running processes with only the privileges they require

- **Five capability sets per process:**
  1. **Permitted** -- upper bound of capabilities the process can activate
  2. **Effective** -- currently active, checked by kernel on every privileged operation
  3. **Inheritable** -- preservable across `execve()`
  4. **Bounding** -- hard limit, once dropped cannot be re-added
  5. **Ambient** -- preserved across `execve()` for non-SUID binaries

- **CAP_SYS_ADMIN is "the new root" because:**
  1. Encompasses ~30% of all capability-guarded operations
  2. Grants: mount/umount, swapon, sethostname, ioctl on devices, BPF operations, namespace configuration, keyring management
  3. In containers: enables mounting host procfs, accessing PID 1's root filesystem -- trivial container escape
  4. Per LWN.net analysis: granting CAP_SYS_ADMIN effectively negates the entire capability model

- **Best practices:**
  - Never grant CAP_SYS_ADMIN to containers
  - Use specific capabilities: `CAP_NET_BIND_SERVICE` for port 80, `CAP_DAC_READ_SEARCH` for log readers
  - Drop all capabilities, add back only what is needed (`--cap-drop=ALL --cap-add=NET_BIND_SERVICE`)
  - Use file capabilities (`setcap`) instead of SUID bits

---

## Q5: How does seccomp-bpf work? How do container runtimes use it?

- **Mechanism:**
  1. Process calls `seccomp(SECCOMP_SET_MODE_FILTER, flags, &bpf_prog)` to install a BPF filter
  2. BPF program inspects syscall number and arguments on every syscall entry
  3. Filter returns an action: `ALLOW`, `KILL_PROCESS`, `ERRNO(n)`, `TRACE`, `LOG`
  4. Filters are inherited by child processes across `fork()` and `execve()`
  5. Filters can only be tightened, never loosened (no privilege escalation via filter removal)

- **Container runtime integration:**
  - Docker/containerd apply a default profile blocking ~44 dangerous syscalls
  - Blocked syscalls include: `mount`, `umount2`, `ptrace`, `kexec_load`, `reboot`, `init_module`, `delete_module`, `unshare` (with CLONE_NEWUSER)
  - Profile format: JSON mapping syscall names to actions
  - Kubernetes: `securityContext.seccompProfile.type: RuntimeDefault` applies runtime default
  - Custom profiles placed at `/var/lib/kubelet/seccomp/` and referenced by `localhostProfile`

- **Why it matters:** Even if an attacker gains code execution inside a container with all capabilities dropped, seccomp prevents invoking dangerous syscalls. It is the final enforcement layer before the kernel.

---

## Q6: Explain the Linux audit framework. How would you configure it for SOC2/PCI compliance?

- **Components:**
  - `kauditd` (kernel thread) -- generates events from kernel hooks, sends to userspace via netlink
  - `auditd` (daemon) -- receives events, writes to `/var/log/audit/audit.log`
  - `auditctl` -- manage rules at runtime
  - `ausearch` -- search/filter logs by criteria (user, syscall, time, key)
  - `aureport` -- generate summary reports (auth, anomalies, executables)

- **Rule types:**
  - File watches: `-w /etc/shadow -p wa -k shadow_changes`
  - Syscall rules: `-a always,exit -F arch=b64 -S execve -k exec_log`
  - Task rules: applied at process creation time

- **SOC2/PCI compliance configuration:**
  1. Authentication events: enabled by default (USER_LOGIN, USER_AUTH messages)
  2. Privileged commands: `-a always,exit -F arch=b64 -S execve -F euid=0 -k root_commands`
  3. Sensitive file monitoring: `-w /etc/shadow -p wa -k identity`, `-w /etc/sudoers -p wa -k sudoers`
  4. Network changes: `-a always,exit -F arch=b64 -S sethostname -S setdomainname -k system_id`
  5. Immutable rules: `-e 2` (cannot modify until reboot)
  6. Disk full behavior: `disk_full_action = HALT` to prevent logging gaps
  7. Remote forwarding: `audisp-remote` plugin ships events to SIEM in real-time
  8. Log retention: PCI requires 1 year minimum; SOC2 varies by control

---

## Q7: How would you harden an SSH server for a production bastion host?

1. **Authentication:**
   - `PasswordAuthentication no` (key-based only)
   - `PubkeyAcceptedKeyTypes ssh-ed25519,rsa-sha2-512,rsa-sha2-256`
   - `PermitRootLogin no`
   - `MaxAuthTries 3`
   - Certificate-based auth with short-lived certs (HashiCorp Vault SSH CA)

2. **Access control:**
   - `AllowGroups bastion-users` (whitelist approach)
   - `AllowTCPForwarding no` (prevent unauthorized tunneling)
   - `X11Forwarding no`
   - `PermitTunnel no`

3. **Session management:**
   - `ClientAliveInterval 300` + `ClientAliveCountMax 2` (terminate idle sessions)
   - `LoginGraceTime 30` (30s to authenticate)
   - `MaxStartups 10:30:60` (rate limit connections)

4. **Cryptography:**
   - Explicit `Ciphers` and `KexAlgorithms` lists (Mozilla Modern guidelines)
   - Regenerate host keys with Ed25519 and RSA-4096
   - Remove DSA and small ECDSA keys

5. **Logging and monitoring:**
   - `LogLevel VERBOSE` for detailed auth logging
   - Fail2Ban or `pam_faillock` for brute force protection
   - Forward auth logs to SIEM

---

## Q8: What is the difference between iptables and nftables? Why is the industry moving to nftables?

- **iptables (legacy):**
  - Separate binaries for IPv4 (`iptables`), IPv6 (`ip6tables`), ARP (`arptables`), bridging (`ebtables`)
  - Linear rule evaluation: O(n) per packet in each chain
  - Atomic replacement requires saving/restoring entire ruleset
  - Rules are plain text with complex flag syntax

- **nftables (modern replacement):**
  - Single unified framework and binary (`nft`) for all protocols
  - Rules compile to bytecode executed by a kernel virtual machine (nf_tables)
  - Supports sets, maps, and concatenated matches for O(1) lookups
  - Atomic rule updates by default (transaction semantics)
  - Native multi-action rules (verdict maps)
  - Better API for programmatic management (libnftables, JSON)

- **Migration:**
  - RHEL 8+, Debian 10+ default to nftables backend
  - `iptables-nft` provides backward-compatible syntax on nftables kernel backend
  - CIS benchmarks list nftables as recommended firewall option

---

## Q9: How do user namespaces interact with Linux capabilities and security?

- **User namespaces** map UIDs inside/outside the namespace:
  - A process can be UID 0 inside (gaining capabilities within namespace) while unprivileged outside
- **Capabilities are namespace-scoped:**
  - `CAP_NET_ADMIN` inside a user namespace affects only the associated network namespace
  - Does not grant host-level network configuration
- **Security implications:**
  1. Rootless containers use user namespaces to run as "root" inside without host root
  2. Bounding set prevents capabilities from leaking to the initial user namespace
  3. Kernel checks the initial user namespace for dangerous operations
  4. User namespaces expand attack surface by allowing unprivileged users to reach kernel code paths previously only reachable by root
  5. Some distros disable unprivileged user namespaces: `kernel.unprivileged_userns_clone = 0`
- **Container security design:** user namespaces provide the UID mapping, but capabilities, seccomp, and SELinux provide the actual access control enforcement within the namespace

---

## Q10: Describe SUID/SGID security implications and how capabilities replace them.

- **SUID (Set User ID):**
  - When executed, process runs with file owner's UID (usually root)
  - Example: `/usr/bin/passwd` is SUID root to write to `/etc/shadow`
  - Any vulnerability in a SUID-root binary gives attacker full root access

- **SGID (Set Group ID):**
  - Process inherits file's group GID
  - On directories: new files inherit directory group (useful for shared folders)

- **Security risks of SUID:**
  1. Buffer overflows, race conditions, path injection in SUID binaries are common exploit vectors
  2. SUID binaries expand the root attack surface
  3. All-or-nothing: SUID grants full owner privileges, not just what the program needs

- **Capabilities as replacement:**
  - `setcap 'cap_net_bind_service=+ep' /usr/bin/node` -- bind port 80 without SUID
  - `setcap 'cap_dac_read_search=+ep' /usr/bin/logread` -- read all files without root
  - Grants only the specific privilege needed, not full root
  - `find / -perm -4000 -type f` -- audit SUID inventory; convert to capabilities where possible
  - Mount `/tmp`, `/home`, NFS shares with `nosuid` to prevent SUID exploitation

---

## Q11: How does Fail2Ban work? What are its limitations at scale?

- **Mechanism:**
  - Python daemon monitoring log files (auth.log, sshd, nginx) via regex patterns
  - On repeated failures from an IP, executes ban action (iptables/nftables DROP rule)
  - Jails defined in `/etc/fail2ban/jail.local`: log path, filter regex, max retries, ban duration

- **Limitations at scale:**
  1. Regex-based log parsing is CPU-intensive with high log volume
  2. Each ban adds a firewall rule -- thousands create O(n) traversal overhead
  3. Distributed botnets rotate IPs faster than Fail2Ban can ban
  4. Ineffective against credential stuffing with unique IPs per attempt
  5. IPv6 support limited; banning /128s useless when attackers use /64 subnets

- **Alternatives at scale:**
  - CrowdSec (community-driven threat intel sharing)
  - Edge-level rate limiting (Cloudflare, AWS WAF)
  - SSHGuard (lower overhead, written in C)
  - eBPF/XDP programs for wire-speed packet dropping

---

## Q12: Explain CIS Benchmarks for Linux. How would you automate compliance?

- **CIS (Center for Internet Security) Benchmarks cover:**
  - Filesystem configuration (separate partitions, mount options)
  - User management (password policies, lockout, umask)
  - Network configuration (firewall, IP forwarding, ICMP)
  - Logging and auditing (rsyslog, auditd rules)
  - SSH hardening, kernel parameters (sysctl)

- **Two profile levels:**
  - Level 1: Practical hardening, minimal performance impact
  - Level 2: Defense-in-depth, may reduce functionality

- **Automation approaches:**
  1. **Ansible:** `ansible-lockdown/RHEL8-CIS` role for applying and remediating
  2. **OpenSCAP:** `oscap` tool with CIS content for scanning + remediation
  3. **Packer:** Bake hardened AMIs/images at build time
  4. **Ubuntu USG:** `sudo ua enable usg` for CIS Level 1/2 profiles
  5. **InSpec:** Compliance-as-code profiles for CI/CD pipelines
  6. **Puppet:** `cis_security_hardening` module for continuous enforcement

---

## Q13: How would you investigate a suspected privilege escalation?

1. **Capture volatile state immediately:**
   - `w` (active sessions), `last -20` (recent logins), `lastb -20` (failed logins)
   - `ps auxf` (full process tree), `ss -tanp` (network connections)
   - `cat /proc/*/cmdline` for running process arguments

2. **Examine audit logs:**
   - `ausearch --uid 0 -ts today -i` (all root activity)
   - `ausearch -m EXECVE -k exec_log -i` (all executed commands)
   - `ausearch -m USER_CMD -i` (sudo usage)

3. **Check persistence mechanisms:**
   - Cron: `/var/spool/cron/`, `/etc/cron.d/`, `/etc/crontab`
   - Systemd: `systemctl list-unit-files --state=enabled` (unknown units)
   - SSH: all `~/.ssh/authorized_keys` for unauthorized keys
   - SUID: `find / -perm -4000 -newer /etc/passwd -type f` (recently modified)

4. **File integrity:**
   - `rpm -Va` (RHEL) or `debsums -c` (Debian) -- verify packages
   - `aide --check` -- compare against baseline

5. **Timeline reconstruction:**
   - Correlate audit, auth, application, and network flow logs
   - `ausearch -ts <start> -te <end> -i` for precise time windows

6. **Containment:**
   - Isolate from network (keep running for forensics)
   - Preserve memory dump and disk image before remediation

---

## Q14: What is the relationship between namespaces, cgroups, capabilities, and seccomp in container security?

- **Namespaces** = **isolation** (pid, net, mnt, uts, ipc, user, cgroup):
  - Container cannot see or interact with host resources
- **Cgroups** = **resource control** (CPU, memory, I/O, PIDs):
  - Prevent resource exhaustion and noisy-neighbor effects
- **Capabilities** = **privilege control**:
  - Restricted set of Linux capabilities (Docker drops ~14 by default)
  - No mounting, no module loading, no raw network access
- **Seccomp-bpf** = **syscall control**:
  - Only whitelisted system calls can be invoked
  - ~44 dangerous syscalls blocked by default

- **Together they form defense in depth:**
  1. Namespaces isolate the view (PID 1 in container is not PID 1 on host)
  2. Cgroups prevent resource abuse (OOM targets container, not host)
  3. Capabilities prevent privileged operations
  4. Seccomp prevents dangerous syscalls even if capabilities are acquired
  5. SELinux/AppArmor adds MAC layer on top

- **Container escape requires defeating ALL layers simultaneously**

---

## Q15: How would you design zero-trust SSH access for a large fleet?

1. **Certificate-based authentication (not static keys):**
   - Deploy CA using HashiCorp Vault SSH secrets engine or `step-ca`
   - Issue short-lived certificates (1-8 hours) tied to IdP identity (Okta, Google Workspace)
   - `sshd` trusts CA (`TrustedUserCAKeys`), not individual keys
   - No `authorized_keys` management; certs contain principals and expiry

2. **Identity-aware proxy layer:**
   - Deploy Teleport, Boundary (HashiCorp), or AWS SSM Session Manager
   - Users authenticate via SSO + MFA; proxy issues ephemeral credentials
   - All sessions recorded and auditable

3. **Network segmentation:**
   - No direct SSH from internet to production
   - SSH only from proxy on dedicated management VLAN
   - Security groups restrict port 22 to proxy IPs only

4. **Least privilege:**
   - Certificates encode allowed principals (roles, not usernames)
   - `AuthorizedPrincipalsFile` maps cert principals to OS users
   - Time-bound sudo via just-in-time privilege escalation

5. **Logging and detection:**
   - All sessions logged centrally with command audit
   - Alert on anomalous patterns (off-hours, unusual source, privilege escalation)

---

## Q16: Explain immutable audit rules and why they matter for security.

- **Activation:** Add `-e 2` as the last line in `/etc/audit/audit.rules`
- **Effect:** Once loaded, rules cannot be modified, deleted, or disabled until reboot
- **Why it matters:**
  1. Attacker with root cannot disable auditing to cover tracks
  2. Tamper-evident logging: any attempt to modify rules requires detectable reboot
  3. PCI-DSS 10.5.2 requires protecting audit trails from unauthorized modification
  4. Pairs with remote log forwarding -- even if host compromised, SIEM already has logs
- **Practical considerations:**
  - Rules must be thoroughly tested before enabling (mistakes require reboot to fix)
  - Combine with `disk_full_action = HALT` to prevent evasion via log overflow
  - Use `augenrules --check` to validate before loading
  - Test in non-production first; some monitoring agents modify audit rules

---

## Q17: A container needs to run a process that binds to port 443. How do you do this securely?

1. **Do NOT run the container as root or add `CAP_NET_BIND_SERVICE`** if alternatives exist:
   - Configure the container to listen on a high port (e.g., 8443) and map it via Kubernetes Service or Docker port mapping (`-p 443:8443`)
   - This is the preferred approach -- no capabilities needed

2. **If the process must bind to 443 inside the container:**
   - Add only `CAP_NET_BIND_SERVICE` to the container security context
   - Drop all other capabilities: `drop: ["ALL"]`, `add: ["NET_BIND_SERVICE"]`
   - Run as non-root user with this capability in the ambient set
   - Apply seccomp profile to restrict syscalls
   - Set `readOnlyRootFilesystem: true`

3. **On bare metal / VMs:**
   - Use file capabilities: `setcap 'cap_net_bind_service=+ep' /usr/bin/nginx`
   - Do not use SUID root
   - Do not run the service as root

---

## Q18: How do SELinux booleans work? Give examples of commonly used booleans.

- **Booleans** are on/off switches that modify SELinux policy behavior at runtime without writing custom policy modules
- Stored in the policy database; toggled with `setsebool` and queried with `getsebool`
- **`-P` flag makes changes persistent** across reboots (writes to policy store)
- Without `-P`, changes are runtime-only and lost on reboot

- **Commonly used booleans:**
  1. `httpd_can_network_connect` -- allow Apache/nginx to make outbound TCP connections (needed for reverse proxy)
  2. `httpd_can_network_connect_db` -- allow Apache to connect to database ports
  3. `httpd_use_nfs` -- allow Apache to serve content from NFS mounts
  4. `httpd_enable_homedirs` -- allow Apache to serve user home directories (`~user`)
  5. `ftpd_anon_write` -- allow anonymous FTP uploads
  6. `samba_enable_home_dirs` -- allow Samba to share user home directories
  7. `virt_use_nfs` -- allow libvirt VMs to use NFS storage
  8. `container_manage_cgroup` -- allow containers to manage cgroup hierarchy

- **Discovery workflow:**
  - `getsebool -a | grep <service>` to find relevant booleans
  - `semanage boolean -l | grep <boolean>` for description
  - `sesearch -b httpd_can_network_connect -A` to see what rules the boolean enables
