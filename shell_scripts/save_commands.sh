
# =============================================
# Daily Command Logger Script
#
# This shell script automates the process of logging your daily terminal commands and pushing them to a GitHub repository.
#
# Summary:
# 1. Adds your SSH key for GitHub access.
# 2. Sets up directories for storing daily command logs.
# 3. Extracts today’s commands from your Zsh history, ignoring trivial commands listed in an external ignore_commands file.
# 4. Groups the commands into categories: Git, Terraform, Kubernetes, Cloud CLI (AWS, Azure, GCloud), and Other.
# 5. Writes the grouped commands into a Markdown file for the current day.
# 6. Commits and pushes the Markdown log file to a specified GitHub repository.
# 7. Cleans up any temporary files created during the process.
#
# This helps you keep a daily, categorized record of your meaningful terminal activity, versioned in a GitHub repo.
# =============================================
#!/bin/zsh

# === Settings ===
ssh-add "$HOME/Workspace/github/ssh-keys/git_login" || {
  echo "Failed to add SSH key. Please check your SSH configuration."
  exit 1
}
REPO_DIR="$HOME/Workspace/github/repos/command_logs"
OUTPUT_DIR="$REPO_DIR/daily_logs"
mkdir -p "$OUTPUT_DIR"

TODAY=$(date '+%Y-%m-%d')
START_OF_DAY=$(date -j -f "%Y-%m-%d %H:%M:%S" "$TODAY 00:00:00" "+%s")  # macOS format
# On Linux, use: START_OF_DAY=$(date -d "$TODAY 00:00:00" "+%s")

ZSH_HIST_FILE="$HOME/.zsh_history"
TMP_FILE=$(mktemp)
OUTPUT_FILE="$OUTPUT_DIR/commands-$TODAY.md"

# === Step 1: Filter only today's commands ===
# === Step 1: Extract today's commands and exclude trivial ones ===
awk -v start="$START_OF_DAY" '
  BEGIN { cmd = "" }
  /^: [0-9]+:[0-9]+;/ {
    split($0, parts, ";")
    timestamp = substr(parts[1], 3)
    if (timestamp >= start) {
      cmd = parts[2]
      if (cmd != "") print cmd
    }
  }
' "$ZSH_HIST_FILE" | 
  grep -vF -f "$HOME/Workspace/github/repos/le-linux/shell_scripts/ignore_commands" | 
  sort | uniq > "$TMP_FILE"

# === Step 2: Group Commands ===
GIT_CMDS=$(grep -E '^git ' "$TMP_FILE" | sort | uniq)
TF_CMDS=$(grep -E '^terraform ' "$TMP_FILE" | sort | uniq)
K8S_CMDS=$(grep -E '^kubectl ' "$TMP_FILE" | sort | uniq)
CLOUD_CMDS=$(grep -E '^(aws|az|gcloud) ' "$TMP_FILE" | sort | uniq)
OTHER_CMDS=$(grep -vE '^(git|terraform|kubectl|aws|az|gcloud) ' "$TMP_FILE" | sort | uniq)

# === Step 3: Write Markdown ===
{
  echo "# 🧾 Daily Command Log - $TODAY"
  echo
  echo "## 🔧 Git Commands"
  echo '```bash'
  echo "$GIT_CMDS"
  echo '```'
  echo
  echo "## 🛠 Terraform Commands"
  echo '```bash'
  echo "$TF_CMDS"
  echo '```'
  echo
  echo "## ☸️ Kubernetes Commands"
  echo '```bash'
  echo "$K8S_CMDS"
  echo '```'
  echo
  echo "## ☁️ Cloud CLI Commands (AWS, Azure, GCloud)"
  echo '```bash'
  echo "$CLOUD_CMDS"
  echo '```'
  echo
  echo "## 🧮 Other Commands"
  echo '```bash'
  echo "$OTHER_CMDS"
  echo '```'
} > "$OUTPUT_FILE"

# === Step 4: Push to GitHub Repo ===
cd "$REPO_DIR"
git add "$OUTPUT_FILE"
git commit -m "Add command log for $TODAY"
git push origin main

# Cleanup
rm "$TMP_FILE"


