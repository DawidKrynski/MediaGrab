import base64
from types import SimpleNamespace
import subprocess
import sys

import pytest

from mediagrab.models import MediaError
from mediagrab import privacy


def test_windows_private_directory_uses_current_sid_without_shell(tmp_path, monkeypatch):
    calls = []

    def run(arguments, **options):
        calls.append((arguments, options))
        return SimpleNamespace(stdout='"example\\user","S-1-5-21-100-200-300-1001"\n')

    monkeypatch.setattr(privacy.sys, "platform", "win32")
    monkeypatch.setattr(privacy.subprocess, "run", run)
    privacy.protect_private_directory(tmp_path)
    assert len(calls) == 3
    assert calls[1][0][1:] == [str(tmp_path), "/reset"]
    args, options = calls[2]
    assert args[1:] == [
        str(tmp_path),
        "/inheritance:r",
        "/grant:r",
        "*S-1-5-21-100-200-300-1001:(OI)(CI)F",
    ]
    assert "shell" not in options and options["creationflags"] == 0x08000000
    assert options["capture_output"] and options["check"]


@pytest.mark.parametrize("output", ["", "invalid", '"user","unexpected"'])
def test_windows_private_directory_refuses_invalid_identity(tmp_path, monkeypatch, output):
    calls = []
    monkeypatch.setattr(privacy.sys, "platform", "win32")
    monkeypatch.setattr(
        privacy.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args) or SimpleNamespace(stdout=output),
    )
    with pytest.raises(MediaError, match="No cookies were copied"):
        privacy.protect_private_directory(tmp_path)
    assert len(calls) == 1


def test_windows_private_directory_sanitizes_acl_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(privacy.sys, "platform", "win32")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["private-path"], stderr="private output")

    monkeypatch.setattr(privacy.subprocess, "run", fail)
    with pytest.raises(MediaError) as error:
        privacy.protect_private_directory(tmp_path)
    assert "private-path" not in str(error.value) and "private output" not in str(error.value)


@pytest.mark.skipif(sys.platform != "win32", reason="Checks native Windows ACLs")
def test_real_windows_cookie_directory_excludes_inherited_access(tmp_path):
    private = tmp_path / "private cookie directory"
    private.mkdir()
    privacy.protect_private_directory(private)
    # Inspect the actual DACL, not POSIX mode bits which Windows ignores.
    literal = str(private).replace("'", "''")
    # Use .NET directly: a nested Windows PowerShell process can inherit pwsh's
    # PSModulePath, so Get-Acl module auto-loading is not a reliable test fixture.
    script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $directory = [System.IO.DirectoryInfo]::new('{literal}')
    $acl = $directory.GetAccessControl([System.Security.AccessControl.AccessControlSections]::Access)
    $rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
    $current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if (-not $acl.AreAccessRulesProtected) {{ throw 'DACL still inherits access.' }}
    if ($rules.Count -ne 1) {{ throw 'DACL does not contain exactly one access rule.' }}
    if ($rules[0].IdentityReference.Value -ne $current) {{ throw 'DACL grants another identity.' }}
    if ($rules[0].AccessControlType -ne 'Allow') {{ throw 'DACL rule is not Allow.' }}
    if ($rules[0].FileSystemRights -ne 'FullControl') {{ throw 'DACL lacks FullControl.' }}
    [Console]::Out.WriteLine('ACL_PRIVATE')
    exit 0
}} catch {{
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}}
"""
    # Submit one script, rather than executing stdin line by line after an error.
    encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=20,
        creationflags=0x08000000,
    )
    assert result.returncode == 0 and result.stdout.strip() == "ACL_PRIVATE", (
        f"Native ACL inspection failed (exit {result.returncode}).\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
