#!/bin/bash
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
