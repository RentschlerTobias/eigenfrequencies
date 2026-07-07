#!/bin/sh
#echo $SLURM_STEPID > /home/st/st_us-042000/st_st186807/ws/rl_upload/step_id


#export FOAM_SIGFPE=false
#
# variables
#
foamCaseDir=$1
procPerJob=$2


for i in "_n_";do
    cd $foamCaseDir

    # Check Mesh
    checkMesh > log.checkMesh 2>&1
    #if cat "log.checkMesh" | grep -q nonClosedCells || cat "log.checkMesh" | grep -q zeroVolumeCells || cat "log.checkMesh" | grep -q wrongOrientedFaces;then
    #    exit
    #fi

    #rm -rf processor*


    #residuals extraction:
    #sed -i "s/numberOfSubdomains.*;/numberOfSubdomains $procPerJob;/" system/decomposeParDict


    sed -i "s/numberOfSubdomains.*;/numberOfSubdomains $procPerJob;/" system/decomposeParDict
    sed -i "s/method.*;/method scotch;/" system/decomposeParDict
    decomposePar -fileHandler collated > log.decomposePar 2>&1
    


    sed -e 's%^[ \t]*writeInterval.*%writeInterval 100;%g' -i system/controlDict
    sed -e 's%^[ \t]*endTime.*%endTime 100;%g' -i system/controlDict
    sed -e 's%turbulence.*on%turbulence off%g' -i constant/turbulenceProperties
    sed -e 's%cellL%faceL%g' -i system/fvSchemes
    #mpirun $executionnHost $procPerJob simpleFoam -parallel -fileHandler collated > log.simpleFoam 2>&1
    mpiexec --oversubscribe -n $procPerJob -v simpleFoam -parallel -fileHandler collated > log.mpiexec 2>&1

    sed -e 's%^[ \t]*writeInterval.*%writeInterval 500;%g' -i system/controlDict
    sed -e 's%^[ \t]*endTime.*%endTime 500;%g' -i system/controlDict
    sed -e 's%turbulence.*off%turbulence on%g' -i constant/turbulenceProperties
    sed -e 's%faceL%cellL%g' -i system/fvSchemes
    #mpirun $executionnHost $procPerJob simpleFoam -parallel -fileHandler collated > log.simpleFoam.2 2>&1
    mpiexec --oversubscribe -n $procPerJob -v simpleFoam -parallel -fileHandler collated > log.mpiexec 2>&1

    reconstructPar > /dev/null 2>&1

    rm -rf processor*
done


