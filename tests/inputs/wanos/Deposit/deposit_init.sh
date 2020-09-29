#!/bin/bash
export NANOVER="V3"
source $NANOMATCH/$NANOVER/configs/deposit.config

WORKING_DIR=`pwd`
DATA_DIR=$WORKING_DIR

if [ -d $SCRATCH ]
then
    WORKING_DIR=$SCRATCH/`whoami`/`uuidgen`
    mkdir -p $WORKING_DIR
    cp -r $DATA_DIR/* $WORKING_DIR/
    cd $WORKING_DIR
fi

echo "Deposit running on node $(hostname) in directory $WORKING_DIR"
cd $WORKING_DIR

export DO_RESTART="{{ wano["TABS"]["Molecules"]["Restart from existing morphology"] }}"
if [ "$DO_RESTART" == "True" ]
then
    if [ -f restartfile.zip ]
    then
        zip -qT restartfile.zip
        if [ "$?" != "0" ]
        then
            echo "Could not read restartfile. Aborting run."
            exit $?
        fi
        echo "Found Checkpoint, extracting for restart."
        unzip -q -o restartfile.zip
        rm restartfile.zip
    else
        echo "Restart was enabled, but no checkpoint file was found. Not starting simulation."
        exit 5
    fi
fi

Deposit.py {% for element in wano["TABS"]["Molecules"]["Molecules"] %} molecule.{{ loop.index - 1 }}.pdb={{ element["Molecule"] }}  molecule.{{ loop.index - 1 }}.spf={{ element["Forcefield"] }} molecule.{{ loop.index - 1 }}.conc={{ element["Mixing Ratio"] }} {% endfor %}  simparams.Thi={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["Initial Temperature [K]"] }}  simparams.Tlo={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["Final Temperature [K]"] }} simparams.sa.Tacc={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["SA Acc Temp"] }} simparams.sa.cycles={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["Number of SA cycles"] }} simparams.sa.steps={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["Number of Steps"] }} simparams.Nmol={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["Number of Molecules"] }} simparams.moves.dihedralmoves={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["Dihedral Moves"] }}  Box.Lx={{ wano["TABS"]["Simulation Parameters"]["Simulation Box"]["Lx"] }}  Box.Ly={{ wano["TABS"]["Simulation Parameters"]["Simulation Box"]["Ly"] }}  Box.Lz={{ wano["TABS"]["Simulation Parameters"]["Simulation Box"]["Lz"] }}  Box.pbc_cutoff={{ wano["TABS"]["Simulation Parameters"]["Simulation Box"]["PBC"]["Cutoff"] }}  simparams.PBC={{ wano["TABS"]["Simulation Parameters"]["Simulation Box"]["PBC"]["enabled"] }} machineparams.ncpu=${UC_PROCESSORS_PER_NODE} Box.grid_overhang=30 simparams.postrelaxation_steps={{ wano["TABS"]["Simulation Parameters"]["Simulation Parameters"]["Postrelaxation Steps"] }} 


obabel structure.cml -O structure.mol2

if [ "{{ wano["TABS"]["Postprocessing"]["Extend morphology (x,y)"] }}" == "True" ]
then
    $DEPOSITPATH/Tools/add_periodic_copies.py {{ wano["TABS"]["Postprocessing"]["Cut first layer by (A)"] }}
    mv periodic_output/structurePBC.cml .
    rm -f periodic_output/*.cml
    zip -r periodic_output_single_molecules.zip periodic_output
    rm -r periodic_output/
fi


zip restartfile.zip deposited_*.pdb.gz static_parameters.dpcf.gz static_parameters.dpcf_molinfo.dat.gz grid.vdw.gz grid.es.gz neighbourgrid.vdw.gz

rm deposited_*.pdb.gz deposited_*.cml static_parameters.dpcf.gz grid.vdw.gz grid.es.gz neighbourgrid.vdw.gz

if [ -d $SCRATCH ]
then
if [ -d $WORKING_DIR ]
then
    rsync -av $WORKING_DIR/* $DATA_DIR/ --exclude "*.stderr" --exclude "*.stdout" --exclude "stdout" --exclude "stderr"
    cd $DATA_DIR
    rm -r $WORKING_DIR
fi
fi


