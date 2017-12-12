#!/bin/bash
python_version="$(python3 -V 2>&1)"
required_python_version="Python 3.6.3"

if [[ $python_version != $required_python_version ]]; then
  echo "Incorrect python version: You have $python_version, you need $required_python_version"
else
  test -d .venv/ || virtualenv .venv --python=python3
  source .venv/bin/activate
  python -m pip install -r requirements.txt
  export PYTHONPATH=$(pwd)
  source .env
fi
