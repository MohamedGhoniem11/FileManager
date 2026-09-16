# Security Policy

## Supported versions

Security updates are provided for the latest release only. Older releases should be upgraded to the newest tag.

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities. Instead:

- Open a [private security advisory](https://github.com/MohamedGhoniem11/FileManager/security/advisories/new) on GitHub, or
- Email the maintainer directly (address available on the GitHub profile).

Include, if possible:

- The affected version and platforms
- A minimal description of the vulnerability and how to reproduce it
- Your suggested fix, if you have one

## Disclosure

Vulnerabilities are handled privately until a fix is released, then disclosed in the release notes and changelog. If the issue is confirmed, you'll be credited (unless you prefer to stay anonymous).

## Scope

This project is shipped as source with optional PyInstaller executables. It does not handle untrusted network input by default; file paths are user-controlled by design.