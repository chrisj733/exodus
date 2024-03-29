# Setup our import list. this is a long list since we have so many dependencies.

from __future__ import print_function
import kubernetes.client
from kubernetes.client.rest import ApiException
from pprint import pprint
from flask import Flask, Blueprint, request, jsonify
from functools import wraps
import requests
import smtplib
import uuid
from string import Template
import calendar
import random
import string
import json
import time
import os
import re
import threading
import base64
import traceback
import logging
import dateutil
import datetime
from distutils.util import strtobool
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from kubernetes import client, config
# from config import config
from snchange import post_sn_change

AUTHOR = 'chris.johnson@sas.com'
ONCALL = 'chris.johnson@sas.com'
NotifyList = AUTHOR + ";" + ONCALL

def string_to_bool(string):
    return bool(strtobool(str(string)))


#######   Important!!!  The next three variables must be set to True for Exodus to run properly.
#######   Setting a default in case we can't pick up environment variables

# Enables Summary emails to oncall and author
ENABLE_ACTION_EMAIL=False
# Enable Auto Deletion of Tenants alternatively you have delete them after the SN is posted or email received
ENABLE_Auto_Deletion=False
# Enable/Disable Service Now Posting
ENABLE_Post_SN=False
manualDeleteOverride=False
AZURE_HOSTED=False

### Now that we have harmless defaults, we'll try to read more specific OS variables.

ENABLE_ACTION_EMAIL=strtobool(str(os.environ['EXODUS_ENABLE_ACTION_EMAIL']))
ENABLE_Auto_Deletion=strtobool(str(os.environ['EXODUS_ENABLE_AUTO_DELETION']))
ENABLE_Post_SN=strtobool(str(os.environ['EXODUS_ENABLE_POST_SN']))
manualDeleteOverride=strtobool(str(os.environ['MANUAL_DELETE_OVERRIDE']))
AZURE_HOSTED=strtobool(str(os.environ['AZURE_HOSTED']))
MAIL_SERVER=str(os.environ['MAIL_HOST'])
MAIL_PORT=str(os.environ['MAIL_PORT'])
SNCI=str(os.environ['SNCI'])

#Define the Minimum Delete threshold, logic should be roughly that we have about one weeks worth of signups.   With 7 to 10 new trials per day, after around 50, we'll determine it's time to delete.

if locals().get('MIN_DELETE'):
   MIN_DELETE=os.environ['MIN_DELETE']
   print(MIN_DELETE)
else :
   MIN_DELETE=50

# Set the Level of Debugging
# 0 - Normal level
# 5 - Informational
#10 - Verbose
#15 - Complete

DEBUGLEVEL=0


### We used to have a generic environment analyticscloud-test, analyticscloud.sas, etc.  The below code block is expired as of v1.3

def determine_env() :
    import os
    osparm = os.environ['DOMAIN']
    return (osparm)



env = determine_env()


################

def read_template(filename):
    with open(filename, 'r', encoding='utf-8') as template_file:
        template_file_content = template_file.read()
    return (template_file_content)


# Configs can be set in Configuration class directly or using helper utility
config.load_incluster_config()

#  BEGIN -  Define Our System Variables as defined by the Sales Team.
#  For our use, we will be examing enviornments as candidates for deletion.  Seperate coding handles the shutdown of applications,
#  UI warn messages, and other messages to contact sales.
#  The software is purchased and an expiration date is determined.  This expiration date is stored in the label for the namespace.
#  A Warning Period is established using a variable called warningdays.   At a value of expiration date minus the warning days,
#  a warning message will appear in the UI for the user, warning them of the expiration date.  The software continues to run
#  without limitation.  (Value in Seconds)

warntimer = 0

# Another variable, grace timer is established and this variable determines how long past the expiration date the environment will
# continue to allow logins to the UI and allow the application tiles to launch as well.  (Value in Seconds)

gracetimer = 0

