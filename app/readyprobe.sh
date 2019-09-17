#!/bin/bash

if test `find "/probe/ready.probe" -mtime -1`
then
    echo "The ready probe passed"
    exit 0 
else
    echo "The ready probe failed to find a file."
    exit 1
fi

