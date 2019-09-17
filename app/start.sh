#!/bin/bash

cd /app
while :
do
  python3 /app/exodus.py
  touch /probe/ready.probe
  sleep 86400
done