# Yet another variable, crash timer is established to determine how much time must pass after the software's expiration
# before the environment is rendered unuseable.  If this is the last lapsed product (or only), the Kuberneetes namespace is now eligible
# for deletion.  The user is not allowed to launhch applications after this period.  (Value in Seconds)


# Crashtimer is Unique in that it can flex per namespace

crashtimer = 2592000

# Variable that controls how long after the crash date that the tenant becomes eligible for deletion.

deletetimer = 2592000

# Likely not needed, but we are adding a final propogation delay timer to account for any system time that may be needed to process
# any last minute registrations  (Value in Seconds)

proptimer = 600

# Get the current time so we can work with it.

timenow = datetime.datetime.now().timestamp()

# Trident Controller needs a delay between deletes. Define that time in seconds below
# v1.0.3 - Azure doesn't need as long, so we take it down some

storagedelay = 600

if (AZURE_HOSTED):
    storagedelay = 100


#Debugging Output
if (DEBUGLEVEL>0):
    print ("Time Right now in Epoch : " + timenow)


def expiretest(now, license, istrial):
    # Calculate the number of seconds our license is over or under the time from now.  Positive means a valid licenes
    # Negative means the license is either in a state of grace, or pending expiration
    raw_delta = license - now
    print ("\tTime in License " + str(license) + " minus time now " + str(now) + " = " + str(raw_delta))
    if (raw_delta < 0) :
        print ("\tExpiration Date of the License is in the Past.")
    else :
        print ("\t" + str(raw_delta) + " seconds remain in this trial before any grace timers are applied.")
# Now add in our SAS defined license timers.
    # Crashtimer depends on istrial
    if (istrial==False) :
        delta = raw_delta + gracetimer + crashtimer + deletetimer + proptimer
    else :
        delta = raw_delta + gracetimer + deletetimer + proptimer
    grace_seconds = delta - raw_delta
    print ("\tSeconds remaining after system defined timers are factored in : " + str(delta) + "\n\tSeconds gained from grace timers : " + str(grace_seconds))
    return (delta)

v1 = client.CoreV1Api()

# Sanity check to debug namespace output.
if (DEBUGLEVEL>4):
    print (namespaces)

def exodus_kill_namespace(namespace, ticketexists, delta) :

   killAPI = client.CoreV1Api()

   pretty = 'true' # str | If 'true', then the output is pretty printed. (optional)
   body = kubernetes.client.V1DeleteOptions() # V1DeleteOptions |  (optional)

   print ("Namespace to kill : ", namespace)

# str | When present, indicates that modifications should not be persisted. An invalid or unrecognized dryRun directive
# will result in an error response
# and no further processing of the request. Valid values are: - All: all dry run stages will be processed (optional)

   grace_period_seconds = 5
   orphan_dependents = True
#   The Dry Run Feature is disabled in the current version of the API, it is an alpha feature request
#   dry_run = 'All'
   propagation_policy = 'Background'
   if (delta < 0) and ticketexists :
       print ('Last Resort Sanity Check found a delta of ' + str(delta) + '.  TicketCheck Status: ' + str(ticketexists) + '. Deletion of namespace ' + namespace + ' will now invoke.')
       try:
          api_response = killAPI.delete_namespace(namespace, pretty=pretty, body=body, grace_period_seconds=grace_period_seconds, propagation_policy=propagation_policy)
          pprint(api_response)
          time.sleep(storagedelay)
          return True
       except ApiException as e:
          print("Exception when calling CoreV1Api->delete_namespace: %s\n" % e)
          return False
   else :
       print ('Positive Delta of ' + str(delta) + 'Found in Delete Call, abort!!!!!!!! Namespace : ' + namespace)
       return False


