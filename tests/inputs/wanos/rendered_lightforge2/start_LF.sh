#!/bin/bash

export NANOVER="V4"
source $NANOMATCH/$NANOVER/configs/lightforge.config

if [ -f lf_output.zip ]; then
    unzip -d ./ lf_output.zip
    sleep 2
    rm lf_output.zip
fi

export OMP_NUM_THREADS=1

# Here we check, whether variables are set and add them to the mpirun exports. This is not required for mpirun with PBS/Torque, but required with everything else.
# We could also specify only the required ones, but we do not know that a priori (i.e. whether Turbomole or Gaussian is to be used.
# To avoid warnings, we therefore check first whether something is set and only then add it to the command.
function varisset {
        if [ -z ${!1+x} ]
        then
                echo "false"
        else
                echo "true"
        fi
}
environmentvariables=("CGPATH"   \
    "DALTONPATH"   \
    "DEPOSITPATH"   \
    "DEPTOOLS"   \
    "DFTBPARAMETERS"   \
    "DFTBPATH"   \
    "DIHEDRAL_PARAMETRIZER_PATH"   \
    "HOSTFILE"   \
    "IBIPATH"   \
    "KMCDEPOSITPATH"   \
    "LD_LIBRARY_PATH"   \
    "LFPATH"   \
    "LOCAL"   \
    "LOCALCONDA"   \
    "MPI_PATH"   \
    "NANOMATCH"   \
    "NANOVER"   \
    "NM_LICENSE_SERVER"   \
    "OMP_NUM_THREADS"   \
    "OPENMMPATH"   \
    "OPENMPIPATH"    \
    "PATH"   \
    "PARNODES" \
    "PYTHONPATH"   \
    "SCRATCH"   \
    "SHREDDERPATH"   \
    "SIMONAPATH"   \
    "SLURM_CPU_BIND"   \
    "THREADFARMPATH"   \
    "TURBODIR"   \
    "UC_MEMORY_PER_NODE"   \
    "UC_NODES"   \
    "UC_PROCESSORS_PER_NODE"   \
    "UC_TOTAL_PROCESSORS"   \
    "UC_TOTAL_PROCESSORS"   \
    "TURBODIR"   \
    "TURBOMOLE_SYSNAME" \
    "XTBPATH"   )


ENVCOMMAND=""
for var in "${environmentvariables[@]}"
do
  if [ "$(varisset ${var})" == "true" ]
  then
        ENVCOMMAND="$ENVCOMMAND -x $var"
  fi
done

python reformat_settings.py settings
if [ -f override_settings.yml ]
then
    python ./merge_settings.py settings override_settings.yml
fi

if [ "$UC_TOTAL_PROCESSORS" -gt 1 ]
then
    $OPENMPI_PATH/bin/mpirun --bind-to none $NMMPIARGS $ENVCOMMAND --hostfile $HOSTFILE --mca btl self,vader,tcp python -m mpi4py $LFPATH/lightforge.py -s settings
else
    lightforge.py -s settings
fi
zip -r results.zip  results

zip_lf_data=`awk 'BEGIN{z="False"} $1=="ziplightforge_data:"&&$2=="true" {z="True"} END{print z}' settings`

cat settings > output_dict.yml

for i in 0;do
    zip -r lightforge_data_subset.zip lightforge_data/material_data/*_"$i".*
    zip -r lightforge_data_subset.zip lightforge_data/runtime_data/*_"$i".*
    zip -r lightforge_data_subset.zip lightforge_data/runtime_data/replay_"$i"
done

if [ $zip_lf_data == "True" ];then
	zip -r lightforge_data.zip lightforge_data
else
	cp lightforge_data_subset.zip lightforge_data.zip
fi

zip lightforge_data_subset.zip *.pdb
zip lightforge_data_subset.zip settings
QP_inputs=`awk '$1=="QP_output.zip:"{print $2}' settings`
for i in `echo $QP_inputs`; do
    zip lightforge_data_subset.zip $i
done


if [ ! -f DriftDiffusion-in.yml ]; then
    touch DriftDiffusion-in.yml
fi
