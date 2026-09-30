# Security policy

## Supported version

Until the first stable release, security fixes are provided only for the current main branch.

## Reporting a vulnerability

Do not disclose vulnerabilities in a public issue. Use GitHub private vulnerability reporting in the repository's **Security** section. Include a minimal reproduction, operating system, Python and TeX distribution versions, and potential impact.

The application invokes TeX tools on selected documents. TeX is not a safe format for untrusted input. Process untrusted `.tex` files only inside an isolated environment with minimal permissions and an up-to-date TeX distribution.