def test_expire (namespaces) :

    totalcount = 0
    no_expirecount = 0
    expiredcount = 0
    trialcount = 0
    actionable_count = 0
    notexpiredcount = 0
    expiredwithticket = 0
    removeexpireflagcount = 0
    todeletecount = 0
    todeletecount_manual = 0
    todelete_noSN_count = 0
    todelete_SN_count = 0
    ticketcreated = 0
    internal_count = 0
    labeled_count = 0
    istrial = False
    sumerr = ""

    # Build an empty string that will run with resulting


    summarytxt = str(print ('Getting Started...\r\n\r\nManual Delete Override: ' +  str(manualDeleteOverride) +  ' Enable Email: ' +  str(ENABLE_ACTION_EMAIL) + ' Enable Auto Deletion : ' + str(ENABLE_Auto_Deletion) + ' Enable SN Post : ' + str(ENABLE_Post_SN) + ' Debug Level : ' + str(DEBUGLEVEL) + '\r\n'))
    

    # Before we begin, build an empty string to track results.

    messagetxt = ''
    oncallsummarytxt = ''
    oncallactionsummarytxt = ''
    manualDeleteString = ''
    
    for ns in namespaces.items:
        # First thing we're going to do is establish where we are in the loops.  We are about to open all namespaces in the cluter with the tenant label.
        # This loop will be testing those.
        # Increment our Count
        totalcount += 1
 
  
        summarytxt += "\r\n\r\nTested Namespace #" + str(totalcount) + " : " + ns.metadata.name + "\r\n" 

        print ("\r\nTesting Namespace #" + str(totalcount) + " : ", ns.metadata.name)

        # By default we ant to do no harm.  So for each namespace we will set/reset the expiration flag and action flag to False.

        is_expired = False
        istrial = False
        action = False
        actionablerun = 0

        # Function call to get the labels.  The Expiration is in the labels, so while we have that open, we're going to go ahead and get everything else
        # that might be useful.

        labels = (ns.metadata.labels)

        # Begin testing the labels, the expiration date if it exists will be stored in expiry.  The conversion to int allows us to do math on them.
        # The license server doesn't install floats as of this iteration so no exact math is neccesary (yet).

        try :
            expiry = int((labels['adx.sas.com/expiration-date']))
        except :
            expiry = 0

        # Test to see if there is a label for Last Exodus action.  If there is, then this run is eligible for action (aka deletion of a namespace)

        try :
            actionable_run = float(labels['adx.sas.com/Last.Exodus.Action.Epoch'])
        except :
            actionable_run = 0

        # Experimental and informational only.  Get the owner label and we'll go ahead and sub out sas.com emails for better formatting.

        try :
            trialowner = str((labels['adx.sas.com/trial-owner']))
        except :
            trialowner = None

        try :
            paidowner = str((labels['adx.sas.com/owner']))
        except :
            paidowner = None

        if (trialowner) :
            istrial = True
            owner = trialowner
            trialcount += 1
        elif (paidowner) :
            istrial = False
            owner = paidowner

        if (".sas.com" in owner) and (expiry !=0 ) and ('sas-adxc-t0000003' not in ns.metadata.name) and ('sas-adxc-t0000002' not in ns.metadata.name) and ('sas-adxc-t0000001' not in ns.metadata.name) :
            owner = owner.replace('.sas.com','@sas.com')
            internal_count +=1

        # Another good sanity check. Let's see if there is a pending Service Now ticket on this namespace, which would indicate Exodus has acted on it before.

        try :
            pendingticket = str((labels['adx.sas.com/Pending.SN.Change']))
        except :
            pendingticket = False



        try :
            nsid = str((labels['adx.sas.com/id']))
        except :
            nsid = "NoID"

        print ("\tNamespace ID : " + str(nsid) + "\r")

        # If we found an actionable run, we're going to set the action to True.  This is necessary because actionable_run is actually an epoch date and not boolean.
        # Can be cleaned up in future runs.

        if (actionable_run > 0):
            action = True
            actionable_count += 1
        else:
            action = False

        # Same for above, except we will set a variable for skipping the creation of a ticket.

        if (pendingticket):
            skipticket = True
            print ("\tPending Ticket : " + str (pendingticket) + " found.")
        else:
            skipticket = False

       # Conduct a test to make sure we got value for expiration date.  If we didn't, we're not going to do anything as this likely is some namespace made outside
       # of normal paths and shouldn't be altered.

        if (expiry != 0):

            # Sanity Check:  Where are we now?   We are testing all namespaces still, with the condition that the expiration was returned.  If we are in this loop
            # then we know that an expiration date existed.

            expiry_hr = time.gmtime(expiry)
            # Build a set of well formated information strings for the debugging and will be later used by Service Now tickets.  These will serve
            # as our runtime results for the delete justification.

            expire_str0 = "\nTenant: " + ns.metadata.name 

            print ("\r\tTimestamp of last exodus flagged execution : " + str(actionable_run))
            
            expire_str1 = "\tId : " + str(nsid) + "\r\tNatural Expiration Date of License in Epoch Format: " + str(expiry) + "\n\tTime Now in Epoch Format: " + str(datetime.datetime.now().timestamp()) + "\t"

            print (expire_str1)

            if (istrial==False) :
                expire_str2 = "\tHuman Readable Expiration Date of License: " + str(time.asctime(expiry_hr)) + "\r\n\tGrace Timer: " + \
                    str(gracetimer) + " Warn Timer : " + str(warntimer) + " Crash Timer : " + str(crashtimer) + " Delete Timer : " + str(deletetimer) + " Propagation Timer : " + str(proptimer) + "\r"
            else :
                expire_str2 = "\tHuman Readable Expiration Date of License: " + str(time.asctime(expiry_hr)) + "\r\n\tGrace Timer: " + \
                    str(gracetimer) + " Warn Timer : " + str(warntimer) + " Crash Timer : -=Not Applicable, Tenant is a Trial=-  Delete Timer : " + str(deletetimer) + " Propagation Timer : " + str(proptimer) + "\r"

            print (expire_str2)

            summarytxt += ("\r" + str(expire_str1) + "\n" + str(expire_str2) + "\n")

            # Use our function to get the number of seconds remaining in the trial by comparing the time now with the time of the license expiration date and our timers
            # A negative number of seconds indicates that the environment is running, 'in the red' and overdue

            ####  The Main Test Function
            ###  Delta is defined as the number of seconds between now and the expiration date of the license.   A negative delta will mean that the tenant has lapsed.

            delta = expiretest(datetime.datetime.now().timestamp(), expiry, istrial)

            ####  End Main Test Function

            if (delta > 0) :
                print ('\tSeconds Remaining in this License for tenant ' + ns.metadata.name + ' : ' + str(delta))
            else :
                print ('\tSeconds Lapsed in this License for tenant ' + ns.metadata.name + ' : ' + str(delta))

            # Just for info, we'll calculate our way back forward by adding the number of seconds remaining or lapsed to our time now to form a human
            # readable version of the expiration time.

            expiretiming = datetime.datetime.now().timestamp() + delta
            expiretiming = time.gmtime(expiretiming)
            expire_str3 = "\tTiming of Expiration : " + str(time.asctime(expiretiming))

            print (expire_str3+ "\r")
            summarytxt += str(expire_str3)  


            # if the delta is below zero, then the tenant has reached their expiration plus graces.  It will be time to act by first setting an
            # Epoch Action timestamp, indicating when we first observed this condition.  An environment needs to be negative for two run cycles to be eligible for deletion.

            if (delta < 0) :

                summarytxt += "\r\tDetermination: This namespace is expired"

                # Sanity Check:  Where are we now?   We are in a loop through a set of namespaces, and we have discovered it has a negative delta.
                # if we are set to receive summary emails, go ahead and build the summary by iteration as well as email this single namespace.

                print ("Negative Delta Detected")
                expiredcount += 1

                # If this is an actionable run, we need to take the approriate action.

                if (action) :

                    
                    # Sanity Check: Where are we now?   We have determined that this particular namespace has both a negative delta, and it's action flag is set.
                    # Therefore:
                    #   a)  It needs a service now ticket
                    #   b)  Once we have a ticket, it's eligible for deletion.
                    #
                    print ("Action Flag is Set")
                    print ("SkipTicket : " + str(skipticket))

                    # If our check for an existing ticket has failed, we will begin our routine to create a ticket.

                    if (not skipticket) :

                        # Sanity Check: Where are we now?  We are looping through a particular namespace which has an action flag, a negative delta, and our loop has found
                        # no existing ticket.  Therefore, we are clear to create a ticket.

                        # Begin building the information strings for the ticket.  We need an integer version of the delta as well as the message texts built earlier.


                        # Our Delta is negative, so we're going to just do a pretty cleanup for user reference.

                        intdelta = -1*int(round(delta,0))

                        print ("Beginning the routine to build a ticket.")

                        summarytxt += "\tThe tenant " + ns.metadata.name + " has expired by " + str(intdelta) + " seconds.  \r\tIt has been identified as expired on at least two consecutive iterations and is now eligible for deletion.  \r\tOwner: " + owner + "\r\n"


                        snmessagetxt = messagetxt + expire_str0 + expire_str1 + expire_str2 + expire_str3

                        oncallactionsummarytxt += "\r\n-------------------------------------------------------------------------------------\r\n" + messagetxt + expire_str1 + expire_str2 + expire_str3

                        if (DEBUGLEVEL > 0) :
                            print (snmessagetxt)

                        # Call our routine to get a pending ticket.
                        if (ENABLE_Post_SN) :

                            # Sanity Check:  Where are we now?  We are in a loop for a namespace with a negative delta, the action flag is set, and we know we need to create a ticket
                            # possibly delete the tenant AND creating tickets is enabled in the system.

                            print ("Target Environment : " + SNCI)

                            # Create the Service Now Ticket

                            pendingticket=post_sn_change(ns.metadata.name, owner, str(snmessagetxt), delta, str(SNCI))
                            print (pendingticket)

                            # Build the post to the namespace label to hold this ticket info.

                            body = {
                                "metadata": {
                                    "labels": {
                                        "adx.sas.com/Pending.SN.Change": pendingticket,}
                                }
                            }


                            # Now, Post the Update to the name space
                            v1.patch_namespace(ns.metadata.name, body)
                            summarytxt += "\r\tAction Taken : Created SN ticket: " + str(pendingticket) + "\r\n"
                            ticketcreated += 1

                        #  Sanity Check: We are in a loop for namespace with a negative delta, the action flag is set, we need to create a ticket and possibly delete, but posting to SN
                        #  is disabled by global variable

                        else :

                            print ("Action Taken : Tenant " + ns.metadata.name + " is actionable for creating a ticket, but Service Now Integration is Disabled." )

                    else :
                        expiredwithticket += 1
                    # Sanity Check:  Where are we now?  We are still in a loop for a namespace with a negative delta.  The action flag is set.  We have handled the cases for creating a ticket
                    # We are now safe to take action, assuming we have a ticket.

                    if (ENABLE_Auto_Deletion) :
                    # Sanity Check:  Where are we now?  We are still in a loop for a namespace with a negative delta.  The action flag is set.  A Service now ticket should exist.
                    # We will verify the ticket, because no action should ever be taken without a ticket.
                        if (pendingticket) :
                            ticketcheck = True
                            print ("ServiceNow Ticket : " + pendingticket + " exists for the tracking of our actions.  Cleared hot for deletion")
                            delresult = exodus_kill_namespace(ns.metadata.name, ticketcheck, delta)
                            summarytxt += "\r\tAction Taken : Exodus deletion of the namespace was triggered.\r\n"

                            if (delresult) :
                                todeletecount += 1
                            else :
                                deleteerr = ns.metadata.name + " returned a deletion error, please check manually for cleanup.\r\n"
                                summarytxt += str(deleteerr)
                                sumerr += str(deleteerr)
                        elif (manualDeleteOverride) :
                            ticketcheck = 'ManualOverride'
                            print ("No Service Now Ticket Exists, but running in Manual Override.  Cleared hot for deletion")
                            delresult = exodus_kill_namespace(ns.metadata.name, ticketcheck, delta)
                            summarytxt += "\r\tAction Taken : Exodus deletion of the namespace was triggered in Manual Override Mode"

                            if (delresult) :
                                todeletecount_manual += 1
                            else :
                                deleteerr = ns.metadata.name + " returned a deletion error (Manual Override), please check manually for cleanup.\r\n"
                                summarytxt += str(deleteerr)
                                sumerr += str(deleteerr)
                                    


                    else :
                        # Sanity Check: Where are we now?
                        if (pendingticket) :
                            print ("Action Taken : Tenant " + ns.metadata.name + " already has a SN ticket created to track its deletion, however auto deletion of tenants is disabled.  See " + str(pendingticket) + " for details.")
                            summarytxt += "\r\tAction Taken : Namespace already has a SN ticket and is prepped for deletion, but deletion of tenants is disabled.  See " + pendingticket + " for details.\r\n"
                            todelete_SN_count += 1
                        if (not pendingticket) :
                            print ("Tenant : " + ns.metadata.name + " does not have a SN ticket created, and auto deletion of tenants is disabled.")
                            print ("Building Manual Delete Log Stream..,\r\n")
                            manualDeleteString += "\r" + ns.metadata.name + " : License Date : (" + str(time.asctime(expiry_hr)) + ") is eligible for deletion on " + str(time.asctime(expiretiming)) + " but SN ticket creation is disabled, and tenant deletion is disabled." 

                            summarytxt += "\r\tAction Taken : Namespacespace does not have a SN ticket, SN creation is disabled, and deletion of tenants is disabled.\r\n"
                            todelete_noSN_count += 1


                # Sanity Check.  Where are we? We are still in the namespace loop and have identified a namespace with a negative delta.  However it was not found to be actionable, meaning that it
                # has no prior existing flag.   So, let's create one, as well as annotate it for inclusion into CMDBs.

                elif (delta < 0) and not (actionable_run) :

                    # Sanity Check: We are still in the loop of all namespaces.  We have identified a negative delta.  This else statement indicates
                    # that the action flag was not set, indicating that no label set was present.  We will now create it.

                    print ("Negative Delta Detected, but no prelminary labeling identified.  Building Labels...")

                    body = {
                       "metadata": {
                           "labels": {
                               "adx.sas.com/Last.Exodus.Action.Epoch": str(timenow)}
                       }
                    }
                    v1.patch_namespace(ns.metadata.name, body)

                    print ("Namespace has been stamped with " + str(body))

                    body = {
                         "metadata": {
                             "annotations": {
                                 "cmdb-watcher/application": str(ns.metadata.name)}
                         }
                    }
                    print ("Patching the Namespace with the cmdb watcher flag so the CI is created")
                    print ("Namespace has been stamped with " + str(body))
                    v1.patch_namespace(ns.metadata.name, body)
                    print ('End of Delta Negative Tests')
                    summarytxt += "\r\tAction Taken : Prepared Namespace for Deletion by tagging CMDB flag and Exodus Action flag.\r\n"
                    labeled_count += 1


            # Sanity Check:  Where are we now?   We are in a loop of all namespaces.  This namespace was found to have an expiration date.
            # By elimination we know now this expiration date is in the future or within a grace period.  Therefore, Delta is greater than
            # zero, but we will continue checks to be safe.

            # Our remaining action is to cover the case where someone has an actionable flag set, but a positive delta.  This would mean that
            # sometime in between runs of Exodus, the license server refreshed it's data.

            if ((actionable_run) and (delta > 0)) :

                # Sanity Check : Still in a loop of all namespaces.  Final check to see if the action flag is set.
                print ("The Namespace delta is " + str(delta) + ". Expiration flag is no longer valid andthe Exodus Action Flag should be removed.")
                print ("Building a null Exodus Action Flag to replace the existing of :" + str(actionable_run))

                body = {
                    "metadata": {
                        "labels": {
                            "adx.sas.com/Last.Exodus.Action.Epoch": None}
                    }
                }
                print ("Patching Namespace with empty Last.Exodus.Action Epoch : " + ns.metadata.name)
                v1.patch_namespace(ns.metadata.name, body)
                removeexpireflagcount += 1
                summarytxt += "\r\tAction Taken : Exodus Action Flag was found, but Expiration did not warrant a deletion.   Cleared the flag.\r\n"


            elif (delta > 0) :
                # Sanity Check:  Still in a loop of all namespaces.  We've found a namespace with a defined expiration and that expiration is in the future or within
                # grace.  We have exhausted all tests.
                notexpiredcount += 1
                print ("\tTenant : " + ns.metadata.name + " has reached the end of its tests." )
                summarytxt += "\r\tAction Taken : Namespace is not expired and thus not a candidate for deletion or tagging.\r\n"


        # Sanity Check : Where are we now?  We are in a loop of all namespaces.  In this one, no expiration date was found inside the labels.  It is likely a system namespace.

        elif (not expiry) :
            no_expirecount += 1
            summarytxt += "\r\tAction Taken : Namespace has no expiration date.\r"
            print ("\r\tThe tenant " + ns.metadata.name + " has no expiration date")

    # Sanity Check:  We have completed a loop of all namespaces passed in.  Along the way, we have built a summary text of our results.  One final check to see if that summary
    # is blank.  If it is, no expired clients with actionable criteria were found.

    external_count = totalcount - internal_count
    print ("\r\n\nPrinting Execution Results...")
    summaryline1 = "  Total Tenants Examined : " + str(totalcount) + "\n    Total Trial Tenants : " + str(trialcount) + "\n    Total Internal Tenants : " + str(internal_count) + "\n    Total External Tenants : " + str(external_count)
    print (summaryline1)
    summaryline2 = "  Total Tenants with no Expiration : " + str(no_expirecount)
    print (summaryline2)
    summaryline3 = ("  Total Non Expired Tenants : " + str(notexpiredcount))
    print (summaryline3)
    summaryline4 = ("  Total Environments Expired : " + str(expiredcount))
    print (summaryline4)
    summaryline5 = ("    Total Environments Which had SN Tickets Created : "  + str(ticketcreated))
    print (summaryline5)
    summaryline6 = ("    Total Environments Which Were Labeled for Deletion on Next Run : " +str(labeled_count))
    print (summaryline6)
    summaryline7 = ("    Total Environments Expired with a Service Now Ticket Pending and Delete Triggered : " +  str(expiredwithticket))
    print (summaryline7)
    summaryline8 = ("    Total Environments Which had their Expired Flag Removed : " + str(removeexpireflagcount))
    print (summaryline8)
    summaryline9 = ("    Total Environments that returned a successful delete : " + str(todeletecount) + "\r\n    Total Environments that returned a successful manual delete : " + str(todeletecount_manual))
    print (summaryline9)
    if sumerr :
        summaryline10 =  ("\r\nErrors: \r\n\r\n" + sumerr)
        print(summaryline10)

    if (not ENABLE_Auto_Deletion) :
        summaryline11 = ("    Total Environments eligible for deletion, SN ticket created, but deletion is disabled : " + str(todelete_SN_count) + "\n    Total Environments eligible for deletion, no SN ticket created - Ticket Creation setting is : " + str(ENABLE_Post_SN) +  ", but deletion is disabled : " + str(todelete_noSN_count) + "\n")
        print (summaryline11)

    oncallsummarytxt += summaryline1 + "\r\n  " + summaryline2 + "\r\n  " +  summaryline3 + "\r\n  " + summaryline4 + "\r\n    " +  summaryline5 + "\r\n    " + summaryline6 + "\r\n    " + summaryline7 + "\r\n    " + summaryline8 + "\r\n    " + summaryline9 + "\r\n    "
    if sumerr :
        oncallsummarytxt += summaryline10 
    if ((not ENABLE_Auto_Deletion) and (expiredcount > MIN_DELETE)) :
        oncallsummarytxt += summaryline11 + "\r\n-----------------------CUT HERE AND PASTE INTO SERVICE NOW FOR MANUAL---------------------------\r\n" + manualDeleteString

    oncallsummarytxt += "\r\n"

    summarytxt += "\r\n" + oncallsummarytxt 

    

    send_email(oncallsummarytxt + oncallactionsummarytxt, NotifyList, 'replies-disabled@sas.com', 'On-Call Exodus Run Summary Results for Expired Clients in ' + SNCI)
    if ((expiredcount > MIN_DELETE) and (not ENABLE_Auto_Deletion)) :
       summarytxt += "\r\n--------------------------Instructions to Enable Manual Deletion-------------------\r\n\r\n1) Access the Environment and edit the deployment sas-adxr-exodus\r\n2) Change the Value for ENABLE_MANUAL_DELETION and ENABLE_Auto_Deletion to be True and save the deployment.\r\n3)  After the run completed, edit the same deployment and reset the value you set to False\r\n-----------------------------------------------------------------------------------"
       send_email(summarytxt, AUTHOR, 'replies-disabled@sas.com', 'Application Owner: -=!DELETE REQUIRED!=- Exodus Run Summary Results for Expired Clients in ' + SNCI)
    else :
       send_email(summarytxt, AUTHOR, 'replies-disabled@sas.com', 'Application Owner: Exodus Run Summary Results for Expired Clients in ' + SNCI)




