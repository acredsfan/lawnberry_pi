#!/usr/bin/env python3
"""
Generate offline documentation bundle for LawnBerry Pi v2

Creates a compressed archive of all documentation files with checksum validation,
freshness alerts, and path traversal protection.
"""

import argparse
import hashlib
import json
import logging
import sys
import tarfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentationBundleGenerator:
    """Generate offline documentation bundles"""
    
    FRESHNESS_THRESHOLD_DAYS = 90
    
    def __init__(self, project_root: Path = Path(".")):
        self.project_root = project_root
        self.docs_dir = project_root / "docs"
        self.output_dir = project_root / "verification_artifacts" / "docs-bundle"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def collect_documentation_files(self) -> list[Path]:
        """Collect all documentation files"""
        doc_files = []
        
        # Core documentation
        for doc_file in self.docs_dir.glob("*.md"):
            doc_files.append(doc_file)
        
        # README
        readme = self.project_root / "README.md"
        if readme.exists():
            doc_files.append(readme)
        
        # Specification docs
        specs_dir = self.project_root / "specs"
        if specs_dir.exists():
            for spec_file in specs_dir.rglob("*.md"):
                doc_files.append(spec_file)
        
        # Constitution
        constitution = self.project_root / ".specify" / "memory" / "constitution.md"
        if constitution.exists():
            doc_files.append(constitution)
        
        logger.info(f"Collected {len(doc_files)} documentation files")
        return doc_files
    
    def validate_path_traversal(self, file_path: Path) -> bool:
        """Validate that file path doesn't escape project root"""
        try:
            resolved = file_path.resolve()
            project_resolved = self.project_root.resolve()
            return str(resolved).startswith(str(project_resolved))
        except Exception as e:
            logger.error(f"Path validation failed for {file_path}: {e}")
            return False
    
    def compute_checksum(self, file_path: Path) -> str:
        """Compute SHA256 checksum of a file"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def check_freshness(self, file_path: Path) -> dict[str, Any]:
        """Check if documentation is fresh (modified within threshold)"""
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
        age_days = (datetime.now(UTC) - mtime).days
        
        is_fresh = age_days <= self.FRESHNESS_THRESHOLD_DAYS
        
        warning = None
        if not is_fresh:
            warning = (
                "Documentation is "
                f"{age_days} days old "
                f"(threshold: {self.FRESHNESS_THRESHOLD_DAYS} days)"
            )

        return {
            "last_modified": mtime.isoformat(),
            "age_days": age_days,
            "is_fresh": is_fresh,
            "warning": warning,
        }
    
    def generate_manifest(self, doc_files: list[Path], bundle_path: Path) -> dict[str, Any]:
        """Generate manifest for documentation bundle"""
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "bundle_path": str(bundle_path.relative_to(self.project_root)),
            "bundle_checksum": self.compute_checksum(bundle_path),
            "bundle_size_bytes": bundle_path.stat().st_size,
            "freshness_threshold_days": self.FRESHNESS_THRESHOLD_DAYS,
            "documents": []
        }
        
        stale_count = 0
        
        for doc_file in doc_files:
            if not self.validate_path_traversal(doc_file):
                logger.warning(f"Skipping file due to path traversal risk: {doc_file}")
                continue
            
            freshness = self.check_freshness(doc_file)
            
            if not freshness["is_fresh"]:
                stale_count += 1
            
            doc_info = {
                "path": str(doc_file.relative_to(self.project_root)),
                "checksum": self.compute_checksum(doc_file),
                "size_bytes": doc_file.stat().st_size,
                "freshness": freshness
            }
            
            manifest["documents"].append(doc_info)
        
        manifest["total_documents"] = len(manifest["documents"])
        manifest["stale_documents"] = stale_count
        manifest["offline_available"] = True
        
        return manifest
    
    def create_tarball(
        self,
        doc_files: list[Path],
        output_name: str = "docs-bundle.tar.gz",
    ) -> Path:
        """Create compressed tarball of documentation"""
        output_path = self.output_dir / output_name
        
        with tarfile.open(output_path, "w:gz") as tar:
            for doc_file in doc_files:
                if not self.validate_path_traversal(doc_file):
                    continue
                
                arcname = str(doc_file.relative_to(self.project_root))
                tar.add(doc_file, arcname=arcname)
        
        logger.info(f"Created tarball: {output_path}")
        return output_path
    
    def create_zipfile(
        self,
        doc_files: list[Path],
        output_name: str = "docs-bundle.zip",
    ) -> Path:
        """Create ZIP archive of documentation"""
        output_path = self.output_dir / output_name
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for doc_file in doc_files:
                if not self.validate_path_traversal(doc_file):
                    continue
                
                arcname = str(doc_file.relative_to(self.project_root))
                zipf.write(doc_file, arcname=arcname)
        
        logger.info(f"Created ZIP file: {output_path}")
        return output_path
    
    def generate_bundle(self, format: str = "tarball") -> dict[str, Any]:
        """Generate complete documentation bundle"""
        logger.info("Starting documentation bundle generation...")
        
        # Collect documentation files
        doc_files = self.collect_documentation_files()
        
        if not doc_files:
            logger.error("No documentation files found")
            return {"error": "No documentation files found"}
        
        # Create bundle
        if format == "tarball":
            bundle_path = self.create_tarball(doc_files)
        elif format == "zip":
            bundle_path = self.create_zipfile(doc_files)
        else:
            logger.error(f"Unsupported format: {format}")
            return {"error": f"Unsupported format: {format}"}
        
        # Generate manifest
        manifest = self.generate_manifest(doc_files, bundle_path)
        
        # Save manifest
        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Manifest saved to: {manifest_path}")
        
        # Check for stale documents
        if manifest["stale_documents"] > 0:
            logger.warning(
                "%(count)s document(s) are stale (older than %(threshold)s days)",
                {
                    "count": manifest["stale_documents"],
                    "threshold": self.FRESHNESS_THRESHOLD_DAYS,
                },
            )
        
        return manifest


def main():
    """CLI entry point"""

    parser = argparse.ArgumentParser(description="Generate offline documentation bundle")
    parser.add_argument(
        "--format",
        choices=["tarball", "zip"],
        default="tarball",
        help="Bundle format (default: tarball)"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Project root directory"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: verification_artifacts/docs-bundle)"
    )
    
    args = parser.parse_args()
    
    generator = DocumentationBundleGenerator(project_root=args.project_root)
    
    if args.output:
        generator.output_dir = args.output
        generator.output_dir.mkdir(parents=True, exist_ok=True)
    
    manifest = generator.generate_bundle(format=args.format)
    
    if "error" in manifest:
        logger.error(manifest["error"])
        sys.exit(1)
    
    logger.info("Documentation bundle generation complete!")
    logger.info(f"Bundle: {manifest['bundle_path']}")
    logger.info(f"Total documents: {manifest['total_documents']}")
    logger.info(f"Stale documents: {manifest['stale_documents']}")
    logger.info(f"Bundle size: {manifest['bundle_size_bytes']} bytes")
    logger.info(f"Bundle checksum: {manifest['bundle_checksum']}")
    
    sys.exit(0)


def check_bundle_freshness(generator: DocumentationBundleGenerator) -> bool:
    """Check if documentation bundle is up-to-date (for CI)"""
    manifest_file = generator.output_dir / "manifest.json"
    
    if not manifest_file.exists():
        logger.error("No documentation bundle manifest found")
        return False
    
    try:
        with open(manifest_file) as f:
            manifest = json.load(f)
        
        # Check if bundle is too old
        generated_at = datetime.fromisoformat(manifest['generated_at'])
        age = datetime.now(UTC) - generated_at
        
        if age > timedelta(days=generator.FRESHNESS_THRESHOLD_DAYS):
            logger.error(f"Documentation bundle is stale ({age.days} days old)")
            return False
        
        # Check if any documents are marked as stale
        if manifest.get('stale_documents', 0) > 0:
            logger.error(f"Bundle contains {manifest['stale_documents']} stale documents")
            return False
        
        logger.info("Documentation bundle is fresh and valid")
        return True
        
    except Exception as e:
        logger.error(f"Error checking bundle freshness: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate offline documentation bundle")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check if bundle is fresh, don't generate"
    )
    args = parser.parse_args()
    
    if args.check_only:
        generator = DocumentationBundleGenerator()
        is_fresh = check_bundle_freshness(generator)
        sys.exit(0 if is_fresh else 1)
    else:
        main()
