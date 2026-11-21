# aria-dl

A download queue for people and for AI agents.

One single-file command runs torrents, magnet links, HTTP(S) files, and video or audio pages (YouTube and other sites through `yt-dlp`). In a terminal you get a one-line status. An agent gets one JSON document on stdout, documented exit codes, `status --wait`, and a function-calling schema (`aria-dl tools`). No extra Python packages.

Supports **`.torrent` files, magnet links, HTTP(S)/FTP URLs, and video sites** (YouTube, Bilibili, X/Twitter, Vimeo, Niconico, TikTok, Instagram, SoundCloud, and others), with batch input, a concurrency queue, automatic resume, retries, and optional **night-only + Wi-Fi-only** scheduling.

## Features

- **Unified interface**: one command for torrents, magnets, direct URLs (`aria2c`), and video/audio pages (`yt-dlp`).
- **Batch & queue**: pass multiple sources on the command line, load from a file (`-f urls.txt`), or pipe via stdin (`pbpaste | aria-dl add`). Runs up to 2 media jobs + 3 aria2 jobs concurrently by default and auto-starts the next queued job immediately when a slot frees.
- **Night + Wi-Fi scheduling (`--when night`)**: downloads only between `22:00–08:00` local time when the default network route is Wi-Fi, automatically pausing outside that window and resuming later.
- **Resumable & non-destructive**: passes `--continue` to both `aria2c` and `yt-dlp`; `aria-dl remove` deletes only the job record, never downloaded files.
- **Automatic retries**: `yt-dlp` retries transient network errors in-process. If a download process still fails, the job waits out a backoff (2m, 5m, 15m, 30m, 60m) and tries again, up to `--retries` (default 5), then stops.
- **Agent-friendly**: `--json` or `ARIA_DL_JSON=1` prints one stable JSON value on stdout (job id, url, kind, state, progress, bytes, paths, last error, hint). Logs stay on stderr. `aria-dl tools` prints a function-calling schema. `status ID --wait` blocks until the job finishes.
- **Single-file stdlib Python 3**: no pip dependencies required. jq is optional and is not used to produce JSON.

## Use with AI agents

Humans and agents use the same `aria-dl` binary and the same LaunchAgent install. Pass `--json` (or export `ARIA_DL_JSON=1`) on every call you intend to parse. `--yes` / `--non-interactive` are accepted; the CLI does not prompt, and a non-TTY stdin does not prompt either.

```bash
aria-dl add 'https://example.com/file.zip' --json --non-interactive
aria-dl status JOBID --wait --timeout 600 --json
aria-dl list --json
aria-dl config get youtube_proxy --json
aria-dl cookies status --json
aria-dl version --json
aria-dl tools --json    # paste into a tool registry
aria-dl schema          # result shapes and exit codes
```

`list` is always a JSON array. One id is a JSON object; several ids, `--file`, or several sources are an array. Parse the whole stdout with a JSON parser. Output is pretty-printed, not JSON Lines. Progress during `--wait` is on stderr.

A job object includes `id`, `url`, `source`, `kind`, `state`, `progress`, `bytes`, `output_paths`, `dir`, `last_error`, and `hint`. `add` also reports `existed` and `action` (`created`, `requeued`, or `exists`). The same URL is the same id (`sha1` prefix); adding it again does not create a second job. A running or complete job is left unchanged.

`status ID` without `--wait` exits 0 when the id exists, including when that job has failed. Use `--wait` when the exit code should be the download result. `--timeout 0` checks once. Omit `--timeout` to wait until complete, failed, or removed. Retries and the night window are not terminal, so pass a timeout.

| Exit | Meaning |
| --- | --- |
| 0 | Success. A plain `status` of an existing id is success even if the job failed. |
| 1 | A source was rejected, a batch was partial, or `--wait` ended failed. |
| 2 | Usage error. |
| 3 | No unique job for that id. |
| 4 | `--wait` ended with a YouTube bot-check or a network error. |
| 5 | `aria2c` or `yt-dlp` is missing. The job is kept; install the tool and `resume` the id. |
| 6 | `--wait` timed out. The job is still in progress. |
| 130 | Interrupted. |

On exit 4 with `last_error` `youtube_bot_check`, ask the user to run `aria-dl cookies refresh` in a terminal, or set a yt-dlp proxy. Do not invent cookie values.

Register the CLI as tools with the JSON from `aria-dl tools`. Copy `name`, `description`, and `parameters` for OpenAI-style function calling. `input_schema` is the same object for Anthropic. A short `status` tool looks like:

