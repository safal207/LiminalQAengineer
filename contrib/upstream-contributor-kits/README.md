# Upstream contributor kits: Boris + Greg

This directory prepares two small, reviewable upstream contributions.

## Boris Cherny / `anthropics/claude-code-action#1522`

Target revision:

```text
anthropics/claude-code-action
b76a0776ae74036e77cd11018083743453d7ad35
```

Problem:

```text
pull_request_review webhook
  -> review.submitted_at becomes triggerTime
  -> filterReviewsToTriggerTime rejects submittedAt >= triggerTime
  -> the triggering review is removed
  -> its inline comments disappear from prompt context
```

Candidate contract:

```text
retain only the review whose databaseId equals the webhook review ID
keep strict same-time rejection for every other review
exclude any review edited strictly after the trigger
retain inline comments
avoid duplicating the review body already supplied by the webhook
```

The generated patch is tested with the repository's Bun unit tests, typecheck,
and format check.

## Greg Brockman / `gdb/tee-output#3`

Target revision:

```text
gdb/tee-output
c41f8ff383200320b746e953e92709ae1b505a71
```

Problem boundary:

```text
write end closes
  -> SIGINT is sent immediately to parent-lifetime
  -> underlying tee may be interrupted before startup/tail drain completes
```

Candidate contract:

```text
flush Python streams
close writer and deliver EOF
wait for natural reader completion
use SIGINT only as a bounded fallback
```

The generated patch adds a PTY regression test for:

```text
print -> traceback -> immediate Tee.close()
```

and runs it on Linux and macOS.

## Authority boundary

These are contributor-ready candidates, not claims that upstream has accepted a
root cause or fix. No upstream branch, issue state, label, review, or merge is
modified by this repository. An external PR requires a GitHub fork owned by the
user.