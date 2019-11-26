#!/bin/bash
error() {
  local parent_lineno="$1"
  local message="$2"
  local code="${3:-1}"
  if [[ -n "$message" ]] ; then
    echo "Error on or near line ${parent_lineno}: ${message}; exiting with status ${code}"
  else
    echo "Error on or near line ${parent_lineno}; exiting with status ${code}"
  fi
  exit "${code}"
}
trap 'error ${LINENO}' ERR

if [ "AA$NANOVER" == "AA" ]
then
    echo "Please export $NANOVER first."
    exit 0
fi

OLD_PWD=$PWD
MY_PATH="`dirname \"$0\"`/../"
echo $MY_PATH
cd $MY_PATH
git-archive-all --prefix=nanomatch/$NANOVER/SimStackServer/ $OLD_PWD/simstackserver.zip
cd -
