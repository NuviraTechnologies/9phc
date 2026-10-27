#!/usr/bin/env python3
"""Standalone Meta Model API helper for server deployments of 9 PHC.

Same command-line contract as the connector helper the engine was
built against:

  meta_api_server.py complete --model <id> --system-file <path>
      --user-file <path> [--schema-file <path>]

Prints the API's response body as JSON to stdout (the engine reads
choices[0].message.content and usage from it). The API key comes from
the META_API_KEY environment variable — on the stage server it is
supplied by the service's protected EnvironmentFile, never written
into this file, the repository, or any log.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://api.meta.ai/v1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("complete")
    c.add_argument("--model", required=True)
    c.add_argument("--system", default=None)
    c.add_argument("--user", default=None)
    c.add_argument("--system-file", default=None)
    c.add_argument("--user-file", default=None)
    c.add_argument("--schema", default=None)
    c.add_argument("--schema-file", default=None)
    c.add_argument("--max-tokens", type=int, default=None)
    args = ap.parse_args()

    key = os.environ.get("META_API_KEY", "")
    if not key:
        print("META_API_KEY is not set in the environment", file=sys.stderr)
        return 2

    system = args.system
    if args.system_file:
        system = open(args.system_file).read()
    user = args.user
    if args.user_file:
        user = open(args.user_file).read()
    schema = None
    if args.schema:
        schema = json.loads(args.schema)
    if args.schema_file:
        schema = json.loads(open(args.schema_file).read())

    payload: dict = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system or ""},
            {"role": "user", "content": user or ""},
        ],
    }
    if schema:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": schema}
    if args.max_tokens:
        payload["max_tokens"] = args.max_tokens

    req = urllib.request.Request(
        f"{BASE}/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(
                req, timeout=280) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:2000]
        print(f"HTTP {e.code} from /chat/completions: {body}",
              file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
