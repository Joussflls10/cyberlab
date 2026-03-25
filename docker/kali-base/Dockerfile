FROM kalilinux/kali-rolling

LABEL maintainer="cyberlab"
LABEL description="Kali Linux base with offensive security tools and ttyd"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Update and install common offensive security tools
RUN apt-get update && apt-get install -y \
    nmap \
    wireshark \
    sqlmap \
    nikto \
    hydra \
    john \
    aircrack-ng \
    burpsuite \
    metasploit-framework \
    curl \
    wget \
    python3 \
    python3-pip \
    vim \
    net-tools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Download and install ttyd binary from GitHub releases
RUN wget -q https://github.com/tsl0922/ttyd/releases/download/1.7.4/ttyd.x86_64 -O /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

# Expose ttyd port
EXPOSE 7681

# Default command: run ttyd with bash
CMD ["/usr/local/bin/ttyd", "-p", "7681", "bash"]