```json
{
  "name": "status",
  "description": "Show jobs. Add wait to block until complete or failed and use the process exit code.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "required": ["ids"],
    "properties": {
      "ids": {"type": "array", "items": {"type": "string"}},
      "wait": {"type": "boolean"},
      "timeout": {"type": "number", "minimum": 0}
    }
  }
}
```

`examples/mcp_server.py` is an optional stdlib MCP stdio server (`python3 examples/mcp_server.py`). `install.sh` does not install it. `AGENTS.md` is the short reference to give an agent.

Example instruction to an agent:

```text
Drive aria-dl with --json and --non-interactive. Parse stdout only.
Add the URL the user named, then `aria-dl status ID --wait --timeout 600 --json`.
Exit 0 means the file is complete. Exit 4 means a YouTube bot-check or a network error:
tell the user to run `aria-dl cookies refresh` in a terminal, or to set youtube_proxy.
Exit 5 means aria2c or yt-dlp is not installed. Exit 6 means the wait timed out; report the state.
Never print or invent cookies. Proxy fields are host:port only.
```

Safety:

- JSON never includes cookie values or proxy usernames and passwords. Proxy fields are `host:port`.
- The proxy is passed only to `yt-dlp`. It does not set `HTTP_PROXY`, `HTTPS_PROXY`, or the system proxy. If that port is closed, the attempt goes direct and the log says `proxy unreachable, falling back to direct`.
- URL userinfo is removed in JSON. Query strings are kept, so do not put tokens in the URL you add.
- The cookie file stays mode `0600` and is not printed. `cookies status` reports age, count, and whether a login cookie is present.
- `remove` deletes the job record only. Files already on disk stay.
- `ARIA_DL_HOME` points at an isolated queue. The default remains `~/.local/share/aria-dl`. Leave `ARIA_DL_JSON` unset in the LaunchAgent; `tick` is silent either way.

## Requirements

- Python 3.8+
- `aria2c` (for HTTP/FTP/BitTorrent)
- `yt-dlp` and `ffmpeg` (for video sites)

On macOS with Homebrew:

```bash
brew install aria2 yt-dlp ffmpeg
```

## Install

```bash
git clone https://github.com/DamoMind/aria-dl.git
cd aria-dl
./install.sh
```

`install.sh` installs `aria-dl` to `~/.local/bin/aria-dl` (symlinking to `/usr/local/bin/aria-dl` if writable) and, on macOS, registers a LaunchAgent (`com.damomind.aria-dl`) that runs `aria-dl tick` every 60 seconds as a safety net for night windows, retries, and reboots. A pending retry also schedules one delayed `tick` at its backoff deadline, so a short wait is not pushed out to the next periodic run. On macOS, `./install.sh --cookies` also runs `aria-dl cookies refresh` in the foreground at the end. `./install.sh --youtube-proxy http://127.0.0.1:2081` stores that URL for aria-dl's own YouTube downloads and does not change the system proxy.

## Usage

### Single download

```bash
aria-dl add ~/Downloads/example.torrent               # Start immediately
aria-dl add 'magnet:?xt=urn:btih:...'                 # Magnet link (quote it)
aria-dl add https://example.com/archive.zip           # Direct URL (8 connections)
aria-dl add https://www.youtube.com/watch?v=...       # Video via yt-dlp (default <=1080p, mp4)
aria-dl add <video-url> --audio                       # Audio only (m4a)
aria-dl add <video-url> --max-height 720              # Cap resolution
aria-dl add <other-video-site-url> --media            # Force yt-dlp
aria-dl add <source> --when night                     # 22:00-08:00 & Wi-Fi only
aria-dl add <source> --retries 5                      # cross-process retries (default); 0 disables
aria-dl add <video-url> --cookies-from-browser chrome # browser cookies for yt-dlp
aria-dl add <source> --dir ~/Videos --limit 2M --name "My Job"
```

### Batch download (multiple tasks)

```bash
# Multiple positional arguments (can mix URLs, videos, magnets, .torrent files)
aria-dl add URL1 URL2 ~/a.torrent 'magnet:?xt=...'

# From a text file (one source per line; blank lines and # comments are ignored)
aria-dl add -f urls.txt --when night --dir ~/Downloads/batch

# From stdin / macOS clipboard
pbpaste | aria-dl add --audio
```

### Inspect and manage jobs

