# Cheatsheet 09: Security (SELinux, PAM, Hardening)

> Quick reference for senior SRE/Cloud Engineer interviews and production work.
> Full notes: [Security](../09-security/security.md)

---

## SELinux Commands

```bash
getenforce                             # Show mode: Enforcing/Permissive/Disabled
setenforce 1                           # Set enforcing (runtime only)
sestatus                               # Full status (mode, policy, MLS)

# Contexts
ls -Z /path                            # File contexts
ps -eZ | grep service                  # Process contexts
id -Z                                  # Current user context

# Fix file contexts
restorecon -Rv /path                   # Restore default from policy
semanage fcontext -a -t httpd_sys_content_t "/srv/web(/.*)?"  # Add persistent rule
restorecon -Rv /srv/web                # Apply persistent rule

# Port labeling
semanage port -l | grep http           # List port labels
semanage port -a -t http_port_t -p tcp 8443  # Label custom port

# Booleans
getsebool -a | grep httpd              # List booleans
setsebool -P httpd_can_network_connect on  # Set persistently

# Troubleshooting
ausearch -m avc -ts recent             # Recent AVC denials
audit2why < /var/log/audit/audit.log   # Explain denials
sealert -a /var/log/audit/audit.log    # Human-readable (setroubleshoot)
audit2allow -a -M mypolicy            # Generate policy module (LAST RESORT)
semodule -i mypolicy.pp               # Install module

# Per-domain permissive (instead of setenforce 0)
semanage permissive -a httpd_t         # Only httpd runs permissive
semanage permissive -d httpd_t         # Restore enforcing for httpd
```

## PAM Configuration

```bash
# Key files
/etc/pam.d/sshd                        # SSH authentication
/etc/pam.d/sudo                        # sudo authentication
/etc/pam.d/system-auth                 # RHEL shared stack
/etc/pam.d/common-auth                 # Debian shared stack
/etc/security/limits.conf              # Resource limits (pam_limits)
/etc/security/pwquality.conf           # Password policy (pam_pwquality)
/etc/security/access.conf              # Access control (pam_access)

# Control flags
# required    - must pass, continues stack on fail
# requisite   - must pass, aborts immediately on fail
# sufficient  - on success + no prior required fail = return success
# optional    - result only matters if sole module

# Account lockout (RHEL 8+)
faillock --user jdoe                   # Show failed attempts
faillock --user jdoe --reset           # Reset counter

# Test PAM without actual login
pamtester sshd username authenticate
```

## File Permissions and ACLs

```bash
# Permissions
chmod 750 /opt/app/bin                 # rwxr-x---
chmod u+s /usr/local/bin/cmd           # Set SUID
chmod g+s /shared/dir                  # Set SGID (new files inherit group)
chmod +t /tmp                          # Sticky bit

# Ownership
chown user:group /path -R              # Recursive
chown --reference=ref_file target      # Copy ownership

# POSIX ACLs
setfacl -m u:deployer:rx /var/www      # Named user ACL
setfacl -m g:ops:rwx /opt/configs      # Named group ACL
setfacl -d -m g:devs:rw /opt/app      # Default ACL (inheritance)
setfacl -b /path                       # Remove all ACLs
getfacl /path                          # View ACLs

# Find dangerous permissions
find / -perm -4000 -type f 2>/dev/null # SUID binaries
find / -perm -2000 -type f 2>/dev/null # SGID binaries
find / -xdev -type f -perm -0002       # World-writable files
```

## Linux Capabilities

```bash
# File capabilities (replace SUID)
setcap 'cap_net_bind_service=+ep' /usr/bin/node   # Bind port <1024
getcap /usr/bin/node                               # Verify
setcap -r /usr/bin/node                            # Remove
getcap -r / 2>/dev/null                            # Find all files with caps

# Process capabilities
getpcaps <pid>                         # Show process capabilities
grep Cap /proc/<pid>/status            # Raw bitmask
capsh --decode=<hex>                   # Decode bitmask

# Critical capabilities
# CAP_SYS_ADMIN   = "the new root" (mount, swapon, namespace config)
# CAP_NET_ADMIN   = network config (routes, firewall, interfaces)
# CAP_NET_BIND_SERVICE = bind ports < 1024
# CAP_DAC_OVERRIDE = bypass file permission checks
# CAP_SETUID       = change UID arbitrarily
# CAP_SYS_PTRACE   = trace/inject into any process
```

## SSH Hardening

