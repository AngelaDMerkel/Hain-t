# Security

Hain’t is currently intended for a trusted workstation or controlled shop network.

- The API has no authentication or authorization.
- The default Compose configuration binds port 8080 to `127.0.0.1` only.
- Changing the binding to `0.0.0.0` exposes read and write endpoints to the network.
- Saved positions may be operationally sensitive; protect Docker volumes and backups accordingly.

Please report vulnerabilities through GitHub's private vulnerability reporting feature when it is enabled for the repository. Do not include production measurements, credentials, or other sensitive data in a public issue.
