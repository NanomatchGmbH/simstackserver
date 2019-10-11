#!/bin/bash

if [ "AA$NANOVER" == "AA" ]
then
    echo "Please export $NANOVER first."
    exit 0
fi

OLD_PWD=$PWD
MY_PATH="`dirname \"$0\"`/../"
echo $MY_PATH
cd $MY_PATH
git archive --prefix=nanomatch/$NANOVER/SimStackServer/ --output=$OLD_PWD/simstackserver.zip master 
cd -
