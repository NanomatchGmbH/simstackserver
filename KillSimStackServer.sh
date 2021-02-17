#!/bin/bash

# if root kill all SimStackServer processes
if [ $(id -u) -eq 0 ]; then
    for PID in $(pgrep -f "python .*SimStackServer"); do
        echo "Killing SimStackServer process $PID of user $(ps -o user= -p $PID). Please wait 20 seconds for it to shutdown."
        kill $PID
        if  [ $? -ne 0 ]; then 
            sleep 20 && kill -KILL $PID 2> /dev/null &
        fi
    done
    exit 0
fi

# otherwise kill process for current user
PID="$(ps x -u $USER | grep SimStackServer | grep python | grep -v grep | gawk '{print $1}')"
if [ "AA$PID" != "AA" ]
then
    echo "Killing SimStackServer process $PID. Please wait 20 seconds for it to shutdown."
    kill $PID
else
    echo "Did not find running SimStackServer process for user $USER"
    exit 0
fi 
sleep 20 && kill -KILL $PID 2> /dev/null &
