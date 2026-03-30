"""Sandbox service for CyberLab - manages Docker containers for challenges."""

import docker
from docker.types import ContainerSpec, Resources
from typing import Optional, Dict
from datetime import UTC, datetime, timedelta
import random
from pathlib import Path

from docker.errors import ImageNotFound, APIError, BuildError, DockerException

# Global network name for isolated sandboxes
SANDBOX_NETWORK = "cyberlab-sandbox"
DOCKER_CONTEXT_ROOT = Path(__file__).resolve().parents[2] / "docker"
DEFAULT_FALLBACK_IMAGE = "rocky9-base"


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def ensure_sandbox_network(client=None):
    """Ensure the isolated sandbox network exists."""
    if client is None:
        client = docker.from_env()
    try:
        client.networks.get(SANDBOX_NETWORK)
    except docker.errors.NotFound:
        client.networks.create(
            SANDBOX_NETWORK,
            driver="bridge",
        )
        print(f"[sandbox] Created isolated network: {SANDBOX_NETWORK}")


class SandboxService:
    """Service for managing sandboxed Docker containers for challenges."""

    def __init__(self):
        self.client = docker.from_env()
        self.label_key = "cyberlab"
        self.label_value = "true"

    def _image_exists(self, image_name: str) -> bool:
        try:
            self.client.images.get(image_name)
            return True
        except ImageNotFound:
            return False

    def _resolve_or_build_image(self, image: str) -> str:
        """Resolve image name locally or build it from local docker context if missing."""
        short_name = image.replace("cyberlab-", "", 1) if image.startswith("cyberlab-") else image
        canonical_name = image if image.startswith("cyberlab-") else f"cyberlab-{image}"

        candidates = [canonical_name, short_name]
        for candidate in candidates:
            if self._image_exists(candidate):
                return candidate

        context_dir = DOCKER_CONTEXT_ROOT / short_name
        dockerfile = context_dir / "Dockerfile"
        if context_dir.exists() and dockerfile.exists():
            print(f"[sandbox] Building missing image {canonical_name} from {context_dir}...")
            try:
                self.client.images.build(
                    path=str(DOCKER_CONTEXT_ROOT),
                    dockerfile=f"{short_name}/Dockerfile",
                    tag=canonical_name,
                    rm=True,
                    pull=True,
                )
                return canonical_name
            except (BuildError, APIError, DockerException) as e:
                raise RuntimeError(
                    f"Failed to build sandbox image '{canonical_name}' from '{context_dir}': {e}"
                ) from e

        raise RuntimeError(
            f"Sandbox image '{canonical_name}' not found locally and no build context exists at '{context_dir}'."
        )

    def find_free_port(self, start: int, end: int) -> int:
        """Find a free port in the given range."""
        used_ports = set()
        for container in self.client.containers.list(all=True):
            ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
            for port_mapping in ports.values():
                if port_mapping:
                    used_ports.add(int(port_mapping[0].get("HostPort", 0)))

        available_ports = [p for p in range(start, end + 1) if p not in used_ports]
        if not available_ports:
            raise RuntimeError(f"No free ports in range {start}-{end}")

        return random.choice(available_ports)

    def start_sandbox(self, challenge_id: str, image: str) -> Dict:
        """
        Start a sandboxed container for a challenge.
        
        Args:
            challenge_id: The challenge identifier
            image: Docker image to use for the sandbox
            
        Returns:
            Dict with container_id, port, and status
        """
        def _run_container_with_image(resolved_image: str) -> Dict:
            import time

            port = self.find_free_port(17000, 17999)
            container = self.client.containers.run(
                image=resolved_image,
                command=[
                    "/usr/local/bin/ttyd",
                    "--writable",
                    "-p",
                    "7681",
                    "bash",
                ],
                detach=True,
                ports={"7681/tcp": port},
                name=f"cyberlab-{challenge_id[:8]}-{int(time.time())}",
                labels={
                    self.label_key: self.label_value,
                    "challenge_id": challenge_id,
                    "started_at": _utc_now().isoformat(),
                },
                mem_limit="512m",
                cpu_period=100000,
                cpu_quota=50000,
                remove=False,
                network=SANDBOX_NETWORK,
            )
            return {
                "container_id": container.id,
                "port": port,
                "status": "running",
                "challenge_id": challenge_id,
                "resolved_image": resolved_image,
            }

        ensure_sandbox_network(self.client)

        requested_image = image
        try:
            resolved_image = self._resolve_or_build_image(requested_image)
            result = _run_container_with_image(resolved_image)
            result["requested_image"] = requested_image
            result["fallback_used"] = False
            return result
        except (DockerException, APIError, RuntimeError) as primary_error:
            # Safety net: if requested image is unavailable/unbuildable, fallback to rocky base.
            if requested_image != DEFAULT_FALLBACK_IMAGE:
                try:
                    fallback_resolved = self._resolve_or_build_image(DEFAULT_FALLBACK_IMAGE)
                    result = _run_container_with_image(fallback_resolved)
                    result["requested_image"] = requested_image
                    result["fallback_used"] = True
                    result["fallback_reason"] = str(primary_error)
                    return result
                except (DockerException, APIError, RuntimeError) as fallback_error:
                    raise RuntimeError(
                        "Failed to start sandbox. "
                        f"Requested image '{requested_image}' error: {primary_error}. "
                        f"Fallback image '{DEFAULT_FALLBACK_IMAGE}' error: {fallback_error}"
                    ) from fallback_error

            raise RuntimeError(f"Failed to start sandbox for image '{requested_image}': {primary_error}") from primary_error

    def run_validation(self, container_id: str, validation_script: str) -> Dict:
        """
        Run validation script inside the container.
        
        Args:
            container_id: The container to run validation in
            validation_script: Shell script to execute
            
        Returns:
            Dict with exit_code, output, and success status
        """
        container = self.client.containers.get(container_id)

        result = container.exec_run(
            cmd=["/bin/sh", "-c", validation_script],
            demux=True,
        )

        stdout = result.output[0].decode() if result.output[0] else ""
        stderr = result.output[1].decode() if result.output[1] else ""

        return {
            "exit_code": result.exit_code,
            "output": stdout,
            "error": stderr,
            "success": result.exit_code == 0,
        }

    def stop_sandbox(self, container_id: str) -> Dict:
        """
        Stop and remove a sandbox container.
        
        Args:
            container_id: The container to stop
            
        Returns:
            Dict with status and container_id
        """
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=5)
            return {
                "container_id": container_id,
                "status": "stopped",
            }
        except docker.errors.NotFound:
            return {
                "container_id": container_id,
                "status": "not_found",
            }

    def cleanup_orphaned_containers(self) -> Dict:
        """
        Kill containers with cyberlab=true label older than 2 hours.
        
        Returns:
            Dict with count of cleaned containers and list of container IDs
        """
        cutoff_time = _utc_now() - timedelta(hours=2)
        cleaned = []

        containers = self.client.containers.list(
            all=True,
            filters={"label": f"{self.label_key}={self.label_value}"},
        )

        for container in containers:
            started_at_str = container.labels.get("started_at")
            if started_at_str:
                try:
                    started_at = datetime.fromisoformat(started_at_str)
                    if started_at < cutoff_time:
                        try:
                            if container.status == "running":
                                container.kill()
                            container.remove(force=True)
                            cleaned.append(container.id)
                        except Exception:
                            pass  # Container may already be stopped/removed
                except (ValueError, TypeError):
                    pass

        return {
            "cleaned_count": len(cleaned),
            "container_ids": cleaned,
        }


# Singleton instance
_sandbox_service: Optional[SandboxService] = None


def get_sandbox_service() -> SandboxService:
    """Get or create the sandbox service singleton."""
    global _sandbox_service
    if _sandbox_service is None:
        _sandbox_service = SandboxService()
    return _sandbox_service


# Convenience functions
def start_sandbox(challenge_id: str, image: str) -> Dict:
    """Start a sandboxed container."""
    return get_sandbox_service().start_sandbox(challenge_id, image)


def run_validation(container_id: str, validation_script: str) -> Dict:
    """Run validation script in container."""
    return get_sandbox_service().run_validation(container_id, validation_script)


def stop_sandbox(container_id: str) -> Dict:
    """Stop a sandboxed container."""
    return get_sandbox_service().stop_sandbox(container_id)


def cleanup_orphaned_containers() -> Dict:
    """Cleanup orphaned containers."""
    return get_sandbox_service().cleanup_orphaned_containers()
