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

Observed lifecycle boundary:

```text
process spawned is not reader ready
reader ready is not output drained
closing a PTY master can discard an unread tail
```

The first shutdown-only candidate failed on all four OS/Python coordinates. A
READY-only bundled relay then passed most runs but still produced an intermittent
empty stdout log on macOS. The final candidate therefore uses two ordered
acknowledgements:

```text
open every output target
  -> READY acknowledgement
  -> permit normal writes
  -> flush Python streams
  -> append a random sentinel to the same PTY/pipe byte stream
  -> relay persists every byte before the sentinel
  -> relay removes the sentinel from user-visible output
  -> DRAIN acknowledgement on a separate status pipe
  -> restore descriptors and close the writer
  -> wait for natural process completion
  -> use SIGINT only as a bounded fallback
```

Because the drain sentinel follows user bytes in the same stream, the
acknowledgement establishes ordering rather than relying on a sleep, file
existence, or process liveness.

The generated patch adds a PTY regression test for:

```text
print -> traceback -> immediate Tee.close()
```

Validation matrix:

```text
Linux + macOS
Python 3.11 + 3.13
25 rounds per coordinate
100 total immediate-close trajectories
```

## Authority boundary

These are contributor-ready candidates, not claims that upstream has accepted a
root cause or fix. No upstream branch, issue state, label, review, or merge is
modified by this repository. An external PR requires a GitHub fork owned by the
user.