# Greg and Boris causal-gate runbook

1. Run `.github/workflows/greg-boris-causal-evidence.yml` on the exact PR head.
2. Require exact checkout of `gdb/tee-output@c41f8ff383200320b746e953e92709ae1b505a71`.
3. Preserve Greg baseline and counterfactual records separately.
4. Refresh Boris fork PR, upstream PR, correction commit, and Claude Code issue state through read-only public GitHub API calls.
5. Validate space, transition, time, and causality.
6. Require zero blocking checks and an overall verdict beginning with `READY_TO_NOTIFY`.
7. Upload the complete exact-attempt portfolio and record its artifact digest.
8. Only then prepare external comments whose claims are copied from the machine message contract.
9. Do not approve, close, label, assign, merge, or modify third-party code or issue state.
