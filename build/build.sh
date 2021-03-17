#!/bin/sh
#set -e

cd ..

#echo Checking Python code style...
#flake8 ./app
#echo OK

# Test run
/bin/sh ./kraken.sh -v discovery localhost
