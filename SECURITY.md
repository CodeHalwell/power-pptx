# Security policy

## Supported versions

Security fixes are released for the latest minor version on PyPI. Older
versions are not patched; upgrade to the current release.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately through GitHub: on the repository's **Security** tab choose
**Report a vulnerability**, or go straight to
<https://github.com/codehalwell/power-pptx/security/advisories/new>.

Include what you can of:

- the version of `power-pptx`, Python, and the operating system;
- a minimal script or file that shows the problem;
- what an attacker gains, and what they need to control to get it.

You should get an acknowledgement within a week. Once a fix is released the
advisory is published with credit to the reporter, unless you ask otherwise.

## What counts

`power-pptx` reads and writes files and, for some features, starts other
programs. The cases worth a private report are those where input the caller
does not control causes harm:

- **Opening a `.pptx` from an untrusted source.** Parsing must not read local
  files, reach the network, or write outside the destination the caller chose.
  A file that only makes parsing fail or use a lot of memory is a bug; report
  it as an ordinary issue unless the cost is out of all proportion to the size
  of the file. A zip that inflates to more than 100 times its size is refused
  once past 512 MiB; the limits are in `power_pptx.opc.serialized`.
- **Building a deck from an untrusted specification.** `from_spec` and
  `from_html` can load local files and drive a headless browser. A
  specification written by a model or supplied by a user should be treated as
  untrusted: see the composition guide for the options that restrict what such
  a specification may load.
- **Rendering.** `power_pptx.render` and `power-pptx review` run LibreOffice
  and Poppler on the deck. Problems in those programs belong with their
  maintainers; problems in how this library invokes them belong here.
  LibreOffice is started with a throwaway profile that blocks linked content
  and macros, on a copy of the deck whose SVGs have had their external
  references removed. HTML capture runs Chromium without its own sandbox
  (Playwright's default), so capture untrusted HTML inside a container or
  other OS-level sandbox.

Behaviour that requires the attacker to already run Python in your process is
not a vulnerability in this library.
