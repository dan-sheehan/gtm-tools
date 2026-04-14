#!/usr/bin/env python3
"""Reverse proxy gateway for GTM tools.

Routes requests by path prefix to backend app servers:
    /brief/*            -> localhost:3003
    /playbook/*         -> localhost:3004
    /discovery/*        -> localhost:3005
    /competitive-intel/* -> localhost:3006
    /prompt-builder/*   -> localhost:3007
    /outbound-email/*   -> localhost:3008
    /gtm-trends/*       -> localhost:3009
    /pipeline/*         -> localhost:3010
    /enrichment/*       -> localhost:3011
    /icp-scorer/*       -> localhost:3012
    /                   -> hub page
"""
import argparse
import http.server
import urllib.request
import urllib.error

DEFAULT_PORT = 8000

ROUTES = {
    "/brief":            ("127.0.0.1", 3003),
    "/playbook":         ("127.0.0.1", 3004),
    "/discovery":        ("127.0.0.1", 3005),
    "/competitive-intel": ("127.0.0.1", 3006),
    "/prompt-builder":   ("127.0.0.1", 3007),
    "/outbound-email":   ("127.0.0.1", 3008),
    "/gtm-trends":       ("127.0.0.1", 3009),
    "/pipeline":         ("127.0.0.1", 3010),
    "/enrichment":       ("127.0.0.1", 3011),
    "/icp-scorer":       ("127.0.0.1", 3012),
}

