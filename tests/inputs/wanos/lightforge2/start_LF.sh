#!/bin/bash

export NANOVER="V3"
source $NANOMATCH/$NANOVER/configs/lightforge.config

if [ -f lf_output.zip ]; then
    unzip -d ./ lf_output.zip
    sleep 2
    rm lf_output.zip
fi

export OMP_NUM_THREADS=1

python reformat_settings.py settings
if [ -f override_settings.yml ]
then
    python ./merge_settings.py settings override_settings.yml
fi

if [ "$UC_TOTAL_PROCESSORS" -gt 1 ]
then
    $MPI_PATH/bin/mpirun -genvall -machinefile $HOSTFILE python -m mpi4py $LFPATH/lightforge.py -s settings
else
    lightforge.py -s settings
fi 
zip -r results.zip  results
zip -r lightforge_data.zip lightforge_data

for i in 0;do
    zip -r lightforge_data_subset.zip lightforge_data/material_data/*_"$i".* 
    zip -r lightforge_data_subset.zip lightforge_data/runtime_data/*_"$i".*
    zip -r lightforge_data_subset.zip lightforge_data/runtime_data/replay_"$i"
done
zip lightforge_data_subset.zip *.pdb
zip lightforge_data_subset.zip settings
QP_inputs=`awk '$1=="QP_output.zip:"{print $2}' settings`
for i in `echo $QP_inputs`; do
    zip lightforge_data_subset.zip $i
done


if [ ! -f DriftDiffusion-in.yml ]; then
    touch DriftDiffusion-in.yml
fi
