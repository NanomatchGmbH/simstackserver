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

sudo -u postgres createuser $username
dbname="aiida_$username"
sudo -u postgres createdb -O $username $dbname

brokerpass=`pwgen 16`
vhostname="aiida_$username"
mquser="aiida_$username"

rabbitmqctl add_user $mquser $brokerpass
rabbitmqctl add_vhost $vhostname
rabbitmqctl set_permissions -p $vhostname $mquser ".*" ".*" ".*"


aiidaexec=`realpath wano-aiida-exec`
sudo -u $username bash -c "source $NANOMATCH/$NANOVER/local_anaconda/etc/profile.d/conda.sh; conda activate aiida;\
reentry scan;\
verdi setup --profile $username --db-engine postgresql_psycopg2 --db-backend django --db-host \"\" --db-port 5432 \
            --db-name $dbname --db-username $username --db-password \"\" --broker-protocol amqp --broker-username $mquser \
            --broker-password $brokerpass --broker-host 127.0.0.1 --broker-port 5672 --broker-virtual-host $vhostname ; \
verdi computer setup -L local -H localhost -D \"\" -T local -S slurm -w /home/ws/{username}/aiida_workspace --prepend-text \"echo AiiDAStartup\" --append-text \"echo AiiDAShutdown\" ; \
verdi computer configure local local; \
reentry scan; \
verdi daemon stop; \
verdi daemon start; \
verdi code setup -Y local -L wano-default-exec -P arithmetic.add  --on-computer  -D wano-default-exec  --remote-abs-path $aiidaexec --prepend-text echo --append-text echo ;\
"
