from apscheduler.scheduler import Scheduler

from brie.config import ldap_config
from brie.lib.ldap_helper import *
from brie.lib.aurore_helper import *
from brie.model.ldap import *

import datetime
import brie.config.credentials as credentials


def admin_user():
    bind = Ldap.connect(credentials.scheduler_user, credentials.scheduler_pass)
    dn = "dc=aurore,dc=u-psud,dc=fr"

    user = User(bind,None, dn)
    result = Member.get_by_dn(user, "uid=admin,ou=Administrators,ou=TopologyManagement,o=netscaperoot")
    user.attrs = result

    return user
#end def

sched = Scheduler()


def disconnect_members_from_residence(admin_user, residence_dn):
    current_year = CotisationComputes.current_year()
    now = datetime.datetime.now()
    
    members =  Member.get_all(admin_user, residence_dn)

    for member in members:
        
        machines_tuples = Machine.get_machine_tuples_of_member(admin_user, member.dn)
        if machines_tuples != []:
            cotisations = Cotisation.cotisations_of_member(admin_user, member.dn, current_year)
            months_list, anniversary = CotisationComputes.ldap_items_to_months_list(cotisations)
            
            if not (now.month in months_list 
                    or ((now.month - 1) in months_list and now.day <= (anniversary + 7))):
                dhcps = Machine.get_dhcps(admin_user, member.dn)
    
                machine_membre_tag = "machine_membre" # FIXME move to config

                for dhcp_item in dhcps:
                    if dhcp_item.uid.first() == machine_membre_tag:
                        dhcp_item.uid.replace(machine_membre_tag, machine_membre_tag + "_disabled")
                        admin_user.ldap_bind.save(dhcp_item)
                    #end if
                #end for
            #end if
            
        #end if

    #end for
            
#end def

@sched.interval_schedule(days=1, start_date="2013-09-30 22:14:37")
def disconnect_members_job():
    user = admin_user()
     
    residences = Residences.get_residences(user)


    for residence in residences:
        print "Disconnect job on : " + residence.uniqueMember.first()
        disconnect_members_from_residence(
            user, residence.uniqueMember.first())
    #end for

#    user.ldap_bind.disconnect()
#end def