HUB_PAGE = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GTM Tools</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #1a1a1a; color: #e0e0e0; min-height: 100vh;
    }
    .hub {
      max-width: 1080px; width: 100%; margin: 0 auto;
      padding: 60px 32px;
    }
    header {
      margin-bottom: 48px;
    }
    h1 {
      font-size: 32px; font-weight: 600; color: #fff;
      margin-bottom: 6px; letter-spacing: -0.5px;
    }
    .subtitle { color: #888; font-size: 15px; }
    .section { margin-bottom: 48px; }
    .section-header { margin-bottom: 20px; }
    .section-title {
      font-size: 20px; font-weight: 600; color: #ccc;
      margin-bottom: 4px; letter-spacing: -0.3px;
    }
    .section-desc { color: #666; font-size: 14px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }
    @media (max-width: 820px) {
      .grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 520px) {
      .grid { grid-template-columns: 1fr; }
      .hub { padding: 40px 16px; }
    }
    a.card {
      display: flex; flex-direction: column;
      background: #242424; border-radius: 14px;
      text-decoration: none; color: #e0e0e0;
      overflow: hidden;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    a.card:hover {
      transform: translateY(-3px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }
    .card-header {
      height: 140px; display: flex;
      align-items: center; justify-content: center;
      position: relative; overflow: hidden;
    }
    .card-icon {
      width: 64px; height: 64px;
      display: flex; align-items: center; justify-content: center;
    }
    .card-icon svg {
      width: 56px; height: 56px;
      stroke: rgba(0,0,0,0.6); stroke-width: 1.5;
      fill: none; stroke-linecap: round; stroke-linejoin: round;
    }
    .card-body {
      padding: 20px 20px 18px;
      flex: 1; display: flex; flex-direction: column;
    }
    .card-title {
      font-weight: 600; font-size: 16px; color: #fff;
      line-height: 1.35; margin-bottom: 6px;
    }
    .card-desc {
      font-size: 13px; color: #999; line-height: 1.5;
      margin-bottom: 14px; flex: 1;
    }
    .card-tag {
      display: inline-flex; align-items: center; gap: 5px;
      font-size: 12px; color: #777;
      width: fit-content;
    }
    .card-tag svg {
      width: 14px; height: 14px; stroke: #777;
      fill: none; stroke-width: 1.5;
      stroke-linecap: round; stroke-linejoin: round;
    }

    /* Card header colors — tight palette, 4 tones rotated */
    .bg-sage      { background: #b5c4b1; }
    .bg-coral     { background: #d4a090; }
    .bg-sky       { background: #a3bdd4; }
    .bg-sand      { background: #c4bba8; }
  </style>
</head>
<body>
  <div class="hub">
    <header>
      <h1>GTM Tools</h1>
      <div class="subtitle">AI-powered sales &amp; GTM toolkit</div>
    </header>

    <!-- Section 1: Outbound Pipeline -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">Outbound Pipeline</h2>
        <p class="section-desc">Find, qualify, and reach target accounts.</p>
      </div>
      <div class="grid">

        <a class="card" href="/enrichment/">
          <div class="card-header bg-sage">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><circle cx="24" cy="14" r="8"/><path d="M8 40c0-8.84 7.16-16 16-16s16 7.16 16 16"/><line x1="36" y1="10" x2="42" y2="10"/><line x1="39" y1="7" x2="39" y2="13"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">Lead Enrichment</div>
            <div class="card-desc">Enrich leads with firmographic &amp; contact data</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
              Outbound
            </div>
          </div>
        </a>

        <a class="card" href="/icp-scorer/">
          <div class="card-header bg-coral">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="18"/><circle cx="24" cy="24" r="12"/><circle cx="24" cy="24" r="6"/><circle cx="24" cy="24" r="2" fill="rgba(0,0,0,0.6)"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">ICP Scorer</div>
            <div class="card-desc">Score leads against your Ideal Customer Profile</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              Scoring
            </div>
          </div>
        </a>

        <a class="card" href="/outbound-email/">
          <div class="card-header bg-sky">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><rect x="4" y="8" width="40" height="30" rx="4"/><polyline points="4 12 24 26 44 12"/><line x1="4" y1="38" x2="16" y2="26"/><line x1="44" y1="38" x2="32" y2="26"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">Outbound Email Helper</div>
            <div class="card-desc">AI-powered cold outreach email sequences</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
              Outbound
            </div>
          </div>
        </a>

        <a class="card" href="/brief/">
          <div class="card-header bg-sand">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="18"/><polyline points="24 14 24 24 32 28"/><circle cx="24" cy="24" r="2"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">GTM Signal Dashboard</div>
            <div class="card-desc">Daily GTM signals &mdash; pipeline alerts, competitive intel, account changes</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              Signals
            </div>
          </div>
        </a>

      </div>
    </div>

    <!-- Section 2: Sales Enablement -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">Sales Enablement</h2>
        <p class="section-desc">Prepare reps to win deals.</p>
      </div>
      <div class="grid">

        <a class="card" href="/discovery/">
          <div class="card-header bg-sage">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><circle cx="20" cy="20" r="14"/><line x1="30" y1="30" x2="42" y2="42"/><circle cx="20" cy="20" r="6" stroke-dasharray="3 3"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">Discovery Call Prep</div>
            <div class="card-desc">Research companies &amp; prospects before calls</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
              Sales
            </div>
          </div>
        </a>

        <a class="card" href="/competitive-intel/">
          <div class="card-header bg-sand">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><rect x="4" y="24" width="8" height="18" rx="2"/><rect x="16" y="16" width="8" height="26" rx="2"/><rect x="28" y="8" width="8" height="34" rx="2"/><polyline points="6 12 18 6 30 10 42 4"/><circle cx="42" cy="4" r="2"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">Competitive Intelligence</div>
            <div class="card-desc">Research competitors &amp; build strategic intel</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
              Strategy
            </div>
          </div>
        </a>

        <a class="card" href="/playbook/">
          <div class="card-header bg-coral">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><path d="M8 6h28a4 4 0 014 4v28a4 4 0 01-4 4H12a4 4 0 01-4-4V6z"/><path d="M16 6v36"/><line x1="24" y1="16" x2="32" y2="16"/><line x1="24" y1="24" x2="32" y2="24"/><line x1="24" y1="32" x2="28" y2="32"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">Onboarding Playbook</div>
            <div class="card-desc">AI-powered onboarding playbook generator</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
              CS
            </div>
          </div>
        </a>

        <a class="card" href="/prompt-builder/">
          <div class="card-header bg-sky">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><rect x="6" y="4" width="36" height="40" rx="4"/><line x1="14" y1="14" x2="34" y2="14"/><line x1="14" y1="22" x2="34" y2="22"/><line x1="14" y1="30" x2="26" y2="30"/><circle cx="34" cy="34" r="6"/><line x1="34" y1="30" x2="34" y2="38"/><line x1="30" y1="34" x2="38" y2="34"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">Prompt Builder</div>
            <div class="card-desc">Generate meeting memory prompts for clients</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              AI
            </div>
          </div>
        </a>

      </div>
    </div>

    <!-- Section 3: Infrastructure -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">Infrastructure</h2>
        <p class="section-desc">Track pipeline and market trends.</p>
      </div>
      <div class="grid">

        <a class="card" href="/pipeline/">
          <div class="card-header bg-sky">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><path d="M6 8h36v8H6z"/><path d="M10 16h28v8H10z"/><path d="M14 24h20v8H14z"/><path d="M18 32h12v8H18z"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">Pipeline Dashboard</div>
            <div class="card-desc">Track deals, stages, and pipeline health metrics</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              Pipeline
            </div>
          </div>
        </a>

        <a class="card" href="/gtm-trends/">
          <div class="card-header bg-coral">
            <div class="card-icon">
              <svg viewBox="0 0 48 48"><rect x="4" y="28" width="8" height="14" rx="2"/><rect x="14" y="20" width="8" height="22" rx="2"/><rect x="24" y="12" width="8" height="30" rx="2"/><rect x="34" y="6" width="8" height="36" rx="2"/><polyline points="6 10 18 6 28 8 42 4"/></svg>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">GTM Trends</div>
            <div class="card-desc">Spot tool &amp; skill patterns across GTM Engineering job postings</div>
            <div class="card-tag">
              <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
              Research
            </div>
          </div>
        </a>

      </div>
    </div>

  </div>
</body>
</html>
"""


class GatewayHandler(http.server.BaseHTTPRequestHandler):
    """Proxy handler that routes by path prefix."""

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def _proxy(self):
        # Serve hub page at root
        if self.path == "/" or self.path == "":
            self._serve_hub()
            return

        # Find matching route
        for prefix, (host, port) in ROUTES.items():
            if self.path == prefix or self.path.startswith(prefix + "/"):
                # Redirect /prefix to /prefix/ for relative path resolution
                if self.path == prefix:
                    self.send_response(301)
                    self.send_header("Location", prefix + "/")
                    self.end_headers()
                    return

                # Forward full path — backends register routes with prefix
                self._forward(host, port, self.path)
                return

        # No route matched
        self.send_error(404, "Not Found")

    def _serve_hub(self):
        body = HUB_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _forward(self, host, port, path):
        url = f"http://{host}:{port}{path}"

        # Read request body if present
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Build forwarded request
        req = urllib.request.Request(url, data=body, method=self.command)

        # Forward relevant headers
        for header in ("Content-Type", "Accept", "Accept-Encoding",
                       "Accept-Language", "Cookie", "Authorization"):
            value = self.headers.get(header)
            if value:
                req.add_header(header, value)

        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                self.send_response(status)

                # Forward response headers
                for key, value in resp.getheaders():
                    lower = key.lower()
                    if lower in ("transfer-encoding", "connection"):
                        continue
                    self.send_header(key, value)
                self.end_headers()

                # Stream response body
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, value in e.headers.items():
                lower = key.lower()
                if lower in ("transfer-encoding", "connection"):
                    continue
                self.send_header(key, value)
            self.end_headers()
            body = e.read()
            if body:
                self.wfile.write(body)

        except urllib.error.URLError:
            body = f"Backend unavailable at {host}:{port}. Is the app running?".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        # Quieter logging: just method + path + status
        pass


def command_serve(args):
    port = args.port or DEFAULT_PORT
    server = http.server.HTTPServer(("127.0.0.1", port), GatewayHandler)
    print(f"Gateway running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return 0


def main():
    parser = argparse.ArgumentParser(prog="gateway")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=None)

    args = parser.parse_args()

    if args.command == "serve":
        return command_serve(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
