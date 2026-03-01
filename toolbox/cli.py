#!/usr/bin/env python3
"""
Usage:
    npu-toolbox [OPTIONS] COMMAND [COMMAND_ARGS]

How to add 'npu-toolbox' command to system:
1. `cd npu-toolbox`
2. `uv tool install ---editable .`(recommendation) or `uv pip install -e .`(for dev)
"""

import argparse
import importlib
import ast
import re
import shutil
import subprocess
import sys
import os
from pathlib import Path

TOOLBOX_BASE_DIR = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = TOOLBOX_BASE_DIR / "scripts"

COMMANDS = {
    "list": {
        "script": None,
        "help": "List all subcommands",
    },
    "probe": {
        "script": "npu_probe.sh",
        "help": "Probe NPU driver and runtime",
        "system_deps": [],
        "sudo": True, 
    },
    # here auto-discover from the script rather than fixed python_deps
    "benchmark": {
        "script": "benchmark.py",
        "help": "Run NPU benchmark",
        # "system_deps": [], 
        # "python_deps": ["ai-edge-litert", "pillow", "numpy"],
    },
}

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"

SYSTEMDRUN_FIX = '''if [ -z "$XDG_RUNTIME_DIR" ] && [ -d "/run/user/$(id -u)" ]; then
    export XDG_RUNTIME_DIR=/run/user/$(id -u)
    export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
fi'''

def get_script_deps(script_name):
    """Auto-discovers PEP 723 python dependencies using regex and ast."""
    if not script_name or not script_name.endswith('.py'):
        return []

    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return []

    content = script_path.read_text()
    match = re.search(r'^#\s+dependencies\s*=\s*(\[[^]]*?\])', content, re.MULTILINE)
    
    if match:
        try:
            raw_deps, n = re.subn(r'\n*#\s*','',match.group(1), re.MULTILINE)
            dependencies = ast.literal_eval(raw_deps)
            # print(f'dependencies={dependencies}, n={n}')
            return [re.split(r'[<>=!~]', d)[0].strip() for d in dependencies]
        except (ValueError, SyntaxError):
            return []
    return []

def get_install_type():
    exe = sys.executable
    if "/uv/tools" in exe:
        return "uv_tool"
    
    # In a standard virtual env or editable install
    if sys.base_prefix != sys.prefix:
        return "pip_editable"
        
    return "system"

def check_system_deps(commands):
    """Verifies that required shell commands exist in PATH."""
    missing = [cmd for cmd in commands if shutil.which(cmd) is None]
    if missing:
        print(f"{RED}Error:{RESET} missing system dependencies '{', '.join(missing)}'")
        print(f"Please install them using your system package manager (e.g., apt, brew).")
        sys.exit(1)

def check_python_deps(packages):
    """Verifies that required python packages are installed in current environment."""
    from importlib import metadata
    missing = []
    # Look for the package name exactly as defined in pip
    for package in packages:
        try:
            metadata.version(package)
        except metadata.PackageNotFoundError:
            missing.append(package)
    if missing:
        print(f"{RED}Error:{RESET} missing python packages '{', '.join(missing)}'")
        print(f"Please run {BLUE}'uv pip install {' '.join(missing)}'{RESET}")
        sys.exit(1)