# Base function to send any message using the smtp libraries.  It will require a message, To address, From address, and a Subject.  The Message will be sent as
# an inline MIMEText.  Most email clients should display this data without the user having to open it as a true attachment.

def send_email(msg, To, From, Subject):
    if (ENABLE_ACTION_EMAIL) :
        email_msg = MIMEMultipart()
        s = smtplib.SMTP(host=MAIL_SERVER, port=MAIL_PORT)
        email_msg['From'] = From
        email_msg['To'] = To
        email_msg['Subject'] = Subject

        email_msg.attach(MIMEText(msg, 'plain'))
        s.send_message(email_msg)
        del (email_msg)


# Function to send an email to a specific user with the results of a SINGLE namespace test against the expiration date and timers.

def email_expire(tenant, expiry, delta):
    message_template = read_template('message.txt')

    message = message_template.replace('TENANT',tenant)

    message = message.replace('EXPIREHRS', str(int(delta // 3600)))
    message = message.replace('EXPIREDATE', time.asctime(expiry))
    message = message.replace('CRASHTIMER', str(crashtimer))
    message = message.replace('WARNTIMER', str(warntimer))
    message = message.replace('DELETETIMER', str(deletetimer))
    message = message.replace('GRACETIMER', str(gracetimer))
    message = message.replace('PROPTIMER', str(proptimer))


    send_email(message, 'chris.johnson@sas.com', 'chris.johnson@sas.com', 'Exodus Run Results for Expired Clients')

    return (message)


## Example Syntax to Walk all Namespaces by Label
namespaces = v1.list_namespace(label_selector='adx.sas.com/tenant')

## Example Syntax to Test A Specific Namespace
#name = "sas-adxc-t30000441"
#target = "metadata.name=" + name
#namespaces = v1.list_namespace(field_selector=target)


## Main Code

print ('Beginning the Run of Exodus.')
test_expire (namespaces)

