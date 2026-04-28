---
name: Bug report
about: Report a reproducible defect in power-pptx
labels: bug
---

## Describe the bug

A clear and concise description of what the bug is.

## Minimal reproduction

```python
# paste the smallest snippet that triggers the bug
from pptx import Presentation

prs = Presentation()
# ...
```

If the bug requires an existing `.pptx` file, please attach a minimal redacted
copy that still triggers the issue.

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened. Include the full traceback if an exception was raised.

## Environment

- Python version: (e.g. 3.12.2)
- `power-pptx` version: (e.g. 1.1.0)
- Platform: (e.g. macOS 14, Ubuntu 24.04, Windows 11)
- Installed via: (e.g. `pip install power-pptx`)
