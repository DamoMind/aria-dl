#!/usr/bin/env python3
"""Agent-facing contract tests. No network and no real downloads.

    python3 tests/test_agent_cli.py
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "aria-dl")
MCP = os.path.join(ROOT, "examples", "mcp_server.py")


def load_module(home):
    os.environ["ARIA_DL_HOME"] = home
    loader = importlib.machinery.SourceFileLoader("aria_dl_under_test", SCRIPT)
    spec = importlib.util.spec_from_loader("aria_dl_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class AriaDlAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.bin = os.path.join(self.home, "bin")
        os.makedirs(self.bin)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, args, *, env=None, input=None, timeout=10):
        child = os.environ.copy()
        for key in ("ARIA_DL_JSON", "ARIA_DL_YES", "ARIA_DL_YOUTUBE_PROXY", "ARIA_DL_PROXY",
                    "ARIA_DL_COOKIES_FROM_BROWSER", "ARIA_DL_PATH"):
            child.pop(key, None)
        child["ARIA_DL_HOME"] = self.home
        child["ARIA_DL_MAX_MEDIA"] = "0"
        child["ARIA_DL_MAX_ARIA"] = "0"
        child["PATH"] = os.environ.get("PATH", "")
        if env:
            child.update(env)
        kwargs = {"capture_output": True, "text": True, "env": child, "timeout": timeout}
        if input is None:
            kwargs["stdin"] = subprocess.DEVNULL
        else:
            kwargs["input"] = input
        return subprocess.run([sys.executable, SCRIPT, *args], **kwargs)

    def parse(self, proc):
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            self.fail("stdout is not one JSON value:\n%s\nstderr:\n%s\n%s" % (proc.stdout, proc.stderr, exc))

    def add(self, url="https://example.com/file.zip", extra=None, env=None):
        args = ["add", url, "--json", "--non-interactive"]
        if extra:
            args.extend(extra)
        proc = self.run_cli(args, env=env)
        return proc, self.parse(proc) if proc.stdout.strip() else None

    def job_path(self, job_id):
        return os.path.join(self.home, "jobs", job_id, "job.json")

    def write_job(self, job):
        with open(self.job_path(job["id"]), "w", encoding="utf-8") as fh:
            json.dump(job, fh)

    def read_job(self, job_id):
        with open(self.job_path(job_id), encoding="utf-8") as fh:
            return json.load(fh)

    def test_pure_functions(self):
        mod = load_module(self.home)
        self.assertEqual(mod.parse_size("5242880B"), 5242880)
        self.assertEqual(mod.parse_size("10.00MiB"), 10485760)
        self.assertEqual(mod.parse_size("1.5KiB"), 1536)
        self.assertEqual(mod.parse_size("2MB"), 2000000)
        self.assertIsNone(mod.parse_size("nope"))
        self.assertEqual(mod.proxy_hostport("http://user:s3cret@127.0.0.1:2081"), "127.0.0.1:2081")
        self.assertEqual(mod.proxy_hostport("socks5://127.0.0.1:1080"), "127.0.0.1:1080")
        red = mod.redact("see http://user:s3cret@127.0.0.1:2081/x Cookie: SECRETVALUE")
        self.assertNotIn("s3cret", red)
        self.assertNotIn("SECRETVALUE", red)
        self.assertIn("[redacted]", red)
        with open(SCRIPT, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("input(", source)
        self.assertNotIn("getpass", source)

    def test_help_stays_text_when_json_env_set(self):
        proc = self.run_cli(["--help"], env={"ARIA_DL_JSON": "1"})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("AI agents", proc.stdout)
        self.assertIn("Exit codes", proc.stdout)
        self.assertNotIn('"ok"', proc.stdout)

    def test_usage_json_and_exit_code(self):
        proc = self.run_cli([], env={"ARIA_DL_JSON": "1"})
        self.assertEqual(proc.returncode, 2)
        body = self.parse(proc)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "usage")
        self.assertIn("hint", body)
        bare = self.run_cli(["add", "--retries", "-1"])
        self.assertEqual(bare.returncode, 2)
        self.assertEqual(bare.stdout, "")
        self.assertIn("retries", bare.stderr)
        negative = self.run_cli(["status", "abc", "--timeout", "-1", "--json"])
        self.assertEqual(negative.returncode, 2)
        many = self.run_cli(["status", "abc", "def", "--wait", "--json"])
        self.assertEqual(many.returncode, 2)

    def test_add_json_shape_and_human_line(self):
        url = "https://example.com/file.zip"
        proc, body = self.add(url)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        job_id = hashlib.sha1(url.encode()).hexdigest()[:8]
        for key in ("id", "url", "source", "kind", "state", "progress", "bytes", "output_paths", "dir", "last_error", "hint"):
            self.assertIn(key, body)
        self.assertEqual(body["id"], job_id)
        self.assertEqual(body["url"], url)
        self.assertEqual(body["kind"], "url")
        self.assertEqual(body["state"], "queued")
        self.assertIsNone(body["last_error"])
        self.assertIsNone(body["progress"]["percent"])
        self.assertEqual(body["bytes"], {"done": None, "total": None})
        self.assertEqual(body["output_paths"], [])
        self.assertTrue(body["hint"])
        self.assertFalse(body["existed"])
        self.assertEqual(body["action"], "created")
        self.assertTrue(body["ok"])
        self.assertIsNone(body["proxy"])
        self.assertFalse(body["proxy_configured"])
        human = self.run_cli(["list"])
        self.assertEqual(human.returncode, 0)
        self.assertIn(job_id, human.stdout)
        self.assertIn("queued", human.stdout)
        self.assertNotIn("{", human.stdout)

    def test_global_json_and_env(self):
        url = "https://example.com/env.zip"
        proc = self.run_cli(["--json", "add", url])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.parse(proc)["url"], url)
        listed = self.run_cli(["list"], env={"ARIA_DL_JSON": "1"})
        self.assertIsInstance(self.parse(listed), list)
        yes = self.run_cli(["list", "--yes"])
        self.assertEqual(yes.returncode, 0)
        nonint = self.run_cli(["-y", "version"])
        self.assertEqual(nonint.returncode, 0)
        self.assertIn("aria-dl 0.5.0", nonint.stdout)

    def test_idempotent_add(self):
        url = "https://example.com/once.zip"
        first, body = self.add(url)
        self.assertEqual(first.returncode, 0)
        job = self.read_job(body["id"])
        job["state"] = "complete"
        self.write_job(job)
        again, second = self.add(url)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(second["id"], body["id"])
        self.assertTrue(second["existed"])
        self.assertEqual(second["action"], "exists")
        self.assertEqual(second["state"], "complete")
        self.assertEqual(len(os.listdir(os.path.join(self.home, "jobs"))), 1)
        job["state"] = "failed"
        job["retry_count"] = 4
        self.write_job(job)
        _, third = self.add(url)
        self.assertEqual(third["action"], "requeued")
        self.assertTrue(third["existed"])
        self.assertEqual(third["state"], "queued")
        self.assertEqual(third["retry_count"], 0)
        self.assertEqual(len(os.listdir(os.path.join(self.home, "jobs"))), 1)

    def test_running_add_does_not_duplicate(self):
        url = "https://example.com/running.zip"
        _, body = self.add(url)
        job = self.read_job(body["id"])
        job["state"] = "running"
        job["pid"] = os.getpid()
        self.write_job(job)
        _, second = self.add(url)
        self.assertEqual(second["action"], "exists")
        self.assertEqual(second["state"], "running")
        self.assertEqual(second["id"], body["id"])

    def test_stdin_not_consumed_when_args_present_and_no_hang(self):
        proc = self.run_cli(
            ["add", "https://example.com/ok.zip", "--json"],
            input="https://example.com/ignored.zip\n",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = self.parse(proc)
        self.assertEqual(body["url"], "https://example.com/ok.zip")
        listed = self.parse(self.run_cli(["list", "--json"]))
        self.assertEqual(len(listed), 1)
        empty = self.run_cli(["add", "--json"], timeout=5)
        self.assertEqual(empty.returncode, 2)
        self.assertFalse(self.parse(empty)["ok"])
        quick = self.run_cli(["list", "--non-interactive"], timeout=5)
        self.assertEqual(quick.returncode, 0)

    def test_not_found(self):
        proc = self.run_cli(["status", "deadbeef", "--json"])
        self.assertEqual(proc.returncode, 3)
        body = self.parse(proc)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "not_found")
        self.assertIn("aria-dl:", proc.stderr)
        plain = self.run_cli(["status", "deadbeef"])
        self.assertEqual(plain.returncode, 3)
        self.assertEqual(plain.stdout, "")

    def test_status_array_and_schema_required_fields(self):
        self.add("https://example.com/a.zip")
        _, second = self.add("https://example.com/b.zip")
        listed = self.parse(self.run_cli(["list", "--json"]))
        self.assertEqual(len(listed), 2)
        both = self.run_cli(["status", listed[0]["id"], listed[1]["id"], "--json"])
        self.assertEqual(both.returncode, 0)
        self.assertIsInstance(self.parse(both), list)
        one = self.parse(self.run_cli(["status", second["id"], "--json"]))
        self.assertIsInstance(one, dict)
        schema = self.parse(self.run_cli(["schema"]))
        for key in schema["job"]["required"]:
            self.assertIn(key, one)
        self.assertEqual(schema["exit_codes"]["4"][:1], "s")
        tools = self.parse(self.run_cli(["tools"]))
        names = [t["name"] for t in tools["tools"]]
        self.assertIn("status", names)
        status = next(t for t in tools["tools"] if t["name"] == "status")
        self.assertEqual(status["parameters"], status["input_schema"])
        self.assertIn("ids", status["parameters"]["properties"])
        self.assertEqual(status["parameters"]["additionalProperties"], False)

    def test_progress_bytes_and_output_paths(self):
        _, body = self.add("https://example.com/video-page", extra=["--media"])
        dest = os.path.join(self.home, "video.mp4")
        log = os.path.join(self.home, "jobs", body["id"], "aria2.log")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(
                "==== start 2026-01-01 00:00:00 ====\n"
                "[#abcd 5242880B/10485760B(50%) CN:2 SD:1 DL:1000B ETA:5s]\n"
                "[download] Destination: " + dest + "\n"
                "Cookie: SUPERSECRETVALUE\n"
                "http://user:s3cret@127.0.0.1:9/track\n"
            )
        proc = self.run_cli(["status", body["id"], "--json"])
        got = self.parse(proc)
        self.assertEqual(got["percent"], 50)
        self.assertEqual(got["progress"]["percent"], 50)
        self.assertEqual(got["bytes"]["done"], 5242880)
        self.assertEqual(got["bytes"]["total"], 10485760)
        self.assertEqual(got["output_paths"], [dest])
        logged = self.run_cli(["log", body["id"], "--json"])
        text = logged.stdout
        self.assertNotIn("SUPERSECRETVALUE", text)
        self.assertNotIn("s3cret", text)
        self.assertIn("[redacted]", text)
        self.assertEqual(self.parse(logged)["id"], body["id"])

    def test_proxy_secret_not_in_output(self):
        secret = "http://user:s3cret@127.0.0.1:2081"
        proc = self.run_cli(["config", "set", "youtube_proxy", secret, "--json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = self.parse(proc)
        self.assertEqual(body["value"], "127.0.0.1:2081")
        self.assertNotIn("s3cret", proc.stdout)
        self.assertNotIn("s3cret", proc.stderr)
        with open(os.path.join(self.home, "config.json"), encoding="utf-8") as fh:
            stored = fh.read()
        self.assertIn("s3cret", stored)
        self.assertEqual(os.stat(os.path.join(self.home, "config.json")).st_mode & 0o777, 0o600)
        text = self.run_cli(["config", "get", "youtube_proxy"])
        self.assertEqual(text.stdout.strip(), "127.0.0.1:2081")
        self.assertNotIn("s3cret", text.stdout)
        direct, direct_body = self.add("https://example.com/plain.zip")
        self.assertIsNone(direct_body["proxy"])
        self.assertFalse(direct_body["proxy_configured"])
        media = self.run_cli(["add", "https://www.youtube.com/watch?v=exampleid", "--json"])
        media_body = self.parse(media)
        self.assertEqual(media_body["kind"], "media")
        self.assertEqual(media_body["proxy"], "127.0.0.1:2081")
        self.assertTrue(media_body["proxy_configured"])
        blob = media.stdout + media.stderr + self.run_cli(["list"]).stdout
        self.assertNotIn("s3cret", blob)
        unknown = self.run_cli(["config", "get", "nope", "--json"])
        self.assertEqual(unknown.returncode, 2)
        self.assertEqual(self.parse(unknown)["error"], "usage")

    def test_cookies_status_hides_values(self):
        path = os.path.join(self.home, "cookies", "youtube.txt")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# Netscape HTTP Cookie File\n")
            fh.write(".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSAPISID\tSUPERSECRETVALUE\n")
        proc = self.run_cli(["cookies", "status", "--json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = self.parse(proc)
        self.assertTrue(body["exists"])
        self.assertTrue(body["login"])
        self.assertEqual(body["cookie_count"], 1)
        self.assertNotIn("SUPERSECRETVALUE", proc.stdout)
        self.assertNotIn("SUPERSECRETVALUE", proc.stderr)
        human = self.run_cli(["cookies", "status"])
        self.assertNotIn("SUPERSECRETVALUE", human.stdout)

    def test_wait_outcomes(self):
        _, body = self.add("https://example.com/wait.zip")
        job = self.read_job(body["id"])
        job["state"] = "complete"
        self.write_job(job)
        done = self.run_cli(["status", body["id"], "--wait", "--timeout", "5", "--json"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.parse(done)["state"], "complete")
        self.assertFalse(self.parse(done)["timed_out"])

        job["state"] = "failed"
        job["last_error"] = "youtube_bot_check"
        self.write_job(job)
        bot = self.run_cli(["status", body["id"], "--wait", "--json"])
        self.assertEqual(bot.returncode, 4)
        self.assertEqual(self.parse(bot)["last_error"], "youtube_bot_check")
        self.assertIn("cookies refresh", self.parse(bot)["hint"])

        job["last_error"] = "network"
        self.write_job(job)
        net = self.run_cli(["status", body["id"], "--timeout", "0", "--json"])
        self.assertEqual(net.returncode, 4)

        job["last_error"] = "dependency_missing"
        job["missing_tool"] = "aria2c"
        self.write_job(job)
        dep = self.run_cli(["status", body["id"], "--wait", "--json"])
        self.assertEqual(dep.returncode, 5)

        job["last_error"] = None
        job["state"] = "failed"
        self.write_job(job)
        other = self.run_cli(["status", body["id"], "--wait", "--json"])
        self.assertEqual(other.returncode, 1)

        job["state"] = "queued"
        job["last_error"] = None
        self.write_job(job)
        timed = self.run_cli(["status", body["id"], "--timeout", "0", "--json"])
        self.assertEqual(timed.returncode, 6)
        self.assertTrue(self.parse(timed)["timed_out"])
        self.assertEqual(self.parse(timed)["state"], "queued")
        query = self.run_cli(["status", body["id"], "--json"])
        self.assertEqual(query.returncode, 0)
        self.assertNotIn("timed_out", self.parse(query))

    def test_log_detection_of_bot_check_and_network(self):
        _, body = self.add("https://www.youtube.com/watch?v=exampleid")
        stamp = os.path.join(self.home, ".cookies-refresh-ts")
        with open(stamp, "w", encoding="utf-8") as fh:
            fh.write(str(time.time()))
        job = self.read_job(body["id"])
        job["state"] = "running"
        job["pid"] = 2 ** 30
        job["max_retries"] = 0
        self.write_job(job)
        log = os.path.join(self.home, "jobs", body["id"], "aria2.log")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("Sign in to confirm you're not a bot\n")
        with open(os.path.join(self.home, "jobs", body["id"], "exitcode"), "w", encoding="utf-8") as fh:
            fh.write("1\n")
        proc = self.run_cli(["status", body["id"], "--wait", "--json"], timeout=8)
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertEqual(self.parse(proc)["last_error"], "youtube_bot_check")
        self.assertEqual(self.parse(proc)["state"], "failed")

        job = self.read_job(body["id"])
        job["state"] = "running"
        job["max_retries"] = 0
        job["last_error"] = None
        self.write_job(job)
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("network is unreachable\n")
        net = self.run_cli(["status", body["id"], "--json"])
        self.assertEqual(net.returncode, 0)
        self.assertEqual(self.parse(net)["last_error"], "network")

    def test_missing_dependency_exit(self):
        empty = os.path.join(self.home, "empty-bin")
        os.makedirs(empty)
        proc = self.run_cli(
            ["add", "https://example.com/needs-aria2.bin", "--json"],
            env={"PATH": empty, "ARIA_DL_PATH": empty, "ARIA_DL_MAX_ARIA": "3", "ARIA_DL_MAX_MEDIA": "0"},
        )
        self.assertEqual(proc.returncode, 5, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertNotIn("Traceback", proc.stdout)
        body = self.parse(proc)
        self.assertFalse(body["ok"])
        self.assertEqual(body["state"], "failed")
        self.assertEqual(body["last_error"], "dependency_missing")
        self.assertEqual(body["missing_tool"], "aria2c")
        self.assertIn("aria2c", body["hint"])

    def test_bulk_resume_remove_and_partial_add(self):
        _, body = self.add("https://example.com/bulk.zip")
        job = self.read_job(body["id"])
        job["state"] = "failed"
        self.write_job(job)
        text = self.run_cli(["resume", "failed"])
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("resumed 1 job", text.stdout)
        again = self.read_job(body["id"])
        again["state"] = "complete"
        self.write_job(again)
        removed = self.run_cli(["remove", body["id"]])
        self.assertIn("removed job", removed.stdout)
        self.assertIn("files kept", removed.stdout)
        self.assertFalse(os.path.exists(self.job_path(body["id"])))
        partial = self.run_cli(["add", "not a source", "https://example.com/good.zip", "--json"])
        self.assertEqual(partial.returncode, 1)
        rows = self.parse(partial)
        self.assertIsInstance(rows, list)
        self.assertTrue(any(row.get("ok") is False for row in rows))
        self.assertTrue(any(row.get("ok") is True for row in rows))

    def test_version_dependencies(self):
        proc = self.run_cli(["version", "--json"])
        body = self.parse(proc)
        self.assertEqual(body["name"], "aria-dl")
        self.assertEqual(body["version"], "0.5.0")
        self.assertEqual(set(body["dependencies"]), {"aria2c", "yt-dlp", "ffmpeg"})

    def test_mcp_roundtrip(self):
        env = os.environ.copy()
        env["ARIA_DL_HOME"] = self.home
        env["ARIA_DL_MAX_MEDIA"] = "0"
        env["ARIA_DL_MAX_ARIA"] = "0"
        proc = subprocess.Popen(
            [sys.executable, MCP],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        def rpc(msg):
            proc.stdin.write((json.dumps(msg) + "\n").encode())
            proc.stdin.flush()
            ready, _, _ = select.select([proc.stdout], [], [], 8)
            if not ready:
                proc.kill()
                err = proc.stderr.read().decode("utf-8", "replace")
                self.fail("mcp server timed out: %s" % err)
            line = proc.stdout.readline()
            self.assertTrue(line)
            return json.loads(line.decode())

        init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "aria-dl")
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
        proc.stdin.flush()
        listed = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [item["name"] for item in listed["result"]["tools"]]
        self.assertIn("version", names)
        self.assertIn("inputSchema", listed["result"]["tools"][0])
        called = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "version", "arguments": {}}})
        self.assertFalse(called["result"]["isError"])
        self.assertEqual(json.loads(called["result"]["content"][0]["text"])["name"], "aria-dl")
        empty = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "list", "arguments": {}}})
        self.assertFalse(empty["result"]["isError"])
        self.assertEqual(json.loads(empty["result"]["content"][0]["text"]), [])
        proc.stdin.close()
        self.assertEqual(proc.wait(timeout=5), 0)
        proc.stdout.close()
        proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
