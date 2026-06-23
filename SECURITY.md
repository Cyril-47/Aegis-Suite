# Security Policy

## Supported Versions

We actively provide security updates for the following versions of Aegis Suite:

| Version | Supported |
| :--- | :--- |
| v2.2.x | Yes (Active) |
| v2.1.x | Yes (Maintenance) |
| v2.0.x | Limited (Critical only) |
| < v2.0 | No |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security bugs.**

If you discover a security vulnerability in Aegis Suite, please email us directly or contact project maintainers to report it privately.

Please include:
* A descriptive title and summary of the issue.
* Steps to reproduce, a proof of concept (PoC), or screenshots.
* Any potential impact or exploits.

We will acknowledge receipt within 48 hours and work with you to coordinate a security patch and disclosure.

## Security Architecture

### Secrets at Rest
In local desktop deployments (Windows EXE), Aegis Suite protects secrets (such as `DISCORD_BOT_TOKEN`, `JWT_SECRET`, and `ADMIN_PASSWORD_HASH`) using **Windows Data Protection API (DPAPI)** inside the `.env.enc` file. 

This model binds the decryption key directly to the current Windows user's credentials. The credentials cannot be decrypted if copied off the machine or accessed by a different Windows user account on the same machine.

### Log Redaction
Aegis Suite utilizes a strict `RedactionFilter` in its logging pipeline to automatically intercept and redact sensitive fields, ensuring that active tokens, password hashes, and JWT secrets are never written in plain text to the log files (`aegis.log`, `aegis.err.log`) or system console outputs.

### Diagnostics Protection
The diagnostics packager automatically runs a config sanitizer before bundling diagnostic archives, redacting credentials and sensitive information while leaving structural properties intact for easier troubleshooting.
