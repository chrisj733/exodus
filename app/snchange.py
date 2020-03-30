from snapi import snapi
import json
import jwt
import time
import datetime
import requests
import getpass
import os


def post_sn_change(tenant, owner, messagetxt, dt, environment) : 
    
    desc = 'Remove Expired Tenant Namespace - ' + tenant

    s = snapi(authurl='https://snapi-auth.itapps.sas.com/',wrapperurl='https://snapi.itapps.sas.com',configfile='/tmp/snapi/conf')



    # pass the secret data into the container as env vars
    # https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-environment-variables

    snapi_user = os.environ.get('SNAPI_USERNAME')
    snapi_pw = os.environ.get('SNAPI_PASSWORD')

    token = s.gettoken(username=snapi_user, password=snapi_pw)


    if (environment == 'analyticscloud-dev.sas.com') :
       env = 'analyticscloud-dev-cluster'
    elif (environment == 'analyticscloud-test.sas.com') :
       env = 'analyticscloud-test-cluster'
    elif (environment == 'analyticscloud.sas.com') :
       env = 'analyticscloud-prod-cluster'

    print (env)

    snci = s.getci(ci=env)
    sncid = snci[0]['sys_id']

    print ("SN CI: " + str(sncid))

    try :
        spec_snci = s.getci(ci=tenant)
    except :
        spec_snci = False
    
    print ("Specific CI: ",  str(spec_snci))

    print ("API Token :", token)

    isvalid = s.validtoken()
    print ("API isvalid: ", isvalid)

    if (spec_snci) :
        
        sncid = spec_snci[0]['sys_id']

    if not token or token == "":
        # Token not found, prompt user to provide
        token = raw_input("Provide authentication token for test cases: ").strip()

    ss_date = datetime.datetime.today().strftime('%Y-%m-%d-%H:%M:%S')

    description=env + " : "

    change = s.createchange (
        impact='3',
        description=messagetxt,
        probability='2',
        close_code='Completed Successful',
        close_notes='Deleted Namespace',
        reason='Update CI',
        assigned_to='chrijo',
        requested_by='chrijo',
        watch_list='chrijo',
        planned_start_date=ss_date,
        planned_end_date=ss_date,
        state='Closed',
        service_interruption=False,
        short_summary=desc,
        assignment_group='Analytics Cloud Support.AG',
        third_weekend_maintenance=False,
        change_manager='SAS IT Change Management.AG',
#        impact_description='Expired Tenant Namespace will be removed from the Analytics Cloud Environment',
        type='Standard',
        cmdb_ci=sncid,
        template='Remove AC Expired Tenant'
    )

    context = {
        'ticket_id' : change['number'],
        'sys_id' : change['sys_id']
    }

    print (context)
    return (change['number'])

