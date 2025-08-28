"""
Build System - Automated build and packaging for deployment
Handles dependency management, validation, and deployable package creation
"""

import asyncio
import logging
import json
import hashlib
import shutil
import subprocess
import tempfile
import tarfile
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import aiofiles
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from .config_manager import ConfigManager


logger = logging.getLogger(__name__)


class BuildStatus(Enum):
    """Build status"""
    PENDING = "pending"
    BUILDING = "building"
    TESTING = "testing"
    PACKAGING = "packaging"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class BuildConfig:
    """Build configuration"""
    version: str
    build_type: str  # release, debug, staging
    include_tests: bool
    include_docs: bool
    compression_level: int
    sign_package: bool
    run_tests: bool
    validate_config: bool


@dataclass
class BuildResult:
    """Build result information"""
    status: BuildStatus
    version: str
    package_path: Optional[Path]
    checksum: Optional[str]
    signature: Optional[str]
    size: int
    build_time: float
    test_results: Dict[str, Any]
    errors: List[str]
    metadata: Dict[str, Any]


class BuildSystem:
    """
    Automated build system for creating deployable packages
    """
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config = self._load_build_config()
        
        # Build directories
        self.build_dir = Path("/tmp/lawnberry_build")
        # Output artifacts should be written to /var/lib (writable), not /opt
        self.output_dir = Path("/var/lib/lawnberry/builds")
        self.source_dir = Path("/opt/lawnberry")
        
        # Signing key
        self.private_key = self._load_private_key()
        
    def _load_build_config(self) -> Dict[str, Any]:
        """Load build configuration"""
        try:
            config = self.config_manager.get_config('build')
            return config if config else self._default_build_config()
        except Exception as e:
            logger.warning(f"Failed to load build config, using defaults: {e}")
            return self._default_build_config()
    
    def _default_build_config(self) -> Dict[str, Any]:
        """Default build configuration"""
        return {
            'build_dir': '/tmp/lawnberry_build',
            'output_dir': '/var/lib/lawnberry/builds',
            'compression_level': 6,
            'include_tests': False,
            'include_docs': True,
            'sign_packages': True,
            'run_tests': True,
            'validate_config': True,
            'exclude_patterns': [
                '*.pyc',
                '__pycache__',
                '.git',
                '.pytest_cache',
                'tests/coverage',
                '*.log',
                '.env',
                'node_modules'
            ],
            'required_files': [
                'src/',
                'config/',
                'requirements.txt',
                'README.md'
            ]
        }
    
    def _load_private_key(self):
        """Load private key for package signing"""
        try:
            # Prefer writable var-lib location; fall back to read-only /opt if provisioned there
            candidates = [
                Path("/var/lib/lawnberry/keys/deployment_private.pem"),
                Path("/opt/lawnberry/keys/deployment_private.pem"),
            ]
            for private_key_path in candidates:
                if private_key_path.exists():
                    with open(private_key_path, 'rb') as f:
                        return serialization.load_pem_private_key(f.read(), password=None)
            logger.warning("Deployment private key not found, package signing disabled")
            return None
        except Exception as e:
            logger.error(f"Failed to load private key: {e}")
            return None
    
    async def initialize(self):
        """Initialize build system"""
        try:
            logger.info("Initializing Build System")
            
            # Create directories
            for path in [self.build_dir, self.output_dir]:
                path.mkdir(parents=True, exist_ok=True)
            
            # Generate keypair if not exists
            if not self.private_key:
                await self._generate_keypair()
            
            logger.info("Build System initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Build System: {e}")
            raise
    
    async def _generate_keypair(self):
        """Generate deployment keypair"""
        try:
            logger.info("Generating deployment keypair")
            
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            
            # Get public key
            public_key = private_key.public_key()
            
            # Create keys directory in writable var-lib location
            key_dir = Path("/var/lib/lawnberry/keys")
            key_dir.mkdir(parents=True, exist_ok=True)
            
            # Save private key
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            private_key_path = key_dir / "deployment_private.pem"
            private_key_path.write_bytes(private_pem)
            private_key_path.chmod(0o600)
            
            # Save public key
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            public_key_path = key_dir / "deployment_public.pem"
            public_key_path.write_bytes(public_pem)
            
            self.private_key = private_key
            
            logger.info("Deployment keypair generated successfully")
            
        except Exception as e:
            logger.error(f"Failed to generate keypair: {e}")
            raise
    
    async def build_package(self, build_config: BuildConfig) -> BuildResult:
        """Build deployable package"""
        start_time = datetime.now()
        build_result = BuildResult(
            status=BuildStatus.BUILDING,
            version=build_config.version,
            package_path=None,
            checksum=None,
            signature=None,
            size=0,
            build_time=0.0,
            test_results={},
            errors=[],
            metadata={}
        )
        
        try:
            logger.info(f"Starting build for version {build_config.version}")
            
            # Create build workspace
            build_workspace = self.build_dir / f"build_{build_config.version}_{int(datetime.now().timestamp())}"
            build_workspace.mkdir(parents=True, exist_ok=True)
            
            # Copy source files
            await self._copy_source_files(build_workspace, build_config)
            
            # Validate configuration
            if build_config.validate_config:
                await self._validate_configurations(build_workspace)
            
            # Install dependencies
            await self._install_dependencies(build_workspace)
            
            # Run tests
            if build_config.run_tests:
                build_result.status = BuildStatus.TESTING
                test_results = await self._run_tests(build_workspace)
                build_result.test_results = test_results
                
                if not test_results.get('success', False):
                    build_result.status = BuildStatus.FAILED
                    build_result.errors.append("Tests failed")
                    return build_result
            
            # Create package
            build_result.status = BuildStatus.PACKAGING
            package_path = await self._create_package(build_workspace, build_config)
            
            # Calculate checksum
            checksum = await self._calculate_checksum(package_path)
            
            # Sign package
            signature = None
            if build_config.sign_package and self.private_key:
                signature = await self._sign_package(package_path)
            
            # Update build result
            build_result.status = BuildStatus.SUCCESS
            build_result.package_path = package_path
            build_result.checksum = checksum
            build_result.signature = signature
            build_result.size = package_path.stat().st_size
            build_result.build_time = (datetime.now() - start_time).total_seconds()
            build_result.metadata = await self._generate_metadata(build_config, build_result)
            
            # Save build info
            await self._save_build_info(build_result)
            
            # Cleanup build workspace
            shutil.rmtree(build_workspace, ignore_errors=True)
            
            logger.info(f"Build completed successfully: {build_config.version}")
            return build_result
            
        except Exception as e:
            logger.error(f"Build failed: {e}")
            build_result.status = BuildStatus.FAILED
            build_result.errors.append(str(e))
            build_result.build_time = (datetime.now() - start_time).total_seconds()
            
            # Cleanup on failure
            if 'build_workspace' in locals():
                shutil.rmtree(build_workspace, ignore_errors=True)
            
            return build_result
    
    async def _copy_source_files(self, build_workspace: Path, build_config: BuildConfig):
        """Copy source files to build workspace"""
        try:
            logger.info("Copying source files")
            
            # Copy required files and directories
            required_files = self.config.get('required_files', [])
            exclude_patterns = self.config.get('exclude_patterns', [])
            
            for item in required_files:
                source_path = self.source_dir / item
                target_path = build_workspace / item
                
                if source_path.exists():
                    if source_path.is_dir():
                        await self._copy_directory(source_path, target_path, exclude_patterns)
                    else:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, target_path)
                else:
                    logger.warning(f"Required file not found: {item}")
            
            # Copy additional files for different build types
            if build_config.include_tests:
                tests_path = self.source_dir / "tests"
                if tests_path.exists():
                    await self._copy_directory(tests_path, build_workspace / "tests", exclude_patterns)
            
            if build_config.include_docs:
                docs_files = ["README.md", "docs/"]
                for doc_file in docs_files:
                    doc_path = self.source_dir / doc_file
                    if doc_path.exists():
                        if doc_path.is_dir():
                            await self._copy_directory(doc_path, build_workspace / doc_file, exclude_patterns)
                        else:
                            shutil.copy2(doc_path, build_workspace / doc_file)
                            
        except Exception as e:
            logger.error(f"Failed to copy source files: {e}")
            raise
    
    async def _copy_directory(self, source: Path, target: Path, exclude_patterns: List[str]):
        """Copy directory with exclusions"""
        import fnmatch
        
        def should_exclude(path: Path) -> bool:
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(str(path), pattern):
                    return True
            return False
        
        target.mkdir(parents=True, exist_ok=True)
        
        for item in source.rglob('*'):
            if should_exclude(item):
                continue
                
            relative_path = item.relative_to(source)
            target_item = target / relative_path
            
            if item.is_dir():
                target_item.mkdir(parents=True, exist_ok=True)
            else:
                target_item.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target_item)
    
    async def _validate_configurations(self, build_workspace: Path):
        """Validate configuration files"""
        try:
            logger.info("Validating configurations")
            
            config_dir = build_workspace / "config"
            if not config_dir.exists():
                raise Exception("Configuration directory not found")
            
            # Validate YAML files
            for config_file in config_dir.glob("*.yaml"):
                try:
                    with open(config_file, 'r') as f:
                        yaml.safe_load(f)
                except yaml.YAMLError as e:
                    raise Exception(f"Invalid YAML in {config_file.name}: {e}")
            
            # Validate required configuration files
            required_configs = ["system.yaml", "hardware.yaml", "safety.yaml"]
            for config_name in required_configs:
                config_file = config_dir / config_name
                if not config_file.exists():
                    raise Exception(f"Required configuration file missing: {config_name}")
                    
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
    
    async def _install_dependencies(self, build_workspace: Path):
        """Install Python dependencies"""
        try:
            logger.info("Installing dependencies")
            
            requirements_file = build_workspace / "requirements.txt"
            if not requirements_file.exists():
                logger.warning("requirements.txt not found, skipping dependency installation")
                return
            
            # Create virtual environment
            venv_path = build_workspace / "venv"
            await self._run_command([
                "python3", "-m", "venv", str(venv_path)
            ], cwd=build_workspace)
            
            # Install dependencies
            pip_path = venv_path / "bin" / "pip"
            await self._run_command([
                str(pip_path), "install", "-r", "requirements.txt"
            ], cwd=build_workspace)
            
        except Exception as e:
            logger.error(f"Dependency installation failed: {e}")
            raise
    
    async def _run_tests(self, build_workspace: Path) -> Dict[str, Any]:
        """Run test suite"""
        try:
            logger.info("Running tests")
            
            test_results = {
                'success': False,
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0,
                'coverage': 0.0,
                'duration': 0.0,
                'errors': []
            }
            
            # Check if tests directory exists
            tests_dir = build_workspace / "tests"
            if not tests_dir.exists():
                logger.warning("Tests directory not found, skipping tests")
                test_results['success'] = True  # No tests to run
                return test_results
            
            start_time = datetime.now()
            
            # Run pytest
            venv_path = build_workspace / "venv"
            pytest_path = venv_path / "bin" / "pytest"
            
            if pytest_path.exists():
                result = await self._run_command([
                    str(pytest_path),
                    "tests/",
                    "--tb=short",
                    "--junit-xml=test_results.xml",
                    "--cov=src",
                    "--cov-report=json:coverage.json"
                ], cwd=build_workspace)
                
                test_results['duration'] = (datetime.now() - start_time).total_seconds()
                test_results['success'] = result.returncode == 0
                
                # Parse test results
                await self._parse_test_results(build_workspace, test_results)
            else:
                logger.warning("pytest not found, running basic Python tests")
                # Run basic syntax check
                result = await self._run_command([
                    "python3", "-m", "py_compile", "src"
                ], cwd=build_workspace)
                
                test_results['success'] = result.returncode == 0
                test_results['duration'] = (datetime.now() - start_time).total_seconds()
            
            return test_results
            
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return {
                'success': False,
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0,
                'coverage': 0.0,
                'duration': 0.0,
                'errors': [str(e)]
            }
    
    async def _parse_test_results(self, build_workspace: Path, test_results: Dict[str, Any]):
        """Parse test results from output files"""
        try:
            # Parse JUnit XML if available
            junit_file = build_workspace / "test_results.xml"
            if junit_file.exists():
                import xml.etree.ElementTree as ET
                tree = ET.parse(junit_file)
                root = tree.getroot()
                
                test_results['total_tests'] = int(root.get('tests', 0))
                test_results['failed_tests'] = int(root.get('failures', 0)) + int(root.get('errors', 0))
                test_results['passed_tests'] = test_results['total_tests'] - test_results['failed_tests']
            
            # Parse coverage report if available
            coverage_file = build_workspace / "coverage.json"
            if coverage_file.exists():
                with open(coverage_file, 'r') as f:
                    coverage_data = json.load(f)
                    test_results['coverage'] = coverage_data.get('totals', {}).get('percent_covered', 0.0)
                    
        except Exception as e:
            logger.warning(f"Failed to parse test results: {e}")
    
    async def _create_package(self, build_workspace: Path, build_config: BuildConfig) -> Path:
        """Create deployable package"""
        try:
            logger.info("Creating package")
            
            # Package filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            package_name = f"lawnberry_{build_config.version}_{timestamp}.tar.gz"
            package_path = self.output_dir / package_name
            
            # Create tar.gz package
            with tarfile.open(package_path, "w:gz", compresslevel=build_config.compression_level) as tar:
                # Add all files from build workspace
                for item in build_workspace.rglob('*'):
                    if item.is_file():
                        arcname = item.relative_to(build_workspace)
                        tar.add(item, arcname=arcname)
            
            logger.info(f"Package created: {package_path}")
            return package_path
            
        except Exception as e:
            logger.error(f"Package creation failed: {e}")
            raise
    
    async def _calculate_checksum(self, package_path: Path) -> str:
        """Calculate package checksum"""
        try:
            sha256_hash = hashlib.sha256()
            
            async with aiofiles.open(package_path, 'rb') as f:
                while chunk := await f.read(8192):
                    sha256_hash.update(chunk)
            
            return sha256_hash.hexdigest()
            
        except Exception as e:
            logger.error(f"Checksum calculation failed: {e}")
            raise
    
    async def _sign_package(self, package_path: Path) -> str:
        """Sign package with private key"""
        try:
            if not self.private_key:
                logger.warning("No private key available for signing")
                return ""
            
            # Read package content
            async with aiofiles.open(package_path, 'rb') as f:
                package_content = await f.read()
            
            # Sign package
            signature = self.private_key.sign(
                package_content,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Encode signature as base64
            import base64
            return base64.b64encode(signature).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Package signing failed: {e}")
            raise
    
    async def _generate_metadata(self, build_config: BuildConfig, build_result: BuildResult) -> Dict[str, Any]:
        """Generate package metadata"""
        return {
            'build_config': asdict(build_config),
            'build_time': build_result.build_time,
            'build_timestamp': datetime.now().isoformat(),
            'builder_version': "1.0.0",
            'python_version': await self._get_python_version(),
            'system_info': await self._get_system_info(),
            'dependencies': await self._get_dependencies_info(),
            'test_summary': build_result.test_results
        }
    
    async def _get_python_version(self) -> str:
        """Get Python version"""
        try:
            result = await self._run_command(["python3", "--version"])
            return result.stdout.decode().strip()
        except Exception:
            return "unknown"
    
    async def _get_system_info(self) -> Dict[str, str]:
        """Get system information"""
        try:
            uname_result = await self._run_command(["uname", "-a"])
            return {
                'system': uname_result.stdout.decode().strip(),
                'platform': 'raspberry-pi'  # Assume RPi for now
            }
        except Exception:
            return {'system': 'unknown', 'platform': 'unknown'}
    
    async def _get_dependencies_info(self) -> List[str]:
        """Get installed dependencies information"""
        try:
            # This would be run in the build venv
            return []  # Simplified for now
        except Exception:
            return []
    
    async def _save_build_info(self, build_result: BuildResult):
        """Save build information"""
        try:
            build_info = {
                'status': build_result.status.value,
                'version': build_result.version,
                'package_path': str(build_result.package_path) if build_result.package_path else None,
                'checksum': build_result.checksum,
                'signature': build_result.signature,
                'size': build_result.size,
                'build_time': build_result.build_time,
                'test_results': build_result.test_results,
                'errors': build_result.errors,
                'metadata': build_result.metadata,
                'created_at': datetime.now().isoformat()
            }
            
            info_file = self.output_dir / f"build_info_{build_result.version}.json"
            async with aiofiles.open(info_file, 'w') as f:
                await f.write(json.dumps(build_info, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save build info: {e}")
    
    async def _run_command(self, command: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run system command"""
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            stdout, stderr = await process.communicate()
            
            result = subprocess.CompletedProcess(
                command, process.returncode or 0, stdout, stderr
            )
            
            if result.returncode != 0:
                logger.warning(f"Command failed: {' '.join(command)}, stderr: {stderr.decode()}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to run command {' '.join(command)}: {e}")
            raise
    
    async def list_builds(self) -> List[Dict[str, Any]]:
        """List available builds"""
        try:
            builds = []
            
            for info_file in self.output_dir.glob("build_info_*.json"):
                try:
                    async with aiofiles.open(info_file, 'r') as f:
                        build_info = json.loads(await f.read())
                        builds.append(build_info)
                except Exception as e:
                    logger.warning(f"Failed to read build info {info_file}: {e}")
            
            # Sort by creation time (newest first)
            builds.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return builds
            
        except Exception as e:
            logger.error(f"Failed to list builds: {e}")
            return []
    
    async def get_build_info(self, version: str) -> Optional[Dict[str, Any]]:
        """Get build information for specific version"""
        try:
            info_file = self.output_dir / f"build_info_{version}.json"
            if info_file.exists():
                async with aiofiles.open(info_file, 'r') as f:
                    return json.loads(await f.read())
            return None
            
        except Exception as e:
            logger.error(f"Failed to get build info for {version}: {e}")
            return None
    
    async def cleanup_old_builds(self, keep_count: int = 10):
        """Cleanup old build files"""
        try:
            builds = await self.list_builds()
            
            # Remove old builds beyond keep_count
            for build_info in builds[keep_count:]:
                try:
                    # Remove package file
                    if build_info.get('package_path'):
                        package_path = Path(build_info['package_path'])
                        if package_path.exists():
                            package_path.unlink()
                    
                    # Remove build info file
                    info_file = self.output_dir / f"build_info_{build_info['version']}.json"
                    if info_file.exists():
                        info_file.unlink()
                        
                    logger.info(f"Cleaned up old build: {build_info['version']}")
                    
                except Exception as e:
                    logger.warning(f"Failed to cleanup build {build_info['version']}: {e}")
                    
        except Exception as e:
            logger.error(f"Build cleanup failed: {e}")
