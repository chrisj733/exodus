## Container Name ##
sas-adxr-exodus

## Developers ##
Chris Johnson <chris.johnson@sas.com>

## Code Location ##
https://gitlab.sas.com/infra-dev/vanguard-control-loops/tree/master/exodus

## Inter-dependent services ##
* python
* Time/Date Functions
* SMTP
* Kubernetes

## Log Location ##
Logs from this service go to stdout.

## Access instructions ##
To run from the command line, type
> python3 exodus.py

## Included health monitors ##
No health monitors are included at this time.

## Functional accounts used ##
This service uses a the sas-adxr-system account as well as a service now functional user capable of using the API

## Upgrade Process ##
Standard k8s container update process.

## Process to scale component ##
Scaling is not supported for this service.

## Process to deploy component ##
* kubectl apply -f https://gitlab.sas.com/infra-dev/vanguard-control-loops/config/kubernetes/exodus.yaml

## List of functions/tasks performed ##
* Walk the namespaces which are labeled as tenant spaces
* Determine the expiration date and compare to system set variables 
* If the namespace has met the criteria for deletion, then set a label indicating the last action fun.
* On the next day's run, the script will look for expiration dates as normal, * but act on any namespaces with the label set by opening a service now ticket
* Once the ticket is created, a deletion routine can run to use the Kubernetes API to delete the namespace.

## Steps to complete tasks manually ##
* Exec into the container
* cd /app
* Run #> python3 exodus.py

# exodus