```bash
aria-dl list                       # List all jobs and progress
aria-dl status <ID> [ID2 ...]      # Job details (ID prefix matching supported)
aria-dl status <ID> --wait --timeout 600   # Block until complete or failed
aria-dl pause <ID> [ID2 ...]       # Pause one or more jobs, including retrying (or: aria-dl pause all)
aria-dl resume <ID> [ID2 ...]      # Resume; failed/retrying jobs reset their retry counter
aria-dl resume all                 # Re-queue paused, failed, waiting, and retrying
aria-dl log <ID> -n 50             # Tail recent download log
aria-dl remove <ID> [ID2 ...]      # Forget job records (keeps downloaded files)
```

Append `--json` for machine-readable output (one job is an object; `list` and batch operations are an array). Field list, exit codes, and `--wait` are in [Use with AI agents](#use-with-ai-agents). `jq` can filter that JSON and is not required to produce it.

## Bulk operations

A state name selects every job in that state. Mix selectors with IDs; each job is acted on once.

```bash
aria-dl resume failed              # Re-queue every failed and retrying job, reset retry counters, tick once
aria-dl resume paused              # Re-queue every paused job
aria-dl resume failed <ID>         # Selector plus an explicit job
aria-dl remove failed              # Forget failed job records; downloaded files stay
aria-dl remove complete            # Forget completed job records; downloaded files stay
```

`resume all` still re-queues paused, failed, waiting, and retrying jobs. Text mode prints one line such as `resumed 3 jobs (failed)`. `--json` returns an array of the affected jobs. If nothing matches, the command prints `no jobs matched` and exits 0.

## Concurrency & Scheduling

- Default concurrency limits: **2** `yt-dlp` jobs + **3** `aria2c` jobs. Override via environment variables:
  - `ARIA_DL_MAX_MEDIA` (default `2`)
  - `ARIA_DL_MAX_ARIA` (default `3`)
- When a job finishes, its wrapper invokes `aria-dl tick` (serialized via `flock`) so the next queued job starts immediately without waiting for the periodic LaunchAgent tick.
- Job states: `queued`, `running`, `waiting` (outside night/Wi-Fi window), `retrying` (backoff before the next attempt), `paused`, `complete`, `failed`.

## Automatic retries

Transient failures are retried at two levels:

- **Inside `yt-dlp`**: media downloads are started with `--retries 5 --fragment-retries 5 --retry-sleep exp=1:30`, so short network glitches are retried before the process exits.
- **Across processes**: if a job exits non-zero, `aria-dl` schedules another attempt instead of failing immediately. aria2c exit code `7` (paused or unfinished control file) stays `waiting` and does not consume a retry.

`aria-dl add --retries N` sets the cross-process cap. The default is `5`, or the value of `ARIA_DL_MAX_RETRIES` when that environment variable is set. `--retries 0` disables automatic cross-process retries.

Each failed attempt waits longer before the next one: **2 minutes, 5 minutes, 15 minutes, 30 minutes, then 60 minutes**. Further attempts stay at 60 minutes until the cap is reached. While it is waiting, the job state is `retrying`. `aria-dl tick` starts it once `next_retry_ts` has passed, and still honors `--when night` and the concurrency caps. One background sleeper runs `aria-dl tick` at that time (a later retry replaces it only when it would fire sooner), so a 2-minute backoff does not sit idle until the next LaunchAgent run. On macOS the LaunchAgent also runs `tick` every 60 seconds as a safety net.

After `retry_count` reaches `max_retries`, the job becomes `failed` and is not retried on its own. Permanently broken URLs therefore stop. `aria-dl resume` on a `failed` or `retrying` job, including `resume failed` and `resume all`, sets `retry_count` back to `0`, clears the schedule, queues the job, and runs `tick` once. Adding that source again does the same for a `failed` or `retrying` job. `aria-dl pause` (including `pause all`) pauses `retrying` jobs and clears `next_retry_ts` / `next_retry_at` without resetting the counter.

`list` and `status` include `retry_count`, `max_retries`, and `next_retry_at` in `--json`. The text view shows a waiting retry as `retry 1/5 @HH:MM`.

## Browser cookies for video sites

Media jobs can pass the browser's own cookies to `yt-dlp`:

```bash
aria-dl add <video-url> --cookies-from-browser chrome
aria-dl add <video-url> --cookies-from-browser 'chrome:Profile 1'
```

The value is stored on the job. When the flag is omitted, `aria-dl` uses `ARIA_DL_COOKIES_FROM_BROWSER`, then the `cookies_from_browser` key in `~/.local/share/aria-dl/config.json` (a missing file changes nothing). If none of those is set and this Netscape file exists, it is used instead:

```text
~/.local/share/aria-dl/cookies/youtube.txt
```

Only one of `--cookies-from-browser` or `--cookies` is passed to `yt-dlp`. Cookie values are never printed or written into status. Status JSON may include the browser name in `cookies_from_browser`.

On macOS, Safari needs Full Disk Access for the terminal. Chrome may prompt for Keychain access once.

Keep the cookies directory mode `700` and never commit cookies to git. If a media download fails with YouTube's "Sign in to confirm you're not a bot" check, the job records `last_error` as `youtube_bot_check` and retries still run. `aria-dl status` suggests browser cookies and, when no proxy is configured, a local proxy.

## YouTube cookies on macOS

LaunchAgent and other background jobs cannot read Chrome, Brave, Edge, Firefox, Safari, or Vivaldi profile directories. macOS TCC returns "Operation not permitted", and yt-dlp then reports that it could not find the cookies database. Import the cookies once from a foreground Terminal, then let background downloads use the file.

```bash
aria-dl cookies refresh                 # auto: first logged-in browser
aria-dl cookies refresh --browser chrome
aria-dl cookies refresh --browser 'chrome:Profile 1'
aria-dl cookies status
./install.sh --cookies                  # macOS: same refresh at the end of install
```

`auto` tries chrome, brave, edge, firefox, safari, then vivaldi, and keeps the first export that contains a logged-in YouTube session (`SAPISID`, `__Secure-3PSID`, or `LOGIN_INFO`). The default browser is `cookies_from_browser` from the environment or `config.json` when that is set, otherwise `auto`. Only `youtube.com` and `google.com` cookies are kept. The file is written atomically, mode `0600`, to `~/.local/share/aria-dl/cookies/youtube.txt`. If that path is a symlink, the bytes go to the symlink target. Cookie values are never printed.

If macOS blocks the read, `cookies refresh` tells you to run it again from Terminal and allow the "access data from other apps" prompt, or to grant Terminal Full Disk Access. Chrome also asks for Keychain "Chrome Safe Storage"; click Always Allow.

`cookies status` reports the file path, age, cookie count, whether a login cookie is present, and the earliest expiry. It does not print names' values.

When a media job fails the YouTube bot check, aria-dl tries one silent `cookies refresh` at most once per hour before the normal retry (under launchd that refresh usually fails, which is expected). Cookie export itself stays direct. The retried download uses the proxy below when one is configured. If a job was started with `cookies_from_browser` and yt-dlp fails because the cookies database is blocked while that browser profile directory exists, the same attempt falls back to the cookies file instead of counting as a failure. If no proxy is configured, `status` also suggests a local proxy.

## Download proxy

The proxy is an argument on the yt-dlp process aria-dl starts. It is not written into `HTTP_PROXY`, `HTTPS_PROXY`, or the macOS system proxy, so other apps stay direct.

```bash
aria-dl config set youtube_proxy http://127.0.0.1:2081   # YouTube media jobs only
aria-dl config set proxy http://127.0.0.1:2081           # every media job
aria-dl config get youtube_proxy
aria-dl config unset youtube_proxy
aria-dl add <video-url> --proxy http://127.0.0.1:2081    # this job only
aria-dl add <video-url> --no-proxy                       # this job goes direct
```

`ARIA_DL_YOUTUBE_PROXY` and `ARIA_DL_PROXY` override the config file. A job flag overrides both. An empty value or `none` disables the proxy. Nothing is proxied until one of these is set.

Before each attempt, aria-dl opens a TCP connection to the proxy host and port (2 second limit). If that fails, the attempt goes direct and the job log records `proxy unreachable, falling back to direct`. The job is not failed only because the proxy is down. `list` and `status --json` show the proxy as `host:port` with any username or password removed.

## Security & Privacy Notes

- All job metadata and logs stay locally under `~/.local/share/aria-dl/jobs/<ID>/`.
- Avoid passing secrets or authenticated tokens directly in CLI arguments if other local users share the machine. JSON strips URL userinfo and shows a proxy as `host:port` only. Cookie values are never printed.
- The download proxy is an argument on the yt-dlp process only. Other apps stay direct, and a closed proxy port falls back to a direct attempt.
- BitTorrent jobs use `--seed-time=0` (stop seeding once complete) and fetch public trackers from `https://cf.trackerslist.com/best_aria2.txt`.

## Tests

```bash
python3 tests/test_agent_cli.py
```

## License

MIT — see [LICENSE](LICENSE).
