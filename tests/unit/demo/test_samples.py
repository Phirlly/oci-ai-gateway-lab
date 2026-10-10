"""Bundled samples separate expected answers from identical bounded requests."""

import unittest

from demo.samples import load_samples, request_body


class SampleTests(unittest.TestCase):
    def test_three_synthetic_cases_have_distinct_categories(self):
        samples = load_samples()
        self.assertEqual(len(samples), 3)
        self.assertEqual({row.expected for row in samples}, {"BILLING", "ACCESS", "TECHNICAL"})

    def test_provider_requests_differ_only_by_model_alias(self):
        sample = load_samples()[0]
        first, second = request_body(sample, "oci-managed"), request_body(sample, "external-anthropic")
        first.pop("model")
        second.pop("model")
        self.assertEqual(first, second)
        self.assertEqual(first["max_tokens"], 32)
        self.assertEqual(set(first), {"messages", "max_tokens"})
        self.assertEqual(first["messages"][1]["content"], sample.text)

    def test_stream_uses_the_same_request_with_usage_opt_in(self):
        sample = load_samples()[0]
        regular = request_body(sample, "oci-managed")
        streamed = request_body(sample, "oci-managed", stream=True)
        self.assertEqual(streamed, {**regular, "stream": True, "stream_options": {"include_usage": True}})
