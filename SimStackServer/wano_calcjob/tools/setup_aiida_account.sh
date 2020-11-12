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
fi
if [ "AA$NANOMATCH" == "AA" ]
then
    echo "Please export NANOMATCH before using this script"
fi

sudo -u postgres createuser $username
dbname="aiida_$username"
sudo -u postgres createdb -O $username $dbname

sudo -u $username bash -c "source $NANOMATCH/$NANOVER/local_anaconda/etc/profile.d/conda.sh; conda activate aiida;\
verdi setup --profile $username --db-engine postgresql_psycopg2 --db-backend django --db-host \"\" --db-port 5432 \
            --db-name $dbname --db-username $username --db-password \"\" --broker-protocol amqp --broker-username guest \
            --broker-password guest --broker-host 127.0.0.1 --broker-port 5672 --broker-virtual-host \"\" ; \
verdi computer setup -L local -H localhost -D \"\" -T local -S slurm -w /home/{username}/aiida_workspace --prepend-text \"echo AiiDAStartup\" --append-text \"echo AiiDAShutdown\" ; \
verdi computer configure local local; \
bash ../register_calcjobs.sh; \
reentry scan; \
verdi daemon stop; \
verdi daemon start; "
 
