#!/bin/bash

username=$1

if [ "AA$1" == "AA" ]
then
    echo "Please specify user as first argument"
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

sudo -u $username bash -c "source $NANOMATCH/$NANOVER/local_anaconda/etc/profile.d/conda.sh; conda activate aiida;\
verdi daemon stop ;\
verdi profile delete $username  --skip-db --include-repository  --include-config ;\
"

dbname="aiida_$username"
sudo -u postgres dropdb $dbname

mquser="aiida_$username"
vhostname=$mquser

rabbitmqctl delete_user $mquser
rabbitmqctl delete_vhost $vhostname
