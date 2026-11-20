# aria-dl

A lightweight, zero-dependency Python CLI wrapper around `aria2c` and `yt-dlp` for managing background downloads on macOS (and Linux) — designed to be ergonomic both for humans and for AI agents (`--json` output).

Supports **`.torrent` files, magnet links, HTTP(S)/FTP URLs, and video sites** (YouTube, Bilibili, X/Twitter, Vimeo, Niconico, TikTok, Instagram, SoundCloud, etc.), with batch input, concurrency queuing, automatic resume, and optional **night-only + Wi-Fi-only** scheduling.

## Features

- **Unified interface**: one command for torrents, magnets, direct URLs (`aria2c`), and video/audio pages (`yt-dlp`).
- **Batch & queue**: pass multiple sources on the command line, load from a file (`-f urls.txt`), or pipe via stdin (`pbpaste | aria-dl add`). Runs up to 2 media jobs + 3 aria2 jobs concurrently by default and auto-starts the next queued job immediately when a slot frees.
- **Night + Wi-Fi scheduling (`--when night`)**: downloads only between `22:00–08:00` local time when the default network route is Wi-Fi, automatically pausing outside that window and resuming later.
- **Resumable & non-destructive**: passes `--continue` to both `aria2c` and `yt-dlp`; `aria-dl remove` deletes only the job record, never downloaded files.
- **Automatic retries**: `yt-dlp` retries transient network errors in-process. If a download process still fails, the job waits out a backoff (2m, 5m, 15m, 30m, 60m) and tries again, up to `--retries` (default 5), then stops.
- **Agent-friendly**: every command supports `--json` for structured output (status, percent, downloaded/total size, speed, peers, ETA, destination directory).
- **Single-file stdlib Python 3**: no pip dependencies required.

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

`install.sh` installs `aria-dl` to `~/.local/bin/aria-dl` (symlinking to `/usr/local/bin/aria-dl` if writable) and, on macOS, registers a LaunchAgent (`com.damomind.aria-dl`) that runs `aria-dl tick` every 60 seconds as a safety net for night windows, retries, and reboots. A pending retry also schedules one delayed `tick` at its backoff deadline, so a short wait is not pushed out to the next periodic run.

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
aria-dl pause <ID> [ID2 ...]       # Pause one or more jobs, including retrying (or: aria-dl pause all)
aria-dl resume <ID> [ID2 ...]      # Resume; failed/retrying jobs reset their retry counter
aria-dl resume all                 # Re-queue paused, failed, waiting, and retrying
aria-dl log <ID> -n 50             # Tail recent download log
aria-dl remove <ID> [ID2 ...]      # Forget job records (keeps downloaded files)
```

Append `--json` to any command for machine-readable output (single job returns a JSON object; batch operations return a JSON array).

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

Keep the cookies directory mode `700` and never commit cookies to git. If a media download fails with YouTube's "Sign in to confirm you're not a bot" check, the job records `last_error` as `youtube_bot_check`, retries still run, and `aria-dl status` adds `hint: set --cookies-from-browser chrome`.

## Security & Privacy Notes

- All job metadata and logs stay locally under `~/.local/share/aria-dl/jobs/<ID>/`.
- Avoid passing secrets or authenticated tokens directly in CLI arguments if other local users share the machine.
- BitTorrent jobs use `--seed-time=0` (stop seeding once complete) and fetch public trackers from `https://cf.trackerslist.com/best_aria2.txt`.

## License

MIT — see [LICENSE](LICENSE).
