#!/bin/bash
#SBATCH --job-name=TestNMSetup
#SBATCH --mem=4096
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --error=TestNMSetup.stderr
#SBATCH --output=TestNMSetup.stdout
#SBATCH --time=23:59:59

UC_NODES=1; export UC_NODES;
UC_PROCESSORS_PER_NODE=1; export UC_PROCESSORS_PER_NODE;
UC_TOTAL_PROCESSORS=1; export UC_TOTAL_PROCESSORS;
UC_MEMORY_PER_NODE=4096; export UC_MEMORY_PER_NODE;
BASEFOLDER="/home/username/micromamba"

# The following are exports to resolve previous and future
# versions of the SimStackServer conda / python interpreters
###########################################################

simstack_server_mamba_source () {
    MICROMAMBA_BIN="$BASEFOLDER/envs/simstack_server_v6/bin/micromamba"
    if [ -f "$MICROMAMBA_BIN" ]
    then
        export MAMBA_ROOT_PREFIX=$BASEFOLDER
        eval "$($MICROMAMBA_BIN shell hook -s posix)"
        export MAMBA_EXE=micromamba
    else
        if [ -d "$BASEFOLDER/../local_anaconda" ]
        then
            source $BASEFOLDER/../local_anaconda/etc/profile.d/conda.sh
        else
            source $BASEFOLDER/etc/profile.d/conda.sh
        fi
        export MAMBA_EXE=conda
    fi
}

# Following are the legacy exports:
if [ -d "$BASEFOLDER/../local_anaconda" ]
then
    # In this case we are in legacy installation mode:
    export NANOMATCH="$BASEFOLDER/../.."
fi

if [ -f "$BASEFOLDER/nanomatch_environment_config.sh" ]
then
    source "$BASEFOLDER/nanomatch_environment_config.sh"
fi
if [ -f "$BASEFOLDER/simstack_environment_config.sh" ]
then
    source "$BASEFOLDER/simstack_environment_config.sh"
fi
if [ -f "/etc/simstack/simstack_environment_config.sh" ]
then
    source "/etc/simstack/simstack_environment_config.sh"
fi
###########################################################


    cd /home/username/nanoscope/calculations/2025-03-06-15h05m44s-fwfw/exec_directories/2025-03-06-15h05m47s-TestNMSetup
    export HOSTFILE=/home/username/nanoscope/calculations/2025-03-06-15h05m44s-fwfw/exec_directories/2025-03-06-15h05m47s-TestNMSetup/HOSTFILE
    #!/bin/bash
echo "Shell was set to: $SHELL" > diagnostic_output.txt
echo "NANOMATCH variable was set to - $NANOMATCH -" >> diagnostic_output.txt

export NANOVER=V4
source $NANOMATCH/$NANOVER/configs/quantumpatch.config

if [ "AA$HOSTFILE" == "AA" ]
then
    echo "HOSTFILE variable was not set. Please check customer_config.sh for the correct setting of the HOSTFILE variable. Exiting." >> diagnostic_output.txt
    exit 0
else
    echo "HOSTFILE was set to $HOSTFILE" >> diagnostic_output.txt
fi
if [ ! -f "$HOSTFILE" ]
then
    echo "HOSTFILE was set to $HOSTFILE but not found." >> diagnostic_output.txt
    exit 0
else
    echo "HOSTFILE was set to $HOSTFILE. Contents were:" >> diagnostic_output.txt
    echo "-- HOSTFILE BEGIN --" >> diagnostic_output.txt
    cat $HOSTFILE >> diagnostic_output.txt
    echo "-- HOSTFILE END --" >> diagnostic_output.txt
fi


echo "DOING CPU binding benchmark" >> diagnostic_output.txt


$OPENMPI_PATH/bin/mpirun --bind-to none $NMMPIARGS --hostfile $HOSTFILE --mca btl self,vader,tcp --mca btl_tcp_if_exclude lo,virbr0,docker0 python -m mpi4py 2>&1 ./cpu_usage_test.py >> diagnostic_output.txt
echo "CPU binding benchmark done." >> diagnostic_output.txt

echo "QP binary location: " >> diagnostic_output.txt
which QuantumPatchNG.py >> diagnostic_output.txt
