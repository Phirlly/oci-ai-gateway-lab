"""Finite synthetic OpenAI-compatible and Anthropic responses; no external calls."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

COUNTS = {"oci": 0, "anthropic": 0}


def openai_response(answer, stream):
    usage = {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}
    base = {"id": "chatcmpl-synthetic", "model": "synthetic-oci", "created": 1}
    if not stream:
        return {**base, "object": "chat.completion", "usage": usage,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}]}
    chunk = {**base, "object": "chat.completion.chunk"}
    return [
        {**chunk, "choices": [{"index": 0, "delta": {"role": "assistant", "content": answer}, "finish_reason": None}]},
        {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {**chunk, "choices": [], "usage": usage}, "[DONE]",
    ]


def anthropic_response(answer, stream):
    message = {"id": "msg_synthetic", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
               "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn", "stop_sequence": None,
               "usage": {"input_tokens": 20, "output_tokens": 3}}
    if not stream:
        return message
    return [
        {"type": "message_start", "message": {**message, "content": [], "stop_reason": None,
                                               "usage": {"input_tokens": 20, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": answer}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 3}},
        {"type": "message_stop"},
    ]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, value, status=200, headers=None):
        content = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path == "/stats":
            self.send(COUNTS)
        elif self.path == "/ready":
            self.send({"ready": True})
        else:
            self.send({}, 404)

    def do_POST(self):
        providers = {"/oci/20231130/actions/v1/chat/completions": "oci", "/anthropic/v1/messages": "anthropic"}
        provider = providers.get(self.path)
        if provider is None:
            return self.send({"error": "unexpected fixture endpoint"}, 404)
        COUNTS[provider] += 1
        authorized = (self.headers.get("Authorization") == "Bearer synthetic-unused" if provider == "oci"
                      else self.headers.get("x-api-key") == "synthetic-unused" and self.headers.get("anthropic-version") == "2023-06-01")
        if not authorized:
            return self.send({"error": "fixture authorization failed"}, 401)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError
            value = json.loads(self.rfile.read(length))
            expected_model = "synthetic-oci" if provider == "oci" else "claude-sonnet-4-6"
            if value["model"] != expected_model or value["max_tokens"] != 32:
                raise ValueError
            text = value["messages"][-1]["content"]
            if isinstance(text, list):
                text = "".join(block["text"] for block in text if block["type"] == "text")
            if not isinstance(text, str):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self.send({"error": "invalid fixture request"}, 400)
        if "fixture-rate-limit" in text:
            return self.send({"type": "error", "error": {"type": "rate_limit_error", "message": "synthetic rate limit"}},
                             429, {'Retry-After': '7'})
        answer = "BILLING" if "invoice" in text else "ACCESS" if "locked" in text else "TECHNICAL"
        stream = value.get("stream", False)
        output = (openai_response if provider == "oci" else anthropic_response)(answer, stream)
        if not stream:
            return self.send(output)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for item in output:
            if provider == "anthropic":
                self.wfile.write(("event: " + item["type"] + "\n").encode())
            data = item if isinstance(item, str) else json.dumps(item)
            self.wfile.write(("data: " + data + "\n\n").encode())
            self.wfile.flush()


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
