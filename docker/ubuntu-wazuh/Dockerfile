FROM ubuntu:22.04

LABEL maintainer="cyberlab"
LABEL description="Ubuntu 22.04 base with wazuh tools and ttyd"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install base packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    sudo \
    python3 \
    python3-pip \
    vim \
    tmux \
    jq \
    tree \
    net-tools \
    iputils-ping \
    traceroute \
    man-db \
    bash-completion \
    ripgrep \
    fd-find \
    bat \
    && (apt-get install -y eza || apt-get install -y exa || true) \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Download and install ttyd binary from GitHub releases
RUN wget -q https://github.com/tsl0922/ttyd/releases/download/1.7.4/ttyd.x86_64 -O /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

# Shared shell QoL template
COPY common/cyberlab-qol.sh /etc/cyberlab-qol.sh
RUN chmod 0644 /etc/cyberlab-qol.sh \
    && echo '[ -f /etc/cyberlab-qol.sh ] && source /etc/cyberlab-qol.sh' >> /etc/bash.bashrc

# Expose ttyd port
EXPOSE 7681

# Default command: run ttyd with bash
CMD ["/usr/local/bin/ttyd", "--writable", "-p", "7681", "bash"]
