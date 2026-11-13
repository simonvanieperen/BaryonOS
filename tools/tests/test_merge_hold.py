"""Unit tests for the merge-hold decision; no network access."""

import contextlib
import io
import os
import sys
from pathlib import Path
from unittest import TestCase, main, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import merge_hold

HEAD = "a" * 40
OTHER = "b" * 40
ENV = {"GH_TOKEN": "x", "REPO": "o/r", "PR_NUMBER": "7", "HEAD_SHA": HEAD}


def comment(body, association="MEMBER"):
    return {"body": body, "author_association": association}


class DecisionTests(TestCase):
    def test_no_label_passes(self):
        self.assertTrue(merge_hold.decide(["bug"], [], HEAD)[0])

    def test_label_without_release_fails(self):
        self.assertFalse(merge_hold.decide([merge_hold.LABEL], [], HEAD)[0])

    def test_release_for_the_current_head_passes(self):
        for association in ("OWNER", "MEMBER", "COLLABORATOR"):
            with self.subTest(association=association):
                passed, _ = merge_hold.decide(
                    [merge_hold.LABEL],
                    [comment("Matrix green.\r\nacceptance-released: " + HEAD + "\n", association)],
                    HEAD)
                self.assertTrue(passed)

    def test_release_for_another_head_does_not_carry_over(self):
        comments = [comment("acceptance-released: " + OTHER)]
        self.assertFalse(merge_hold.decide([merge_hold.LABEL], comments, HEAD)[0])

    def test_untrusted_or_inexact_release_is_ignored(self):
        for body, association in (
            ("acceptance-released: " + HEAD, "CONTRIBUTOR"),
            ("acceptance-released: " + HEAD, "NONE"),
            ("acceptance-released: " + HEAD[:12], "MEMBER"),
            ("not acceptance-released: " + HEAD, "MEMBER"),
            ("acceptance-released: " + HEAD.upper(), "MEMBER"),
        ):
            with self.subTest(body=body, association=association):
                self.assertFalse(merge_hold.decide(
                    [merge_hold.LABEL], [comment(body, association)], HEAD)[0])

    def test_malformed_head_fails_closed(self):
        for head in ("", "abc", None, "g" * 40):
            with self.subTest(head=head):
                self.assertFalse(merge_hold.decide([], [], head)[0])


class MainTests(TestCase):
    def run_main(self, env, fetch):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(merge_hold, "fetch_all", fetch), \
                contextlib.redirect_stdout(out):
            return merge_hold.main(), out.getvalue()

    def test_reads_live_labels_and_comments(self):
        calls = []

        def fetch(token, url):
            calls.append(url)
            if url.endswith("/labels"):
                return [{"name": merge_hold.LABEL}]
            return [comment("acceptance-released: " + HEAD)]

        code, out = self.run_main(ENV, fetch)
        self.assertEqual(code, 0, out)
        self.assertEqual(calls, ["https://api.github.com/repos/o/r/issues/7/labels",
                                 "https://api.github.com/repos/o/r/issues/7/comments"])

    def test_pending_label_fails(self):
        def fetch(token, url):
            return [{"name": merge_hold.LABEL}] if url.endswith("/labels") else []

        code, out = self.run_main(ENV, fetch)
        self.assertEqual(code, 1)
        self.assertIn("::error::", out)

    def test_api_failure_and_missing_input_fail_closed(self):
        def broken(token, url):
            raise OSError("HTTP 502")

        self.assertEqual(self.run_main(ENV, broken)[0], 1)
        env = dict(ENV)
        del env["GH_TOKEN"]
        self.assertEqual(self.run_main(env, lambda t, u: [])[0], 1)
        env = dict(ENV, PR_NUMBER="seven")
        self.assertEqual(self.run_main(env, lambda t, u: [])[0], 1)

    def test_unexpected_payload_fails_closed(self):
        def odd(token, url):
            raise TypeError("Unexpected API response")

        self.assertEqual(self.run_main(ENV, odd)[0], 1)


class FetchTests(TestCase):
    @staticmethod
    def pages(*bodies):
        responses = [io.BytesIO(body.encode()) for body in bodies]
        calls = []

        def urlopen(req, timeout):
            calls.append(req.full_url)
            return contextlib.nullcontext(responses[len(calls) - 1])
        return urlopen, calls

    def test_reads_every_page(self):
        full = "[" + ",".join(['{"name": "x"}'] * 100) + "]"
        urlopen, calls = self.pages(full, '[{"name": "last"}]')
        with mock.patch.object(merge_hold.request, "urlopen", urlopen):
            items = merge_hold.fetch_all("t", "https://api.example/x")
        self.assertEqual(len(items), 101)
        self.assertEqual(items[-1], {"name": "last"})
        self.assertEqual(calls, ["https://api.example/x?per_page=100&page=1",
                                 "https://api.example/x?per_page=100&page=2"])

    def test_non_list_payload_is_rejected(self):
        urlopen, _ = self.pages('{"message": "Not Found"}')
        with mock.patch.object(merge_hold.request, "urlopen", urlopen), \
                self.assertRaises(TypeError):
            merge_hold.fetch_all("t", "https://api.example/x")

    def test_page_limit_is_enforced(self):
        full = "[" + ",".join(["{}"] * 100) + "]"
        urlopen, _ = self.pages(*([full] * (merge_hold.MAX_PAGES + 1)))
        with mock.patch.object(merge_hold.request, "urlopen", urlopen), \
                self.assertRaises(ValueError):
            merge_hold.fetch_all("t", "https://api.example/x")


if __name__ == "__main__":
    main()
