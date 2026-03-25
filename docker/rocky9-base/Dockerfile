FROM rockylinux:9

LABEL maintainer="cyberlab"
LABEL description="Rocky Linux 9 base with ansible and ttyd"

# Install base packages
RUN dnf install -y --allowerasing \
    python3 \
    python3-pip \
    git \
    curl \
    wget \
    vim \
    net-tools \
    && dnf clean all

# Install ansible via pip
RUN pip3 install --no-cache-dir ansible ansible-lint

# Download and install ttyd binary from GitHub releases
RUN wget -q https://github.com/tsl0922/ttyd/releases/download/1.7.4/ttyd.x86_64 -O /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

# Expose ttyd port
EXPOSE 7681

# Default command: run ttyd with bash
CMD ["/usr/local/bin/ttyd", "-p", "7681", "bash"]
