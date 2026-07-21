"""Skill package file storage: blobs directory management and SHA256 hashing."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger("app.services.skill_storage")

DEFAULT_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "skill_registry")


def _get_registry_path() -> str:
    from app.config import settings
    custom = getattr(settings, "skill_registry_path", None)
    if custom:
        return custom
    return os.path.abspath(DEFAULT_REGISTRY_PATH)


def ensure_skill_dir(skill_name: str, version: str) -> Path:
    """Create and return the blob directory for a skill version."""
    base = Path(_get_registry_path())
    blob_dir = base / "blobs" / skill_name / version
    blob_dir.mkdir(parents=True, exist_ok=True)
    return blob_dir


def save_package(
    skill_name: str,
    version: str,
    manifest: dict,
    files: dict[str, bytes],
) -> str:
    """Save a skill package to blob storage. Returns SHA256 of the package."""
    blob_dir = ensure_skill_dir(skill_name, version)

    # Save manifest.json
    manifest_path = blob_dir / "manifest.json"
    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
    manifest_path.write_text(manifest_json, encoding="utf-8")

    # Save additional files (SKILL.md, scripts/, references/, etc.)
    for rel_path, content in files.items():
        file_path = blob_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            file_path.write_text(content, encoding="utf-8")
        else:
            file_path.write_bytes(content)

    # Compute package hash (directory-level)
    package_hash = _compute_dir_hash(blob_dir)
    logger.info("Package saved | %s@%s hash=%s", skill_name, version, package_hash[:16])
    return package_hash


def get_package_content(skill_name: str, version: str) -> dict[str, str | bytes] | None:
    """Read all files from a skill package. Returns None if not found."""
    blob_dir = Path(_get_registry_path()) / "blobs" / skill_name / version
    if not blob_dir.exists():
        return None

    result = {}
    for root, _, files in os.walk(blob_dir):
        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), blob_dir)
            file_path = os.path.join(root, f)
            if f.endswith(('.json', '.md', '.txt', '.yaml', '.yml', '.toml')):
                with open(file_path, 'r', encoding='utf-8') as fp:
                    result[rel_path] = fp.read()
            else:
                with open(file_path, 'rb') as fp:
                    result[rel_path] = fp.read()
    return result


def get_manifest(skill_name: str, version: str) -> dict | None:
    """Read just the manifest.json from a skill package."""
    blob_dir = Path(_get_registry_path()) / "blobs" / skill_name / version
    manifest_path = blob_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def compute_hash(content: bytes) -> str:
    """SHA256 hash of bytes content."""
    return hashlib.sha256(content).hexdigest()


def _compute_dir_hash(directory: Path) -> str:
    """Compute a deterministic hash of all files in a directory."""
    hasher = hashlib.sha256()
    for root, _, files in sorted(os.walk(directory)):
        for f in sorted(files):
            file_path = os.path.join(root, f)
            rel_path = os.path.relpath(file_path, directory)
            hasher.update(rel_path.encode())
            with open(file_path, 'rb') as fp:
                while True:
                    chunk = fp.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)
    return hasher.hexdigest()


def delete_package(skill_name: str, version: str) -> bool:
    """Delete a specific version package from storage."""
    blob_dir = Path(_get_registry_path()) / "blobs" / skill_name / version
    if blob_dir.exists():
        shutil.rmtree(blob_dir)
        # Clean up empty parent directories
        skill_dir = blob_dir.parent
        if skill_dir.exists() and not any(skill_dir.iterdir()):
            skill_dir.rmdir()
        return True
    return False


def delete_skill_packages(skill_name: str) -> bool:
    """Delete all packages for a skill."""
    skill_dir = Path(_get_registry_path()) / "blobs" / skill_name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
        return True
    return False