def run_command(cmd_name, args, extra_args=None):
    """The execution engine for all subcommands."""
    cfg = COMMANDS[cmd_name]
    
    if cmd_name == "list":
        print(f"{GREEN}Usage:{RESET} {BLUE}npu-toolbox [OPTIONS] COMMAND [COMMAND_ARGS]{RESET}\n")
        print(f"{GREEN}Options:{RESET}")
        print(f"  {BLUE}-h, --help{RESET}         Show this help message and exit")
        print(f"  {BLUE}--ramlimit SIZE{RESET}    Limit the process tree RAM usage (unit MB)\n")
        print(f"{GREEN}Commands:{RESET}")
        for name, info in COMMANDS.items():
            print(f"  {BLUE}{name:<13}{RESET} {info.get('help', '')}")
        print(f"\nRun 'npu-toolbox COMMAND --help' for specific script options.")
        return

    script_file = cfg.get("script")
    script_path = SCRIPTS_DIR / script_file

    if not script_path.exists():
        print(f"{RED}Error:{RESET} script not found '{script_path}'")
        sys.exit(1)

    install_type = get_install_type()

    # Check Dependencies
    sys_reqs = cfg.get("system_deps", [])
    check_system_deps(sys_reqs)
    if script_path.suffix == ".py" and install_type == "pip_editable":
        py_reqs = cfg.get("python_deps", get_script_deps(script_file))
        check_python_deps(py_reqs)
    
    # Enviroment
    env = os.environ.copy()
    env["TOOLBOX_BASE_DIR"] = str(TOOLBOX_BASE_DIR)

    # Setup the Jail (RAM limit)
    ram_mb = getattr(args, 'ramlimit', None)
    cg_name = f"npu_jail_{os.getpid()}" if ram_mb else None
    if ram_mb and not shutil.which("systemd-run"):
        print(f"{RED}Error:{RESET} 'systemd-run' not found, which --ramlimit needed.")
        sys.exit(1)
    if ram_mb and (not os.environ.get("DBUS_SESSION_BUS_ADDRESS") or not os.environ.get("XDG_RUNTIME_DIR")):
        print(f"{RED}Error:{RESET} the environment variables for systemd-run not found.")
        print(f"{BLUE}Add these lines to your ~/.bashrc{RESET}\n{SYSTEMDRUN_FIX}")
        sys.exit(1)
    
    # Setup inner command
    inner_cmd = []
    if script_path.suffix == ".py":
        runpy = ["uv", "run", str(script_path)] + extra_args
        if install_type == "pip_editable":
            runpy = [sys.executable, str(script_path)] + extra_args
        inner_cmd = runpy
    else:
        inner_cmd = ["bash", str(script_path)] + extra_args

    if os.geteuid() != 0 and cfg.get("sudo") is True:
        inner_cmd = ["sudo", "-E"] + inner_cmd

    # Wrap with Jailer if needed
    jail_cmd = []
    if ram_mb:
        jail_cmd = (["systemd-run", "--user"] if os.geteuid() != 0 else ["systemd-run"]) + [
                "--scope",
                #"--quiet",
                f"--property=MemoryMax={ram_mb}M",
                f"--property=MemorySwapMax=0",
                "--collect" # Clean up logs immediately after finish
            ]

    # Execution
    try:
        # print(f"Running {cmd_name}...")
        subprocess.run(jail_cmd + inner_cmd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(prog='npu-toolbox',
        description='tools for NPUs on edge computing devices',
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ramlimit', type=str, metavar='SIZE', help="Limit the process tree RAM usage (unit MB)")
    # Override the default error handler
    def handle_arg_error(message):
        print(f"{RED}Error:{RESET} {message}")
        run_command("list", None)
        sys.exit(1)
    parser.error = handle_arg_error

    def check_ramlimit_value(raw_value, warning_value=None):
        try:
            ramlimit = int(raw_value)
            # Check for negative or zero values
            if ramlimit <= 0:
                raise argparse.ArgumentError('SIZE should be a positive integer')
            # Safety Floor Check
            if warning_value and ramlimit < warning_value:
                print(f"{YELLOW}Warning:{RESET} {ramlimit}MB is very low. "
                    "The process may be killed immediately by the kernel.")
        except:
            parser.error(f'argument --ramlimit: SIZE={args.ramlimit}, which should be a positive integer')

    args, unknown = parser.parse_known_args()
    user_command = None
    remaining_args = []
    wants_help = False
    for i, item in enumerate(unknown):
        if not item.startswith('-'):
            user_command = item
            remaining_args = unknown[i+1:]
            break
        elif item in ('-h', '--help'):
            # global help
            wants_help = True
        else:
            parser.error(f"'{item}' is not a valid OPTION.")

    # Triggered by: 'npu-toolbox', 'npu-toolbox --options'
    if not user_command or wants_help:
        if not wants_help:
            if args.ramlimit is not None:
                check_ramlimit_value(args.ramlimit)
            parser.error(f"COMMAND not found.")
        else:
            run_command("list", args)
            sys.exit(0)

    # Triggered by: 'npu-toolbox unknown-command'
    if user_command not in COMMANDS:
        parser.error(f"'{user_command}' is not a valid COMMAND.")
    elif args.ramlimit is not None:
        check_ramlimit_value(args.ramlimit, 50)

    # Triggered by: 'npu-toolbox command --help' 
    run_command(user_command, args, remaining_args)
    return

if __name__ == "__main__":
    main()