#!/bin/bash

username=$1
MYCOM="${@:2}"
echo "Executing >$MYCOM< as $username"

if [ "AA$1" == "AA" ]
then
    echo "Please specify user as first argument"
    exit 1
fi

if [ "AA$2" == "AA" ]
then
    echo "Please specify command as second argument"
    exit 1
fi

if [ "AA$NANOVER" == "AA"  ]
then
    echo "Please export NANOVER before using this script"
    exit 1
fi
if [ "AA$NANOMATCH" == "AA" ]
then
    echo "Please export NANOMATCH before using this script"
    exit 1
fi

sudo -u $username bash -c "cd ; source $NANOMATCH/$NANOVER/local_anaconda/etc/profile.d/conda.sh; conda activate aiida;\
$MYCOM ;\
"
