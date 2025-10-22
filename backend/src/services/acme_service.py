import asyncio
import subprocess
import tempfile
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..core.observability import observability


logger = observability.get_logger(__name__)


class ACMEService:
    """ACME TLS certificate management service."""
    
    def __init__(self):
        self.certificates: Dict[str, Dict[str, Any]] = {}
        self.challenges: Dict[str, str] = {}  # token -> file_content
        self.cert_dir = Path("/etc/lawnberry/certs")
        self.challenge_dir = Path("/var/www/.well-known/acme-challenge")
        self.auto_renewal_enabled = True
        
    def initialize(self):
        """Initialize ACME service directories."""
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        self.challenge_dir.mkdir(parents=True, exist_ok=True)
        
    def request_certificate(self, domain: str, email: str) -> Dict[str, Any]:
        """Request a new certificate from Let's Encrypt."""
        try:
            # Placeholder for ACME certificate request
            # In production, this would use a proper ACME client like certbot
            
            result = {
                "domain": domain,
                "status": "requested",
                "requested_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(days=90),
                "auto_renew": True
            }
            
            self.certificates[domain] = result
            return result
            
        except Exception as e:
            return {
                "domain": domain,
                "status": "failed",
                "error": str(e),
                "requested_at": datetime.now(timezone.utc)
            }
            
    def create_challenge_file(self, token: str, key_auth: str) -> str:
        """Create HTTP-01 challenge file."""
        challenge_file = self.challenge_dir / token
        challenge_file.write_text(key_auth)
        
        # Store for cleanup
        self.challenges[token] = key_auth
        
        return str(challenge_file)
        
    def get_challenge_content(self, token: str) -> Optional[str]:
        """Get challenge content for serving."""
        return self.challenges.get(token)
        
    def cleanup_challenge(self, token: str):
        """Clean up challenge file."""
        challenge_file = self.challenge_dir / token
        if challenge_file.exists():
            challenge_file.unlink()
            
        self.challenges.pop(token, None)
        
    def list_certificates(self) -> Dict[str, Dict[str, Any]]:
        """List all managed certificates."""
        return self.certificates.copy()
        
    def get_certificate_info(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get certificate information."""
        return self.certificates.get(domain)
        
    def is_certificate_valid(self, domain: str) -> bool:
        """Check if certificate is valid and not expired."""
        cert_info = self.certificates.get(domain)
        if not cert_info:
            return False
            
        if cert_info["status"] != "issued":
            return False
            
        # Check expiration (renew if < 30 days)
        expires_at = cert_info["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            
        renewal_threshold = datetime.now(timezone.utc) + timedelta(days=30)
        return expires_at > renewal_threshold
        
    def needs_renewal(self, domain: str) -> bool:
        """Check if certificate needs renewal."""
        return not self.is_certificate_valid(domain)
        
    def renew_certificate(self, domain: str) -> Dict[str, Any]:
        """Renew an existing certificate."""
        cert_info = self.certificates.get(domain)
        if not cert_info:
            return {"error": "Certificate not found"}
            
        try:
            # Placeholder renewal logic
            cert_info.update({
                "status": "renewed",
                "renewed_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(days=90)
            })
            
            return cert_info
            
        except Exception as e:
            return {"error": str(e)}
            
    def revoke_certificate(self, domain: str) -> bool:
        """Revoke a certificate."""
        if domain not in self.certificates:
            return False
            
        try:
            # Placeholder revocation logic
            self.certificates[domain]["status"] = "revoked"
            self.certificates[domain]["revoked_at"] = datetime.now(timezone.utc)
            return True
            
        except Exception:
            return False
            
    def get_certificates_needing_renewal(self) -> List[str]:
        """Get list of domains with certificates needing renewal."""
        domains = []
        for domain, cert_info in self.certificates.items():
            if cert_info.get("auto_renew", True) and self.needs_renewal(domain):
                domains.append(domain)
        return domains
        
    def setup_http_challenge_server(self, port: int = 80):
        """Set up HTTP server for ACME challenges."""
        try:
            # Create nginx configuration for ACME challenges
            nginx_config = f"""
# ACME HTTP-01 challenge configuration
server {{
    listen {port};
    listen [::]:{port};
    server_name _;
    
    # ACME challenge location
    location /.well-known/acme-challenge/ {{
        root /var/www;
        try_files $uri =404;
    }}
    
    # Redirect all other HTTP traffic to HTTPS
    location / {{
        return 301 https://$host$request_uri;
    }}
}}
"""
            
            # Write nginx config for ACME challenges
            config_path = Path("/etc/nginx/sites-available/lawnberry-acme")
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(nginx_config)
            
            # Enable the configuration
            symlink_path = Path("/etc/nginx/sites-enabled/lawnberry-acme")
            if not symlink_path.exists():
                symlink_path.symlink_to(config_path)
                
            # Test and reload nginx
            result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
            if result.returncode == 0:
                subprocess.run(["systemctl", "reload", "nginx"], check=True)
                logger.info(
                    "Reloaded nginx after writing ACME challenge configuration",
                    extra={"command": "nginx -t"},
                )
                return True
            logger.error(
                "Nginx configuration validation failed",
                extra={"stderr": result.stderr},
            )
            observability.record_error(
                origin="acme",
                message="Nginx configuration validation failed",
                metadata={"stderr": result.stderr},
            )
            return False

        except Exception as e:
            logger.error("Failed to setup HTTP challenge server", exc_info=True)
            observability.record_error(
                origin="acme",
                message="Failed to setup HTTP challenge server",
                exception=e,
            )
            return False
        
    def install_certificate(self, domain: str, cert_path: str, key_path: str, 
                          chain_path: Optional[str] = None) -> bool:
        """Install certificate files."""
        try:
            # Copy certificate files to the cert directory
            domain_dir = self.cert_dir / domain
            domain_dir.mkdir(exist_ok=True)
            
            # In production, this would copy the actual certificate files
            # and reload the web server configuration
            
            cert_info = self.certificates.get(domain, {})
            cert_info.update({
                "status": "installed",
                "installed_at": datetime.now(timezone.utc),
                "cert_path": str(domain_dir / "cert.pem"),
                "key_path": str(domain_dir / "key.pem"),
                "chain_path": str(domain_dir / "chain.pem") if chain_path else None
            })
            
            self.certificates[domain] = cert_info
            return True
            
        except Exception as e:
            logger.error("Certificate installation failed", exc_info=True)
            observability.record_error(
                origin="acme",
                message="Certificate installation failed",
                exception=e,
            )
            return False
            
    def reload_web_server(self):
        """Reload web server after certificate update."""
        try:
            # Test nginx configuration before reload
            result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
            if result.returncode == 0:
                subprocess.run(["systemctl", "reload", "nginx"], check=True)
                logger.info("Web server reloaded after certificate update")
                return
            logger.error(
                "Nginx configuration validation failed during reload",
                extra={"stderr": result.stderr},
            )
            raise Exception("Invalid nginx configuration")
        except Exception as e:
            logger.error("Web server reload failed", exc_info=True)
            observability.record_error(
                origin="acme",
                message="Web server reload failed",
                exception=e,
            )
            raise
            
    def get_renewal_status(self) -> Dict[str, Any]:
        """Get renewal status and statistics."""
        total_certs = len(self.certificates)
        valid_certs = sum(1 for domain in self.certificates if self.is_certificate_valid(domain))
        expired_certs = total_certs - valid_certs
        renewal_needed = len(self.get_certificates_needing_renewal())
        
        return {
            "total_certificates": total_certs,
            "valid_certificates": valid_certs,
            "expired_certificates": expired_certs,
            "renewal_needed": renewal_needed,
            "auto_renewal_enabled": self.auto_renewal_enabled,
            "last_check": datetime.now(timezone.utc).isoformat()
        }


# Global instance
acme_service = ACMEService()