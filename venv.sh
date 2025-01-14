#!/usr/bin/env bash
#
# Perform various actions for a python virtual environment.
# This includes the following:
# 	* creation
# 	* activation
# 	* installing packages
# 	* exporting packages
# 	* removal

# Ansi escape codes for colored output
ANSI_ESCAPE="\033[0"
RESET="${ANSI_ESCAPE}m"
RED="${ANSI_ESCAPE};31m"
GRE="${ANSI_ESCAPE};32m"
YEL="${ANSI_ESCAPE};33m"

## Printing functions ##

#######################################
# Info Echo
#######################################
function info_echo() {
	echo -e "${GRE}[info] ${1}${RESET}"
}

#######################################
# Warning Echo
#######################################
function warning_echo() {
	echo -e "${YEL}[warning] ${1}${RESET}"
}

#######################################
# Error Echo
#######################################
function error_echo() {
	# Non-exiting error
	echo -e "${RED}[error] ${1}${RESET}"
}

#######################################
# Fatal Error Echo
#######################################
function fatal_echo() {
	echo -e "${RED}[error] ${1}${RESET}"
	exit 1
}

#######################################
# Print Help message
#######################################
function usage() {
	local script="${0##*/}"
	cat <<-EOM
		Usage: $script [option] [env_name]

		   This script, $script, is meant to quickly setup
		   python virtual environments

		Required Arguments:
		   option 			Means of interacting with a virtual python environment
							Options: create, activate, install, export, remove

		   env_name 			Name of the environment

		Optional Arguments:
		   -h, --help 		Display this help and exit
	EOM
}

function check_venv() {
	if ! command -v python3 -m venv &>/dev/null; then
		warning_echo "The python module 'venv' is not installed. Installing..."
		python3 -m pip install --user venv
		info_echo "Success: 'venv' installation complete"
	fi
}

#######################################
# Creates a new virtual environment with
# the specified name.
#
# Arguments:
# 	Virtual Environment Name
#######################################
function create_venv() {
	# Check if venv is installed
	# and if not, install it
	check_venv

	local env_name="${1:-".venv"}"

	if [ -d "${env_name}" ]; then
		fatal_echo "Virtual environment '$env_name' already exists. Aborting"
		return 1
	fi

	python3 -m venv "$env_name"
	source "./$env_name/bin/activate"
	pip install --upgrade pip
}

#######################################
# Starts up the specified virtual
# environment to perform work
#
# Arguments:
# 	Virtual Environment Name
#######################################
function activate_venv() {
	local env_name="${1:-".venv"}"

	if [ ! -d "$env_name" ]; then
		fatal_echo "Virtual environment '$env_name' not found."
		return 1
	fi

	source "./$env_name/bin/activate"
}

#######################################
# Installs required packages from
# requirements file
#
# Arguments:
# 	Virtual Environment Name
#######################################
function install_dependencies() {
	local env_name="${1:-".venv"}"

	if [ ! -d "$env_name" ]; then
		fatal_echo "Virtual environment '$env_name' not found."
	fi

	source "./$env_name/bin/activate"

	if [ -f "requirements.txt" ]; then
			pip install -r ./requirements.txt
	fi

	if [ -f "setup.py" ]; then
			pip install -e .
	fi
}

#######################################
# Exports the installed packages to a
# requirements file
#
# Arguments:
# 	Virtual Environment Name
#######################################
function export_dependencies() {
	local env_name=${1:-".venv"}

	if [ ! -d "$env_name" ]; then
			fatal_echo "Virtual environment '$env_name' not found"
	fi

	source "./$env_name/bin/activate"
	pip freeze > requirements.txt
	info_echo "Dependencies exported to requirements.txt"
}


#######################################
# Remove specified python virtual
# environment
#
# Arguments:
# 	Virtual Environment Name
#######################################
function remove_venv() {
	local env_name=${1:-".venv"}

	if [ ! -d "$env_name" ]; then
			echo "Virtual environment '$env_name' not found."
			return 1
	fi

	deactivate
	rm -rf "$env_name"
}

## Main script ##

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
	usage
	return 0
fi

case "${1,,}" in
    "create")
        create_venv "$2"
        ;;
    "activate")
        activate_venv "$2"
        ;;
    "install")
        install_dependencies "$2"
        ;;
    "export")
        export_dependencies "$2"
        ;;
    "remove")
        remove_venv "$2"
        ;;
    *)
        echo "Unknown option: $1"
        usage
        exit 1
        ;;
esac
