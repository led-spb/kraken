#!/bin/sh

cd $(dirname $0)/app

#export PYTHONPATH=$PYTHONPATH:../lib
python ./kraken.py $@
