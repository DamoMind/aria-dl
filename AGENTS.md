# aria-dl for agents

Single-file download queue for torrents, magnets, HTTP(S), and video (yt-dlp). Same binary humans use. Parse **stdout only**. Progress and errors are on stderr.

```bash
aria-dl add 'https://example.com/file.zip' --json --non-interactive
aria-dl status JOBID --wait --timeout 600 --json
aria-dl tools --json
aria-dl schema
```

`ARIA_DL_JSON=1` is the same as `--json`. `--yes` and `--non-interactive` are accepted. The CLI never prompts; a non-TTY stdin does not prompt either. macOS Keychain or TCC dialogs are the operating system. Import cookies once with `aria-dl cookies refresh` in a terminal.

## JSON

One pretty-printed JSON value per command (indent 1). Not JSON Lines. `json.loads` the whole stdout. jq is optional.

`list` is always an array (`[]` when empty). One id from `status`, `add`, `pause`, `resume`, or `remove` is an object. Several ids, `--file`, or several sources are an array.

A job object always has: `id`, `url`, `source`, `kind`, `state`, `progress`, `bytes`, `output_paths`, `dir`, `last_error`, `hint`. `progress` repeats the legacy top-level `percent`, `done`, `total`, `speed`, `eta`, `connections`, and `seeds`. Ignore unknown keys.

`add` also sets `existed`, `action` (`created`, `requeued`, `exists`), and `ok`. The id is `sha1(source)[:8]`. Adding the same URL again returns that id. A running or complete job is left as it is (`action` `exists`). Any other existing job is queued again (`requeued`).

`status --wait` adds `timed_out`. `config get` of a proxy returns `host:port` or `null`.

`aria-dl schema` is the authoritative shape if this file and the command ever disagree.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success. `status` without `--wait` exits 0 when the id exists, even if the job failed. |
| 1 | Bad source, partial batch, or `--wait` ended in `failed`. |
| 2 | Usage error (bad flags, missing args, unknown config key). |
| 3 | No unique job for that id. |
| 4 | `--wait` ended with `last_error` `youtube_bot_check` or `network`. |
| 5 | `aria2c` or `yt-dlp` is missing. The job is kept. Install the tool and `resume` the id. |
| 6 | `--wait` timed out. The job is still in progress. |
| 130 | Interrupted. |

Check the exit code and the JSON. Use `--wait` when the download result is what you need.

```bash
aria-dl status "$id" --wait --timeout 600 --json
# 0 complete, 4 bot-check or network, 5 missing tool, 6 still running, 1 other failure
```

`--timeout 0` checks once. Omit `--timeout` to wait until a terminal state. Retries and the night window are not terminal; pass a timeout so you do not block overnight.

On code 4 with `youtube_bot_check`, tell the user to run `aria-dl cookies refresh` in a terminal, or set `youtube_proxy`. Do not invent cookies.

## Tools

`aria-dl tools --json` prints definitions you can register. Copy `name`, `description`, and `parameters` for OpenAI-style function calling. `input_schema` is the same object for Anthropic. `aria_dl` is only for wrappers that build argv.

`examples/mcp_server.py` is a stdlib MCP stdio server. It is optional and is not installed by `install.sh`.

```bash
python3 examples/mcp_server.py
```

## Safety

- Cookie values are never printed. `cookies status` reports counts and whether a login cookie exists.
- Proxy output is `host:port` only. Usernames and passwords stay in the mode `0600` config file and are not echoed.
- The proxy is an argument to yt-dlp only. It does not change `HTTP_PROXY`, `HTTPS_PROXY`, or the system proxy. If that port is closed, the attempt goes direct.
- URL userinfo is stripped in JSON. Query strings are kept, so do not put tokens in the URL.
- `remove` deletes the job record only. Files in `dir` stay.
- Download only URLs the user asked for.
- `ARIA_DL_HOME` isolates state. The default is `~/.local/share/aria-dl`. Leave the LaunchAgent on `aria-dl tick` without `ARIA_DL_JSON`.

## State

`queued`, `running`, `waiting` (night window), `retrying`, `paused`, `complete`, `failed`.

Concurrency defaults: 2 media jobs, 3 aria2c jobs (`ARIA_DL_MAX_MEDIA`, `ARIA_DL_MAX_ARIA`).

Tests: `python3 tests/test_agent_cli.py`
