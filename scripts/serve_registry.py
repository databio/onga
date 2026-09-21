#!/usr/bin/env python3
"""Serve the generated registry API tree for the compliance suite.

The GA4GH Schema Registry compliance checks request extensionless resource
paths (/namespaces, /schemas/databio, ...). On the static tree those resources
live at <path>/index.json, so this tiny stdlib server rewrites extensionless
GET paths accordingly (mirroring what the production static host's index
resolution does). Used only by `make test-registry`.
"""

import argparse
import functools
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler


class RegistryHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Drop the query string (a static tree cannot filter; the compliance
        # suite's filter checks are expected to fail against it).
        path = path.split("?", 1)[0]
        translated = super().translate_path(path)
        # A directory resource resolves to its index.json (extension sniffing
        # is not enough: version segments like /versions/0.1.0 look like they
        # have a ".0" extension).
        if os.path.isdir(translated):
            return os.path.join(translated, "index.json")
        return translated

    def log_message(self, fmt, *args):  # keep make output readable
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--port", type=int, default=8917)
    ap.add_argument("--pid", help="write the server pid to this file")
    args = ap.parse_args()

    if args.pid:
        with open(args.pid, "w") as f:
            f.write(str(os.getpid()))

    handler = functools.partial(RegistryHandler, directory=args.root)
    HTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
