FROM rockylinux:9

LABEL maintainer="cyberlab"
LABEL description="Rocky Linux 9 base with ansible and ttyd"

# Install base packages
RUN set -eux; \
        dnf install -y --allowerasing epel-release; \
        dnf install -y --allowerasing \
            python3 \
            python3-pip \
            git \
            curl \
            wget \
            vim \
            tmux \
            jq \
            tree \
            net-tools \
            iputils \
            man-db \
            bash-completion \
            ripgrep; \
        (dnf install -y --allowerasing fd-find || dnf install -y --allowerasing fd || true); \
        (dnf install -y --allowerasing bat || true); \
        (dnf install -y --allowerasing eza || dnf install -y --allowerasing exa || true); \
        dnf clean all

# Install ansible via pip
RUN pip3 install --no-cache-dir ansible ansible-lint

# Download and install ttyd binary from GitHub releases
RUN wget -q https://github.com/tsl0922/ttyd/releases/download/1.7.4/ttyd.x86_64 -O /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

# Shared shell QoL template
COPY common/cyberlab-qol.sh /etc/cyberlab-qol.sh
RUN chmod 0644 /etc/cyberlab-qol.sh \
    && echo '[ -f /etc/cyberlab-qol.sh ] && source /etc/cyberlab-qol.sh' >> /etc/bashrc

# Expose ttyd port
EXPOSE 7681

# Default command: run ttyd with bash
CMD ["/usr/local/bin/ttyd", "--writable", "-p", "7681", "bash"]
