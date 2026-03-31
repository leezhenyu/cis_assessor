import os
import sys

import paramiko
from scp import SCPClient

HOST = "192.168.1.30"
USER = "eric"
PASS = "189640"
REMOTE_DIR = "cis_assessor_deploy"

print("Connecting to %s..." % HOST)
ssh = paramiko.SSHClient()

# Security: load the system + user known_hosts files so only verified
# host keys are accepted. RejectPolicy (the default) will raise
# paramiko.ssh_exception.SSHException if the host key is unknown or
# has changed, preventing man-in-the-middle attacks.
# To add a new host: ssh-keyscan 192.168.1.30 >> ~/.ssh/known_hosts
ssh.load_system_host_keys()          # /etc/ssh/ssh_known_hosts
ssh.load_host_keys(                  # ~/.ssh/known_hosts
    os.path.expanduser("~/.ssh/known_hosts")
)
ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

try:
    ssh.connect(HOST, port=22, username=USER, password=PASS)
except paramiko.ssh_exception.SSHException as e:
    print(
        f"ERROR: Could not verify host key for {HOST}.\n"
        f"If this is a trusted host, add its key first:\n"
        f"  ssh-keyscan {HOST} >> ~/.ssh/known_hosts\n"
        f"Details: {e}"
    )
    sys.exit(1)

print("Uploading cis_assessor...")
with SCPClient(ssh.get_transport()) as scp:
    scp.put('cis_assessor', recursive=True, remote_path=REMOTE_DIR)

print("Preparing dependencies on remote...")
cmd1 = f"cd {REMOTE_DIR} && python3 -m pip install jinja2 --user"
stdin, stdout, stderr = ssh.exec_command(cmd1)
exit_status = stdout.channel.recv_exit_status()
if exit_status != 0:
    print("pip install failed:", stderr.read().decode())

print("Running Level 2 CIS Assessor on remote (skipping remote HTML render)...")
cmd2 = f"cd {REMOTE_DIR} && echo '{PASS}' | sudo -S python3 cis_assessor.py --level 2 --type server --output-dir ./remote_output --format json,csv"
stdin, stdout, stderr = ssh.exec_command(cmd2, get_pty=True)

# print output live
while True:
    line = stdout.readline()
    if not line:
        break
    print(line.strip('\n'))

exit_status = stdout.channel.recv_exit_status()
print(f"Assessment complete. Exit status: {exit_status}")

print("Downloading reports...")
# We need to find the specific output directory inside remote_output (newest one)
cmd3 = f"ls -1dt {REMOTE_DIR}/remote_output/* | head -1"
stdin, stdout, stderr = ssh.exec_command(cmd3)
output_dir = stdout.read().decode().strip()

if output_dir:
    print(f"Downloading from {output_dir}")
    os.makedirs('downloaded_report', exist_ok=True)
    with SCPClient(ssh.get_transport()) as scp:
        scp.get(output_dir, local_path='downloaded_report/', recursive=True)
    print("Report downloaded successfully to downloaded_report/")
    
    # Run the local HTML generator
    print("Generating HTML report locally...")
    os.system("/Users/eric/proj/cis_asessor/venv/bin/python /tmp/gen_html.py")
else:
    print("Failed to find output directory.")

ssh.close()
print("Done.")
