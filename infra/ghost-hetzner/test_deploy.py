import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import deploy


class DeploymentTests(unittest.TestCase):
    def run_env_setup(self, directory, openssl):
        script = (deploy.ROOT / "bootstrap.sh").read_text()
        script = script[script.index('if [ ! -f .env ]; then'):script.index('docker compose up')]
        script = script.replace('/opt/ghost/public.env', 'public.env')
        (directory / "public.env").write_text("BLOG_DOMAIN=blog.example.com\n")
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail\numask 077\nADMIN_DOMAIN=private.ts.net\n'
             + openssl + '\n' + script],
            cwd=directory, capture_output=True, text=True,
        )

    def test_password_generation_failure_does_not_leave_partial_env(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result = self.run_env_setup(directory, 'openssl() { return 1; }')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((directory / ".env").exists())
            self.assertFalse((directory / ".env.tmp").exists())

    def test_env_is_private_and_passwords_survive_rerun(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result = self.run_env_setup(directory, 'openssl() { printf "test-password\\n"; }')
            self.assertEqual(result.returncode, 0, result.stderr)
            env = directory / ".env"
            original = env.read_text()
            self.assertIn("DB_ROOT_PASSWORD=test-password\n", original)
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            result = self.run_env_setup(directory, 'openssl() { return 1; }')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_text(), original)

    def test_cloud_init_keeps_secrets_out_of_shell_commands(self):
        key = 'tskey-test-"\n$(`not-a-command`)'
        config = json.loads(deploy.cloud_config("blog.example.com", key).split("\n", 1)[1])
        files = {entry["path"]: entry for entry in config["write_files"]}
        self.assertEqual(files["/run/tailscale-auth.key"]["content"], key)
        self.assertEqual(files["/run/tailscale-auth.key"]["permissions"], "0600")
        self.assertNotIn(key, json.dumps(config["runcmd"]))
        self.assertFalse(config["ssh_pwauth"])
        self.assertTrue(config["disable_root"])

    @patch("deploy.wait_for_bootstrap")
    @patch.object(deploy.Hetzner, "wait_action")
    @patch("deploy.secret", side_effect=["hetzner-secret", "tailscale-secret"])
    @patch("deploy.subprocess.run")
    @patch("deploy.shutil.which", return_value="/usr/bin/tailscale")
    @patch.object(deploy.Hetzner, "request")
    def test_firewall_attached_at_creation_without_ssh(self, request, which, run, secret, wait, bootstrap):
        run.return_value.returncode = 0
        run.return_value.stdout = '{"BackendState":"Running"}'
        request.side_effect = [
            {"servers": []}, {"firewalls": []}, {"firewall": {"id": 42}},
            {"server": {"id": 100, "public_net": {"ipv4": {"ip": "192.0.2.1"}}}, "action": {"id": 10}},
        ]
        with patch("sys.argv", ["deploy.py", "--domain", "blog.example.com"]):
            deploy.main()
        firewall = request.call_args_list[2].args[2]
        self.assertEqual([rule["port"] for rule in firewall["rules"]], ["80", "443"])
        server = request.call_args_list[3].args[2]
        self.assertEqual(server["firewalls"], [{"firewall": 42}])
        self.assertNotIn("hetzner-secret", server["user_data"])

    @patch("deploy.secret", return_value="token")
    @patch("deploy.subprocess.run")
    @patch("deploy.shutil.which", return_value="/usr/bin/tailscale")
    @patch.object(deploy.Hetzner, "request", return_value={"servers": [{"id": 100}]})
    def test_existing_server_is_not_modified(self, request, which, run, secret):
        run.return_value.returncode = 0
        run.return_value.stdout = '{"BackendState":"Running"}'
        with patch("sys.argv", ["deploy.py", "--domain", "blog.example.com"]):
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                deploy.main()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[0], "GET")

    def test_domain_injection_rejected_before_api_calls(self):
        with patch("sys.argv", ["deploy.py", "--domain", "example.com\nEVIL=1"]):
            with self.assertRaises(SystemExit) as result:
                deploy.main()
        self.assertEqual(result.exception.code, 2)

    @patch.dict(os.environ, {}, clear=True)
    @patch("sys.stdin.isatty", return_value=False)
    def test_secret_input_requires_terminal_or_environment(self, isatty):
        with self.assertRaises(ValueError):
            deploy.secret("HCLOUD_TOKEN", "Token: ")


if __name__ == "__main__":
    unittest.main()
