# CyberLab sandbox shell quality-of-life defaults
# Sourced from system bashrc files in each sandbox image.

# Only apply for interactive bash shells
[[ $- != *i* ]] && return

# Prompt tuning (bash only)
if [[ -n "${BASH_VERSION:-}" ]]; then
  export PS1='\[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]\$ '
fi

# Enable bash completion when available
if [[ -f /usr/share/bash-completion/bash_completion ]]; then
  # shellcheck source=/usr/share/bash-completion/bash_completion
  source /usr/share/bash-completion/bash_completion
elif [[ -f /etc/bash_completion ]]; then
  # shellcheck source=/etc/bash_completion
  source /etc/bash_completion
fi

# Better ls
if command -v eza >/dev/null 2>&1; then
  alias ls='eza'
  alias ll='eza -la'
  alias lt='eza --tree --icons=auto'
elif command -v exa >/dev/null 2>&1; then
  alias ls='exa'
  alias ll='exa -la'
  alias lt='exa --tree'
fi

# Better cat
if command -v bat >/dev/null 2>&1; then
  alias cat='bat --paging=never --style=plain'
elif command -v batcat >/dev/null 2>&1; then
  alias cat='batcat --paging=never --style=plain'
fi

# Better grep
if command -v rg >/dev/null 2>&1; then
  alias grep='rg'
fi

# Better find
if command -v fd >/dev/null 2>&1; then
  alias find='fd'
elif command -v fdfind >/dev/null 2>&1; then
  alias find='fdfind'
fi