```bash
# Key generation
ssh-keygen -t ed25519 -C "user@host"           # Preferred
ssh-keygen -t rsa -b 4096 -C "user@host"       # Legacy compat

# Key deployment
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@host

# Critical sshd_config directives
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
PubkeyAcceptedKeyTypes ssh-ed25519,rsa-sha2-512,rsa-sha2-256
MaxAuthTries 3
AllowGroups sre-team
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowTCPForwarding no
LoginGraceTime 30
MaxStartups 10:30:60
LogLevel VERBOSE

# Validate and reload
sshd -t                                # Syntax check
systemctl reload sshd                  # Reload (keeps existing connections)
```

## Firewall (iptables / nftables)

```bash
# iptables
iptables -L -n -v --line-numbers       # List rules
iptables -A INPUT -p tcp --dport 22 -s 10.0.0.0/8 -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -P INPUT DROP                 # Default deny
iptables-save > /etc/iptables.rules    # Persist

# nftables (modern replacement)
nft list ruleset                       # Show all
nft add table inet filter
nft add chain inet filter input '{ type filter hook input priority 0; policy drop; }'
nft add rule inet filter input tcp dport 22 ip saddr 10.0.0.0/8 accept
nft add rule inet filter input ct state established,related accept
```

## Audit Framework

```bash
# Status
auditctl -s                            # Audit status
auditctl -l                            # Active rules

# Common rules
auditctl -w /etc/shadow -p wa -k shadow_changes       # File watch
auditctl -w /etc/sudoers.d/ -p wa -k sudoers          # Directory watch
auditctl -a always,exit -F arch=b64 -S execve -k cmds # Track all commands
auditctl -a always,exit -F arch=b64 -S setuid -k priv_esc  # Privilege esc

# Search and report
ausearch -k shadow_changes -ts today -i               # By key, human-readable
ausearch -m USER_LOGIN -ts today -i                    # Login events
ausearch --uid 0 -ts today -i                          # All root activity
ausearch -m avc -ts recent                             # SELinux denials
aureport --auth                                        # Auth summary
aureport --anomaly                                     # Anomalies
aureport -x --summary                                  # Executable summary

# Immutable rules (add as LAST rule)
# -e 2                                # Cannot modify rules until reboot
```

## Kernel Security Parameters (sysctl)

```bash
kernel.randomize_va_space = 2          # Full ASLR
fs.suid_dumpable = 0                   # No SUID core dumps
net.ipv4.tcp_syncookies = 1            # SYN flood protection
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.ip_forward = 0               # Disable unless router
kernel.unprivileged_bpf_disabled = 1   # Restrict BPF
kernel.dmesg_restrict = 1             # Restrict dmesg
kernel.kptr_restrict = 2              # Hide kernel symbols
```

## CIS Hardening Quick Checks

```bash
# Filesystem mount options
mount | grep /tmp                      # Should have nosuid,noexec,nodev
mount | grep /dev/shm                  # Should have nosuid,noexec,nodev

# Disabled protocols
lsmod | grep -E "cramfs|freevxfs|hfs|squashfs|udf"  # Should be empty

# Password policy
grep -E "minlen|dcredit|ucredit|ocredit|lcredit" /etc/security/pwquality.conf
grep PASS_MAX_DAYS /etc/login.defs     # Should be <= 365
grep PASS_MIN_DAYS /etc/login.defs     # Should be >= 1

# SSH compliance
sshd -T | grep -i "permitrootlogin"   # Should be "no"
sshd -T | grep -i "passwordauth"      # Should be "no"

# Audit compliance
auditctl -s | grep enabled            # Should be 2 (immutable)
systemctl is-active auditd             # Should be "active"
```

## Incident Response Quick Commands

```bash
# Who is on this system right now
w                                      # Active sessions
last -20                               # Recent logins
lastb -20                              # Failed logins

# What is running
ps auxf                                # Full process tree
ss -tanp                               # Network connections
lsof -i -n -P                         # Open network files

# Check for unauthorized changes
rpm -Va 2>/dev/null                    # RHEL: verify all packages
debsums -c 2>/dev/null                 # Debian: check changed files
find / -perm -4000 -newer /etc/passwd -type f  # Recent SUID changes
find /tmp /var/tmp -type f -executable # Executables in temp dirs

# Check for persistence
crontab -l -u root                     # Root cron jobs
ls /etc/cron.d/                        # System cron jobs
systemctl list-unit-files --state=enabled  # Enabled services
cat /root/.ssh/authorized_keys         # Root SSH keys
```
