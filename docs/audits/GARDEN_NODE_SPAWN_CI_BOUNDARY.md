# Garden Node spawn CI boundary

This branch uses a temporary draft pull request to `main` only to obtain an observable GitHub Actions merge ref while the original stacked PR is conflicted with its moving base.

The workflow is runtime-diagnostic and read-only. It performs no Airbnb navigation, authentication, form submission, host contact, payment, reservation, external submission, deployment, or merge.

The diagnostic checks whether the exact fixed Garden seccomp profile permits a bundled Node runtime to spawn the exact Chromium headless shell with `--version` inside namespaces, pivot_root, dropped capabilities, and seccomp.

Ownership, approval, external-submission, deployment, and merge authority remain false.
