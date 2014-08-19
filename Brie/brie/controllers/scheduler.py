from apscheduler.scheduler import Scheduler

from brie.config import ldap_config
from brie.lib.ldap_helper import *
from brie.lib.aurore_helper import *
from brie.model.ldap import *
import sys
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
    members =  Member.get_all_non_admin(admin_user, residence_dn)
    print (CotisationComputes.current_year())
    date_actuelle = datetime.datetime.now()

    for member in members:
        
        machines_tuples = Machine.get_machine_tuples_of_member(admin_user, member.dn)
        if machines_tuples != []:
            
            if not CotisationComputes.is_cotisation_paid(member.dn, admin_user, residence_dn):
                #verification de grace pour septembre : si le membre avait cotise en Aout, on lui accorde un delai de paiement pour Septembre, et on ne le deconnecte pas
                if date_actuelle.month = 9 and is_cotisation_was_paid_last_year(member_dn, admin_user, residence_dn):
                    #le membre etait a jour en aout, on lui autorise un delai de paiement en septembre - pas de deconnexion
                    break
                #end if

                dhcps = Machine.get_dhcps(admin_user, member.dn)
                machine_membre_tag = "machine_membre" # FIXME move to config

                for dhcp_item in dhcps:
                    if dhcp_item.uid.first() == machine_membre_tag:
                        print("[LOG "+datetime.now().strftime("%Y-%m-%d %H:%M")+"] scheduler disable machine " + dhcp_item.get("dhcpHWAddress").values[0] + " pour l'utilisateur "+ member.dn + " -- "+ dhcp_item.dn)
                        dhcp_item.uid.replace(machine_membre_tag, machine_membre_tag + "_disabled")
                        admin_user.ldap_bind.save(dhcp_item)
                    #end if
                #end for
            #end if
            
        #end if
        if CotisationComputes.is_member_to_delete(member, admin_user, residence_dn):
            # supprime les machines mais pas le membre (il pourrait avoir besoin du compte ex : Yohan, le LDAP d'Aurores, etc)
            # alors test a ajouter pour ne supprimer que si membre d'aucun groupe
            # duplication de code avec class MachineDeleteController
            machine_dn = ldap_config.machine_base_dn + member.dn
            machines = admin_user.ldap_bind.search(machine_dn, "(objectClass=organizationalRole)", scope = ldap.SCOPE_ONELEVEL)
            for machine in machines:
                    dns = Machine.get_dns_by_id(admin_user, machine.dn)
                    ip = IpReservation.get_ip(admin_user, residence_dn, dns.dlzData.first())
                    print("[LOG "+datetime.now().strftime("%Y-%m-%d %H:%M")+"] suppression machine " + Machine.get_dhcps(admin_user, machine.dn)[0].get("dhcpHWAddress").values[0] + " pour l'utilisateur "+ member.dn + " par le scheduler")
                    #sys.stdout.flush()
                    admin_user.ldap_bind.delete_entry_subtree(machine.dn)
                    if ip is not None:
                        taken_attribute = ip.get("x-taken").first()
                        if taken_attribute is not None:
                            print ("[LOG "+datetime.now().strftime("%Y-%m-%d %H:%M")+"] deleting taken_attribute")
                            admin_user.ldap_bind.delete_attr(ip.dn, IpReservation.taken_attr(taken_attribute))
                        #end if
                    #end if
            #end for
        #end if

    #end for
            
#end def

@sched.interval_schedule(days=1, start_date="2013-09-30 22:14:37")
#@sched.interval_schedule(minutes=1, start_date="2013-09-30 22:14:37")
def disconnect_members_job():
    user = admin_user()
     
    residences = Residences.get_residences(user)

    for residence in residences:
        print "Disconnect job on : " + residence.uniqueMember.first()
        disconnect_members_from_residence(user, residence.uniqueMember.first())
    #end for

#    user.ldap_bind.disconnect()
#end def

