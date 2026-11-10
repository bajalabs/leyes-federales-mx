# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's private
vulnerability reporting: open the repository's **Security** tab and choose
**Report a vulnerability**
(<https://github.com/bajalabs/leyes-federales-mx/security/advisories/new>).
Do not open a public issue.

Include what you found, how to reproduce it, and the impact you expect. You
will get an acknowledgement within a few days, and a fix or a decision as
soon as the issue is understood.

## Scope

The scripts download files from the Cámara de Diputados and parse them, and
the release assets are files people download and open. Relevant reports
include, for example, a way for a crafted source file to make the pipeline
write outside its folders or run commands, or a release asset that does not
match its `SHA256SUMS`.

An error in the legal data itself is not a security issue: please open a
[data error](https://github.com/bajalabs/leyes-federales-mx/issues/new?template=data-error.yml)
instead.

## Supported versions

Only the latest release and the `main` branch receive fixes.
