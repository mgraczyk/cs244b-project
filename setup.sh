#!/bin/bash
case "$(uname -s)" in

   Darwin)
     echo 'Mac OS X'
     required_python_version="Python 3.6.3"
     ;;

   Linux)
     echo 'Linux'
     yes |sudo yum install python36 gcc64 gcc64-c++ libstdc++64.x86_64
     yes |sudo yum install java-1.8.0-openjdk.x86_64
     required_python_version="Python 3.6.2"
     ;;

   CYGWIN*|MINGW32*|MSYS*)
     echo 'MS Windows'
     ;;


   *)
     echo 'other OS'
     ;;
esac

if [ ! -d zookeeper ]; then
    wget https://archive.apache.org/dist/zookeeper/zookeeper-3.4.11/zookeeper-3.4.11.tar.gz \
	&& tar -xzf zookeeper-3.4.11.tar.gz \
	&& mv zookeeper-3.4.11 zookeeper \
	&& rm zookeeper-3.4.11.tar.gz
fi


python_version="$(python3 -V 2>&1)"

if [[ $python_version != $required_python_version ]]; then
  echo "Incorrect python version: You have $python_version, you need $required_python_version"
else
  test -d .venv/ || virtualenv .venv --python=python3
  source .venv/bin/activate
  python -m pip install -r requirements.txt
  export PYTHONPATH=$(pwd)
  source .env
fi
