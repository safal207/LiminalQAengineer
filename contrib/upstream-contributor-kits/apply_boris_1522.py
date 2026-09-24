#!/usr/bin/env python3
# Apply the bounded fix for anthropics/claude-code-action#1522.
# Every replacement must match once against the pinned upstream revision.

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one source match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--patch-out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()

    fetcher = repo / "src/github/data/fetcher.ts"
    tag = repo / "src/modes/tag/index.ts"
    tests = repo / "test/data-fetcher.test.ts"

    replace_once(
        fetcher,
        '''  return undefined;
}

/**
 * Extracts the original title from the GitHub webhook payload.
''',
        '''  return undefined;
}

/**
 * Returns the database ID of the review that triggered a
 * pull_request_review event.
 *
 * The ID lets the trigger-time filter retain exactly the webhook entity while
 * continuing to reject unrelated reviews submitted at the same timestamp.
 */
export function extractTriggerReviewDatabaseId(
  context: ParsedGitHubContext,
): string | undefined {
  return isPullRequestReviewEvent(context)
    ? context.payload.review.id.toString()
    : undefined;
}

/**
 * Extracts the original title from the GitHub webhook payload.
''',
    )

    replace_once(
        fetcher,
        '''export function filterReviewsToTriggerTime<
  T extends { submittedAt: string; updatedAt?: string; lastEditedAt?: string },
>(reviews: T[], triggerTime: string | undefined): T[] {
  if (!triggerTime) return reviews;

  const triggerTimestamp = new Date(triggerTime).getTime();

  return reviews.filter((review) => {
    // Review must have been submitted before trigger (not at or after)
    const submittedTimestamp = new Date(review.submittedAt).getTime();
    if (submittedTimestamp >= triggerTimestamp) {
      return false;
    }

    // If review has been edited, the most recent edit must have occurred before trigger
    const lastEditTime = review.lastEditedAt || review.updatedAt;
    if (lastEditTime) {
      const lastEditTimestamp = new Date(lastEditTime).getTime();
      if (lastEditTimestamp >= triggerTimestamp) {
        return false;
      }
    }

    return true;
  });
}
''',
        '''export function filterReviewsToTriggerTime<
  T extends {
    databaseId?: string;
    submittedAt: string;
    updatedAt?: string;
    lastEditedAt?: string;
  },
>(
  reviews: T[],
  triggerTime: string | undefined,
  triggerReviewDatabaseId?: string,
): T[] {
  if (!triggerTime) return reviews;

  const triggerTimestamp = new Date(triggerTime).getTime();

  return reviews.filter((review) => {
    const isTriggerReview =
      triggerReviewDatabaseId !== undefined &&
      review.databaseId === triggerReviewDatabaseId;

    // Reviews after the trigger are unsafe. Reviews exactly at the trigger are
    // only safe when their database ID matches the webhook entity.
    const submittedTimestamp = new Date(review.submittedAt).getTime();
    if (
      submittedTimestamp > triggerTimestamp ||
      (submittedTimestamp === triggerTimestamp && !isTriggerReview)
    ) {
      return false;
    }

    // Preserve the exact triggering review if GitHub reports its update time as
    // the submission time. Any edit strictly after the trigger remains unsafe.
    const lastEditTime = review.lastEditedAt || review.updatedAt;
    if (lastEditTime) {
      const lastEditTimestamp = new Date(lastEditTime).getTime();
      if (
        lastEditTimestamp > triggerTimestamp ||
        (lastEditTimestamp === triggerTimestamp && !isTriggerReview)
      ) {
        return false;
      }
    }

    return true;
  });
}
''',
    )

    replace_once(
        fetcher,
        '''  triggerUsername?: string;
  triggerTime?: string;
  originalTitle?: string;
''',
        '''  triggerUsername?: string;
  triggerTime?: string;
  triggerReviewDatabaseId?: string;
  originalTitle?: string;
''',
    )

    replace_once(
        fetcher,
        '''  triggerUsername,
  triggerTime,
  originalTitle,
''',
        '''  triggerUsername,
  triggerTime,
  triggerReviewDatabaseId,
  originalTitle,
''',
    )

    replace_once(
        fetcher,
        '''    reviewData.nodes = filterCommentsByActor(
      filterReviewsToTriggerTime(reviewData.nodes, triggerTime),
      includeCommentsByActor,
      excludeCommentsByActor,
    );

    // Apply the same trigger-time + actor filtering to inline review comments.
''',
        '''    reviewData.nodes = filterCommentsByActor(
      filterReviewsToTriggerTime(
        reviewData.nodes,
        triggerTime,
        triggerReviewDatabaseId,
      ),
      includeCommentsByActor,
      excludeCommentsByActor,
    );

    // The webhook payload already provides the triggering review body through
    // trigger_comment. Keep the review node for its inline comments and state,
    // but avoid duplicating the body in <review_comments>.
    reviewData.nodes = reviewData.nodes.map((review) =>
      review.databaseId === triggerReviewDatabaseId
        ? { ...review, body: "" }
        : review,
    );

    // Apply the same trigger-time + actor filtering to inline review comments.
''',
    )

    replace_once(
        tag,
        '''  extractTriggerTimestamp,
  extractOriginalTitle,
  extractOriginalBody,
''',
        '''  extractTriggerTimestamp,
  extractTriggerReviewDatabaseId,
  extractOriginalTitle,
  extractOriginalBody,
''',
    )
    replace_once(
        tag,
        '''  const triggerTime = extractTriggerTimestamp(context);
  const originalTitle = extractOriginalTitle(context);
''',
        '''  const triggerTime = extractTriggerTimestamp(context);
  const triggerReviewDatabaseId = extractTriggerReviewDatabaseId(context);
  const originalTitle = extractOriginalTitle(context);
''',
    )
    replace_once(
        tag,
        '''    triggerUsername: context.actor,
    triggerTime,
    originalTitle,
''',
        '''    triggerUsername: context.actor,
    triggerTime,
    triggerReviewDatabaseId,
    originalTitle,
''',
    )

    replace_once(
        tests,
        '''  extractTriggerTimestamp,
  extractOriginalTitle,
''',
        '''  extractTriggerTimestamp,
  extractTriggerReviewDatabaseId,
  extractOriginalTitle,
''',
    )
    replace_once(
        tests,
        '''describe("extractOriginalTitle", () => {
''',
        '''describe("extractTriggerReviewDatabaseId", () => {
  it("should extract the triggering review database ID", () => {
    expect(extractTriggerReviewDatabaseId(mockPullRequestReviewContext)).toBe(
      "11122233",
    );
  });

  it("should return undefined for non-review events", () => {
    expect(extractTriggerReviewDatabaseId(mockIssueCommentContext)).toBeUndefined();
    expect(
      extractTriggerReviewDatabaseId(mockPullRequestReviewCommentContext),
    ).toBeUndefined();
  });
});

describe("extractOriginalTitle", () => {
''',
    )
    replace_once(
        tests,
        '''  const createMockReview = (
    submittedAt: string,
    updatedAt?: string,
    lastEditedAt?: string,
  ): GitHubReview => ({
    id: String(Math.random()),
    databaseId: String(Math.random()),
''',
        '''  const createMockReview = (
    submittedAt: string,
    updatedAt?: string,
    lastEditedAt?: string,
    databaseId: string = String(Math.random()),
  ): GitHubReview => ({
    id: String(Math.random()),
    databaseId,
''',
    )
    replace_once(
        tests,
        '''    it("should handle exact timestamp match", () => {
      const review = createMockReview("2024-01-15T12:00:00Z");
      const filtered = filterReviewsToTriggerTime([review], triggerTime);
      // Reviews submitted exactly at trigger time should be excluded for security
      expect(filtered.length).toBe(0);
    });
''',
        '''    it("should exclude an unrelated review at the exact trigger timestamp", () => {
      const review = createMockReview("2024-01-15T12:00:00Z");
      const filtered = filterReviewsToTriggerTime(
        [review],
        triggerTime,
        "trigger-review-id",
      );
      expect(filtered.length).toBe(0);
    });

    it("should include the exact triggering review at the trigger timestamp", () => {
      const review = createMockReview(
        "2024-01-15T12:00:00Z",
        undefined,
        undefined,
        "trigger-review-id",
      );
      const filtered = filterReviewsToTriggerTime(
        [review],
        triggerTime,
        "trigger-review-id",
      );
      expect(filtered).toEqual([review]);
    });

    it("should include the triggering review when updatedAt equals submission time", () => {
      const review = createMockReview(
        "2024-01-15T12:00:00Z",
        "2024-01-15T12:00:00Z",
        undefined,
        "trigger-review-id",
      );
      const filtered = filterReviewsToTriggerTime(
        [review],
        triggerTime,
        "trigger-review-id",
      );
      expect(filtered).toEqual([review]);
    });

    it("should still exclude the triggering review if it was edited after the trigger", () => {
      const review = createMockReview(
        "2024-01-15T12:00:00Z",
        "2024-01-15T12:00:01Z",
        undefined,
        "trigger-review-id",
      );
      const filtered = filterReviewsToTriggerTime(
        [review],
        triggerTime,
        "trigger-review-id",
      );
      expect(filtered.length).toBe(0);
    });
''',
    )

    subprocess.run(["git", "-C", str(repo), "diff", "--check"], check=True)
    args.patch_out.parent.mkdir(parents=True, exist_ok=True)
    patch = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary"])
    args.patch_out.write_bytes(patch)


if __name__ == "__main__":
    main()
