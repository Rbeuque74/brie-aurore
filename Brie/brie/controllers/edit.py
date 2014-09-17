# -*- coding: utf-8 -*-

from tg import session
from tg.controllers import redirect
from tg.decorators import expose, validate

from brie.config import ldap_config
from brie.config import groups_enum
from brie.lib.ldap_helper import *
from brie.lib.plugins import *
from brie.lib.aurore_helper import *
from brie.lib.log_helper import BrieLogging
from brie.model.ldap import *
from brie.lib.name_translation_helpers import Translations

from brie.controllers import auth
from brie.controllers.auth import AuthenticatedBaseController, AuthenticatedRestController

from operator import itemgetter

from datetime import datetime
import uuid
import re
import ldap


#root = tg.config['application_root_module'].RootController

""" Controller d'edition de details de membres, chambres""" 
class EditController(AuthenticatedBaseController):
    require_group = groups_enum.admin


    """ Controller fils wifi pour gérer le wifi """
    wifi = None

    """ Controller fils room pour gérer les chambres """
    room = None

    """ Controller fils de gestion des machines """
    machine = None

    member = None

    add = None

    cotisation = None

    def __init__(self, new_show):
        self.show = new_show
        self.wifi = WifiRestController(new_show)
        self.machine = MachineController()
        self.room = RoomController(new_show)
        self.cotisation = CotisationController()
        self.member = MemberModificationController(new_show, self.machine, self.room, self.cotisation)
        self.add = MemberAddController()
        self.member_delete = MemberDeleteController(self.machine, self.room, self.cotisation)

    
    """ Affiche les détails éditables de la chambre """
    @expose("brie.templates.edit.room")
    def room(self, residence, room_id):
        return self.show.room(residence, room_id)
    #end def

#end class

class MemberAddController(AuthenticatedRestController):
	require_group = groups_enum.admin

	""" Fonction de gestion de requete post sur le controller d'ajout """
	@expose()
	def post(self, residence, prenom, nom, mail, phone, go_redirect = True):

		member_uid = Translations.to_uid(prenom, nom)
                if phone == '':
                    phone = ' '
                #end if

		residence_dn = Residences.get_dn_by_name(self.user, residence)
                
                # On modifie silencieusement le nom de la machine si il existe déjà
                def try_name(name, number):
                    actual_name = name
                    if number > 0:
                        actual_name = name + str(number)
                    #end if 
        
                    member = Member.get_by_uid(self.user, residence_dn, actual_name)
                    if member is not None:
                        return try_name(name, number + 1)
                    else:
                        return actual_name
                    #end if
                #endif

                def year_directory_exists(year):
                    search = self.user.ldap_bind.search(ldap_config.username_base_dn + residence_dn,"(ou="+str(year)+")")
                    if len(search) == 0:
                        BrieLogging.get().info("Year "+str(year)+" directory does not exist. Creating.")
                        directory_attrs = {
                                "objectClass" : ["top","organizationalUnit"],
                                "ou" : str(year).encode("utf-8")
                                        }
                        directory_dn = "ou="+str(year)+","+ ldap_config.username_base_dn + residence_dn
                        self.user.ldap_bind.add_entry(directory_dn,directory_attrs)


                member_uid = try_name(member_uid, 0)
        
                member = Member.entry_attr(member_uid, prenom, nom, mail, phone, -1)

                year = CotisationComputes.registration_current_year()

		member_dn = "uid=" + member_uid + ",ou=" + str(year) + "," + ldap_config.username_base_dn + residence_dn
		year_directory_exists(year)
                self.user.ldap_bind.add_entry(member_dn, member)
		

		#preview = member, room
		#index_result["preview"] = preview

                if go_redirect:
                    redirect("/edit/member/" + residence + "/" + member_uid)
                else:
                    return member_uid
                #end if
	#end def
#end class

class MemberModificationController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Controller show qu'on réutilise pour gérer l'affichage """
    show = None
    """ Controller room qu'on réutilise pour gérer les chambres """
    room = None
    """ Controller machine qu'on réutilise pour gérer les machines """
    machine = None
    """ Controller cotisation qu'on réutilise pour gérer les cotis """
    cotisation = None

    def __init__(self, new_show, machine, room, cotisation):
        self.show = new_show
        self.room = room
        self.machine = machine
        self.disable = MemberDisableController()
        self.enable = MemberEnableController()
        self.disconnectall = AllMembersDisableController()
        self.reconnectall = AllMembersEnableController()
    #end def

    """ Affiche les détails éditables du membre et de la chambre """
    @expose("brie.templates.edit.member")
    def get(self, residence, uid):
        residence_dn = Residences.get_dn_by_name(self.user, residence)
        
        self.show.user = self.user
        show_values = self.show.member(residence, uid)
        
        rooms = Room.get_rooms(self.user, residence_dn)
        if rooms is None:
            raise Exception("unable to retrieve rooms")
        #end if
        rooms = sorted(rooms, key=lambda t:t.cn.first())

        areas = Room.get_areas(self.user, residence_dn)

        for room in rooms:
            for area in areas:
                if area.dn in room.dn:
                    room.area = area
                    break
                #end if
            #end for
        #end for
            

        show_values["rooms"] = rooms

        cotisations = show_values["cotisations"]
        month_names = [
            "Janvier",
            "Fevrier",
            "Mars",
            "Avril",
            "Mai",
            "Juin",
            "Juillet",
            "Aout",
            "Septembre",
            "Octobre",
            "Novembre",
            "Decembre"
        ]  # SALE FIXME

        # FIXME => mettre dans aurore helper
        paid_months = []
        already_paid = 0
        for cotisation in cotisations:
            paid_months = (
                paid_months + 
                [int(month) for month in cotisation.get("x-validMonth").all()]
            )

            already_paid += int(cotisation.get("x-amountPaid").first())
        #end for

        now = datetime.now()
        #si le membre est en retard, on doit pas lui faire de cadeau sur sa cotisation si nous sommes dans le mois calendaire suivant de sa due date
        if CotisationComputes.is_cotisation_late(show_values["member_ldap"].dn, self.user, residence_dn) and CotisationComputes.anniversary_from_ldap_items(cotisations).day > now.day:
            start_month = now.month - 1
            if start_month < 0:
                start_month = 12
            #end if
        else :
            start_month = now.month
        #end if
        available_months = CotisationComputes.get_available_months(start_month, 8, paid_months)

        year_price = 0
        month_price = 0

        try:
            year_price = int(Cotisation.prix_annee(self.user, residence_dn).cn.first())
            month_price = int(Cotisation.prix_mois(self.user, residence_dn).cn.first())
        except:
            pass
        #end try

        available_months_prices = []
        index = 1
        
        anniversary = CotisationComputes.generate_new_anniversary_from_ldap_items(cotisations)

        for available_month in available_months:
            if available_month == 8:
                available_months_prices.append(
                    (available_month, "fin de l'année ".decode("utf-8"), CotisationComputes.price_to_pay(year_price, month_price, already_paid, index))
                )
            else: 
                available_months_prices.append(
                    (available_month, str(anniversary.day) + " " + month_names[available_month % 12], CotisationComputes.price_to_pay(year_price, month_price, already_paid, index))
                )
            #end if
            index += 1
        #end for

        show_values["available_months_prices"] = available_months_prices
        
        extras_available = Cotisation.get_all_extras(self.user, residence_dn)
        show_values["extras_available"] = extras_available

        return show_values
    #end def

    @expose()
    def post(self, residence, member_uid, sn, givenName, mail, phone, comment):
        residence_dn = Residences.get_dn_by_name(self.user, residence)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)

        # FIXME
        sn = unicode.encode(sn, 'utf-8')
        givenName = unicode.encode(givenName, 'utf-8')
        comment = unicode.encode(comment, 'utf-8')
    
        member.sn.replace(member.sn.first(), sn)

        member.givenName.replace(member.givenName.first(), givenName)
        member.cn.replace(member.cn.first(), givenName + " " + sn)
        member.mail.replace(member.mail.first(), mail)
        if phone == '':
            phone = ' '
        #end if
        member.mobile.replace(member.mobile.first(), phone)
        if comment != "":
            member.get("x-comment").replace(member.get("x-comment").first(), comment)

        self.user.ldap_bind.save(member)

        redirect("/edit/member/" + residence + "/" + member_uid)
    #end def

""" Controller REST de gestion de la deconnexion. """
class MemberDisableController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        if member is None:
            raise Exception('membre inconnu')
        #end if

        dhcps = Machine.get_dhcps(self.user, member.dn)
    
        machine_membre_tag = "machine_membre" # FIXME move to config

        for dhcp_item in dhcps:
            if dhcp_item.uid.first() == machine_membre_tag:
                dhcp_item.uid.replace(machine_membre_tag, machine_membre_tag + "_disabled")
                self.user.ldap_bind.save(dhcp_item)
            #end if
        #end for

        BrieLogging.get().info("disable member "+member_uid+" by "+self.user.attrs.dn)

        # On redirige sur la page d'édition du membre
        redirect("/edit/member/" + residence + "/" + member_uid)
    #end def

""" Controller REST de gestion de la reconnexion. """
class MemberEnableController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        if member is None:
            raise Exception('membre inconnu')
        #end if

        dhcps = Machine.get_dhcps(self.user, member.dn)
    
        machine_membre_tag = "machine_membre" # FIXME move to config
        machine_membre_disabled = machine_membre_tag + "_disabled" # FIXME move to config

        for dhcp_item in dhcps:
            if dhcp_item.uid.first() == machine_membre_disabled:
                dhcp_item.uid.replace(machine_membre_disabled, machine_membre_tag)
                self.user.ldap_bind.save(dhcp_item)
            #end if
        #end for

        BrieLogging.get().info("enable member "+member_uid+" by "+self.user.attrs.dn)

        # On redirige sur la page d'édition du membre
        redirect("/edit/member/" + residence + "/" + member_uid)
    #end def
#end class

class MemberDeleteController(AuthenticatedRestController):
    require_group = groups_enum.responsablereseau
    machine = None
    room = None
    cotisation = None
    
    def __init__(self, machine, room, cotisation):
        self.machine = machine
        self.room = room
        self.cotisation = cotisation
    #end def

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid):
        residence_dn = Residences.get_dn_by_name(self.user, residence)
        self.machine.delete.user = self.user
        self.room.move.user = self.user
        self.cotisation.delete.user = self.user

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        if member is None:
            raise Exception('membre inconnu')
        #end if

        #on vide la chambre du membre
        self.room.move.post(residence, member_uid, "", False, False)

        #on supprime les machines du membre
        for name, mac, dns, disable in Machine.get_machine_tuples_of_member(self.user, member.dn):
            self.machine.delete.post(residence, member_uid, name, False)
        #end if

        #on supprime sa cotisation histoire de laisser une trace dans les logs...
        year = CotisationComputes.current_year()
        cotisations = Cotisation.cotisations_of_member(self.user, member.dn, year)
        for cotisation in cotisations:
            self.cotisation.delete.post(residence, member_uid, cotisation.get('cn').first(), False)
        #end for

        #on supprime le membre
        self.user.ldap_bind.delete_entry_subtree(member.dn)

        BrieLogging.get().info("suppression du membre "+member_uid+" by "+self.user.attrs.dn)

        # On redirige sur la page de la residence
        redirect("/rooms/index/" + residence)

    #end def

#end class


""" Controller de gestion des machines """
class MachineController(AuthenticatedBaseController):
    require_group = groups_enum.admin

    """ Controller fils d'ajout de machine """
    add  = None
    """ Controller fils de suppression de machine """
    delete = None
    """ Controller fils de desactivation de machine """
    disable  = None
    """ Controller fils d'activation de machine """
    enable = None
    def __init__(self):
        self.add = MachineAddController()
        self.delete = MachineDeleteController()
        self.enable = MachineEnableController()
        self.disable = MachineDisableController()

#end class

""" Controller de gestion des ajouts de machines.
    Il est de type REST, i.e. il gère séparement les requêtes
    get, post, put, delete
"""
class MachineAddController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Fonction de gestion de requete post sur le controller d'ajout """
    @expose()
    @plugin_action("brie.controllers.edit.machine.post")
    def post(self, residence, member_uid, name, mac, go_redirect = True, plugin_action = None):
        residence_dn = Residences.get_dn_by_name(self.user, residence)
        member_base_dn = ldap_config.username_base_dn + residence_dn
        member = Member.get_by_uid(self.user, residence_dn, member_uid)

        mac = mac.strip()
        name = name.strip().replace(" ", "-").replace("_", "-")
        name = Translations.strip_accents(name)

        #Vérification que l'adresse mac soit correcte
        mac_match = re.match('^([0-9A-Fa-f]{2}[:-]?){5}([0-9A-Fa-f]{2})$', mac)
        if mac_match is None:
            #TODO : changer l'exception en une page d'erreur
            raise Exception("mac non valide")
        #endif

        #Remplacement de l'adresse mac non séparée
        mac_match = re.match('^([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})$', mac)
        if mac_match is not None:
            mac = mac_match.group(1) + ":" + mac_match.group(2) + ":" + mac_match.group(3) + ":" + mac_match.group(4) + ":" + mac_match.group(5) + ":" + mac_match.group(6)
        #endif
        
        #Remplacement de l'adresse mac séparée par des tirets
        mac_match = re.match('^([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})$', mac)
        if mac_match is not None:
            mac = mac_match.group(1) + ":" + mac_match.group(2) + ":" + mac_match.group(3) + ":" + mac_match.group(4) + ":" + mac_match.group(5) + ":" + mac_match.group(6)
        #endif

        #Passage au format lowercase
        mac = mac.lower()


        # Vérification que le membre existe
        if member is None:
            #TODO : membre inexistant
            pass
        #endif


        # Vérification que l'adresse mac de la machine n'existe pas déjà
        # Note : on cherche sur toute la résidence (residence_dn)
        machine = Machine.get_dhcp_by_mac(self.user, member_base_dn, mac)
        if machine is not None:
            #TODO : gérer l'exception
            raise Exception("mac address already exist")
        #endif

        # Nettoyage des erreurs communes

        # On modifie silencieusement le nom de la machine si il existe déjà
        def try_name(name, number):
            actual_name = name
            if number > 0:
                actual_name = name + "-" + str(number)
            #end if 

            machine = Machine.get_dns_by_name(self.user, member_base_dn, actual_name)
            if machine is not None:
                return try_name(name, number + 1)
            else:
                return actual_name
            #end if
        #endif

        #On retire les underscore interdits
        name = re.sub('_', '-', name)

        name = try_name(name, 0)
        
        # Génération de l'id de la machine et recherche d'une ip libre
        ip = IpReservation.get_first_free(self.user, residence_dn)

        # Rendre l'ip prise 
        taken_attribute = IpReservation.taken_attr(str(datetime.today()))
        self.user.ldap_bind.add_attr(ip.dn, taken_attribute)

        machine_folder = Machine.folder_attr()
        machine_folder_dn = ldap_config.machine_base_dn + member.dn
        try:
            self.user.ldap_bind.add_entry(machine_folder_dn, machine_folder)
        except ldap.ALREADY_EXISTS:
            pass # OKAY
        #end try

        # Attributs ldap de l'objet machine (regroupant dns et dhcp)
        machine_top = Machine.entry_attr(name)

        # Attributs ldap des objets dhcp et dns, fils de l'objet machine
        machine_dhcp = Machine.dhcp_attr(name, mac)
        machine_dns = Machine.dns_attr(name, ip.cn.first())
        
        # Construction du dn et ajout de l'objet machine 
        # en fils du membre (membre.dn)
        machine_dn = "cn=" + name + "," + ldap_config.machine_base_dn + member.dn
        self.user.ldap_bind.add_entry(machine_dn, machine_top)

        # Construction du dn et ajout de l'objet dhcp 
        # en fils de la machine (machine_dn)
        dhcp_dn = "cn=dhcp," + machine_dn
        self.user.ldap_bind.add_entry(dhcp_dn, machine_dhcp)

        # Construction du dn et ajout de l'objet dns 
        dns_dn = "cn=dns," + machine_dn
        self.user.ldap_bind.add_entry(dns_dn, machine_dns)

        # Ajout de l'entrée dans les logs
        BrieLogging.get().info("ajout machine " + mac + " pour l'utilisateur "+ member.dn + " par l'admin "+ self.user.attrs.dn)
        
        plugin_vars = {
            "machine_dn" : machine_dn,
            "name" : name,
            "ip" : ip,
            "mac" : mac
        }

        plugin_action(self.user, residence, plugin_vars)
        
        if go_redirect:
            redirect("/edit/member/" + residence + "/" + member_uid)
        #end if
    #end def
#end class
        
class CotisationController(AuthenticatedBaseController):
    require_group = groups_enum.admin

    add  = None
    delete = None
    grace = None
    def __init__(self):
        self.add = CotisationAddController()
        self.delete = CotisationDeleteController()
        self.grace = CotisationGraceController()
    #end def


#end class



class CotisationDeleteController(AuthenticatedRestController):
    require_group = groups_enum.admin

    @expose()
    def post(self, residence, member_uid, cotisation_cn, go_redirect = True):
        residence_dn = Residences.get_dn_by_name(self.user, residence)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)

        if member is None:
            raise Exception('membre inconnu')
        #end if

        current_year = CotisationComputes.current_year()

        cotisation = Cotisation.get_payment_by_name(self.user, member.dn, cotisation_cn, current_year)

        if cotisation.has('x-paymentCashed') and cotisation.get('x-paymentCashed').first() == 'TRUE':
            raise Exception('Impossible de supprimer une cotisation encaissée')
        #end if

        self.user.ldap_bind.delete_entry_subtree(cotisation.dn)

        BrieLogging.get().info("suppression cotisation (" + cotisation.get('x-amountPaid').first() + "EUR) pour l'utilisateur "+ member.dn + " par l'admin "+ self.user.attrs.dn)

        if go_redirect:
            redirect("/edit/member/"+residence+"/"+member_uid)
        #end if

    #end def

#end class


class CotisationGraceController(AuthenticatedRestController):
    require_group = groups_enum.responsablereseau

    @expose()
    def post(self, residence, member_uid, cotisation_cn):
        residence_dn = Residences.get_dn_by_name(self.user, residence)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)

        if member is None:
            raise Exception('membre inconnu')
        #end if

        current_year = CotisationComputes.current_year()

        cotisation = Cotisation.get_payment_by_name(self.user, member.dn, cotisation_cn, current_year)

        if cotisation.has('x-paymentCashed') and cotisation.get('x-paymentCashed').first() == 'TRUE':
            raise Exception('Impossible de gracier une cotisation encaissée')
        #end if

        old_montant = cotisation.get("x-amountPaid").first()
        cotisation.get("x-amountPaid").replace(cotisation.get("x-amountPaid").first(), 0)
        self.user.ldap_bind.save(cotisation)

        BrieLogging.get().info("cotisation graciee (" + old_montant + "EUR) pour l'utilisateur "+ member.dn + " par l'admin "+ self.user.attrs.dn)

        redirect("/edit/member/"+residence+"/"+member_uid)

    #end def

#end class


class CotisationAddController(AuthenticatedRestController):
    require_group = groups_enum.admin

    def create_cotisation(self, member, time, current_year, residence, residence_dn, member_uid, next_end):

        now = datetime.now()
        next_month = int(next_end)        

        if not CotisationComputes.is_valid_month(next_month):
            raise Exception("Invalid month") #FIXME
        #end if

        cotisations_existantes = Cotisation.cotisations_of_member(self.user, member.dn, current_year)
        paid_months = []
        already_paid = 0
        for cotisation in cotisations_existantes:
            paid_months = (
                paid_months + 
                [int(month) for month in cotisation.get("x-validMonth").all()]
            )
            already_paid += int(cotisation.get("x-amountPaid").first())
        #end for

        available_months = CotisationComputes.get_available_months(now.month, next_month, paid_months)

        if available_months == []:
            return

        year_price = 0
        month_price = 0

        try:
            year_price = int(Cotisation.prix_annee(self.user, residence_dn).cn.first())
            month_price = int(Cotisation.prix_mois(self.user, residence_dn).cn.first())
        except:
            pass
        #end try
        
        price_to_pay = CotisationComputes.price_to_pay(year_price, month_price, already_paid, len(available_months))

        
        # réactivation des machines du membre # FIXME 
        if now.month in available_months:
            dhcps = Machine.get_dhcps(self.user, member.dn)

            machine_membre_tag = "machine_membre" # FIXME move to config

            for dhcp_item in dhcps:
                dhcp_item.uid.replace(dhcp_item.uid.first(), machine_membre_tag)
                self.user.ldap_bind.save(dhcp_item)
            #end for
        #end if

        user_info = self.user.attrs.cn.first()
        return Cotisation.entry_attr(time, residence, current_year, self.user.attrs.dn, user_info, price_to_pay, available_months)
    #end def

    def create_extra(self, time, current_year, residence, residence_dn, member_uid, extra_name):
        extra_item = Cotisation.get_extra_by_name(self.user, residence_dn, extra_name)

        prix = extra_item.cn.first()

        user_info = self.user.attrs.cn.first()
        return Cotisation.extra_attr(time, residence, current_year, self.user.attrs.dn, user_info, extra_item.uid.first(), prix)
    #end def
    
    @expose()
    def post(self, residence, member_uid, next_end, extra_name, go_redirect = True):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        time = str(datetime.now())
        current_year = CotisationComputes.current_year()
        member = Member.get_by_uid(self.user, residence_dn, member_uid)

        cotisation = None
        extra = None

        if next_end != "":
            cotisation = self.create_cotisation(member, time, current_year, residence, residence_dn, member_uid, next_end)
        
        if extra_name != "":
            extra = self.create_extra(time, current_year, residence, residence_dn, member_uid, extra_name)
        #end if

        if cotisation is None and extra is None:
            if go_redirect:
                redirect("/edit/member/" + residence + "/" + member_uid)
            else:
                return
            #end if
        #end if
            
        folder_dn = ldap_config.cotisation_member_base_dn + member.dn
        year_dn = "cn=" + str(current_year) + "," + folder_dn
   
        try:
            folder = Cotisation.folder_attr()
            self.user.ldap_bind.add_entry(folder_dn, folder)
        except ldap.ALREADY_EXISTS:
            pass # OKAY
        #end try

        try:
            year = Cotisation.year_attr(current_year)
            self.user.ldap_bind.add_entry(year_dn, year)
        except ldap.ALREADY_EXISTS:
            pass # OKAY
        #end try

        
        if cotisation is not None:
            cotisation_dn = "cn=cotisation-" + time + "," + year_dn
            BrieLogging.get().info("cotisation ajoutée pour "+ member.dn +"("+cotisation.get("x-amountPaid").first()+"EUR) by "+ self.user.attrs.dn)
            self.user.ldap_bind.add_entry(cotisation_dn, cotisation)
        #end if        

        if extra is not None:
            extra_dn = "cn=extra-" + time + "," + year_dn
            BrieLogging.get().info("extra ajouté pour "+ member.dn +"("+extra.get("x-amountPaid").first()+"EUR) by "+ self.user.attrs.dn)
            self.user.ldap_bind.add_entry(extra_dn, extra)
        #end if

        if go_redirect:
            redirect("/edit/member/" + residence + "/" + member_uid)
        else:
            return 
        #end if
    #end def

#end class

""" Controller REST de gestion des ajouts de machines. """
class MachineDeleteController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid, machine_id, redirect = True):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        machine = Machine.get_machine_by_id(self.user, member.dn, machine_id)
        dns = Machine.get_dns_by_id(self.user, machine.dn)
        ip = IpReservation.get_ip(self.user, residence_dn, dns.dlzData.first())
        ip_machines = Machine.get_dns_by_ip(self.user, residence_dn, ip.cn.first())

        # Si la machine existe effectivement, on la supprime
        if machine is not None:
            # Ajout de l'entrée dans les logs
            BrieLogging.get().info("suppression machine " + Machine.get_dhcps(self.user, machine.dn)[0].get("dhcpHWAddress").values[0] + " pour l'utilisateur "+ member.dn + " par l'admin "+ self.user.attrs.dn)

            self.user.ldap_bind.delete_entry_subtree(machine.dn)

            if len(ip_machines) == 1:
                taken_attribute = IpReservation.taken_attr(ip.get("x-taken").first())
                self.user.ldap_bind.delete_attr(ip.dn, taken_attribute)
            #end if
        #end if

        # On redirige sur la page d'édition du membre
        if redirect:
            redirect("/edit/member/" + residence + "/" + member_uid)
        #end if
    #end def
#end def


""" Controller REST de gestion de la deconnexion d'une machine. """
class MachineDisableController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid, mac):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        if member is None:
            raise Exception('membre inconnu')
        #end if

        machine = Machine.get_dhcp_by_mac(self.user, member.dn, mac)
        if machine is None:
            raise Exception('machine inconnue')
        #end if

        machine_membre_tag = "machine_membre" # FIXME move to config

        if machine.uid.first() == machine_membre_tag:
            machine.uid.replace(machine_membre_tag, machine_membre_tag + "_disabled")
            self.user.ldap_bind.save(machine)
        #end if

        BrieLogging.get().info("disable member "+member_uid+" machine "+ machine.dhcpStatements.first().split(" ")[1] +" by "+self.user.attrs.dn)

        # On redirige sur la page d'édition du membre
        redirect("/edit/member/" + residence + "/" + member_uid)
    #end def

""" Controller REST de gestion de la reconnexion d'une machine. """
class MachineEnableController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid, mac):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        if member is None:
            raise Exception('membre inconnu')
        #end if

        machine = Machine.get_dhcp_by_mac(self.user, member.dn, mac)
        if machine is None:
            raise Exception('machine inconnue')
        #end if

        machine_membre_tag = "machine_membre" # FIXME move to config
        machine_membre_disabled = machine_membre_tag + "_disabled" # FIXME move to config

        if machine.uid.first() == machine_membre_disabled:
            machine.uid.replace(machine_membre_disabled, machine_membre_tag)
            self.user.ldap_bind.save(machine)
        #end if

        BrieLogging.get().info("enable member "+member_uid+" machine "+ mac +" by "+self.user.attrs.dn)

        # On redirige sur la page d'édition du membre
        redirect("/edit/member/" + residence + "/" + member_uid)
    #end def




class WifiRestController(AuthenticatedRestController):
    require_group = groups_enum.respsalleinfo

    show = None

    def __init__(self, new_show):
        self.show = new_show
    
    @expose("brie.templates.edit.wifi")
    def get(self, uid):
        member = Member.get_by_uid(self.user, self.user.residence_dn, uid)     

        if member is None:
            self.show.error_no_entry()

        return { "member_ldap" : member }
    #end def
        

    @expose("brie.templates.edit.wifi")
    def post(self, uid, password):
    
        member = Member.get_by_uid(self.user, self.user.residence_dn, uid)
    
        if member is None:
            self.show.error_no_entry()
        
        wifi = Wifi.get_by_dn(self.user, member.dn)    
        
        if wifi is None:
            wifi_dn = "cn=wifi," + member.dn
            self.user.ldap_bind.add_entry(wifi_dn, Wifi.entry_attr(password))
        else:
            attr = Wifi.password_attr(password)
            self.user.ldap_bind.replace_attr(wifi.dn, attr)
        #end if

        redirect("/show/member/" + uid)
    #end def
#end class
        
""" Controller de gestion des rooms """
class RoomController(AuthenticatedBaseController):
    require_group = groups_enum.admin

    """ Controller fils d'ajout de machine """
    move  = None
    show = None
    change_member = None
    def __init__(self, show):
        self.move = RoomMoveController()
        self.show = show
        self.change_member = RoomChangeMemberController()


    """ Affiche les détails éditables de la chambre """
    @expose("brie.templates.edit.room")
    def index(self, residence, room_id):
        residence_dn = Residences.get_dn_by_name(self.user, residence)    

        room = Room.get_by_uid(self.user, residence_dn, room_id)

        if room is None:
            raise Exception("no room")

        member = None
        if room.has("x-memberIn"):
            member = Member.get_by_dn(self.user, room.get("x-memberIn").first())

        members = Member.get_all(self.user, residence_dn)
        
        return { 
            "residence" : residence,
            "user" : self.user, 
            "room_ldap" : room, 
            "member_ldap" : member,
            "members" : members
        }        
        #se Exception("tait toi")
    #end def

#end class

""" Controller REST de gestion des ajouts de machines. """
class RoomMoveController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid, room_uid, erase = True, go_redirect = True):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        room = Room.get_by_uid(self.user, residence_dn, room_uid)

        if room is not None:
            member_in = room.get('x-memberIn').first()
            if  member_in is not None:
                if erase:
                    BrieLogging.get().info("ecrasement de chambre - passage en sdf pour "+member_in+" chambre "+room_uid+" by"+self.user.attrs.dn)
                    self.user.ldap_bind.delete_attr(room.dn, { "x-memberIn" : member_in })
                else:
                    raise Exception("chambre de destination non vide")
                #end if
            #end if
            old_room = Room.get_by_member_dn(self.user, residence_dn, member.dn)
            memberIn_attribute = Room.memberIn_attr(str(member.dn))
            if old_room is not None:
                self.user.ldap_bind.delete_attr(old_room.dn, memberIn_attribute)
            #end if
            self.user.ldap_bind.add_attr(room.dn, memberIn_attribute)
            if old_room is not None:
                BrieLogging.get().info("demenagement member "+member_uid+" from "+ old_room.uid.first() +" to "+ room_uid +" by "+self.user.attrs.dn)
            else:
                BrieLogging.get().info("demenagement member "+member_uid+" to "+ room_uid +" by "+self.user.attrs.dn)
            #end if
        else:
            old_room = Room.get_by_member_dn(self.user, residence_dn, member.dn)
            memberIn_attribute = Room.memberIn_attr(str(member.dn))
            if old_room is not None:
                self.user.ldap_bind.delete_attr(old_room.dn, memberIn_attribute)
                BrieLogging.get().info("retrait de chambre pour le member "+member_uid+" from "+ old_room.uid.first() +" by "+self.user.attrs.dn)
            #end if
        #end if
            
            #self.user.ldap_bind.delete_entry_subtree(machine.dn)

            #taken_attribute = IpReservation.taken_attr(ip.get("x-taken").first())
            #self.user.ldap_bind.delete_attr(ip.dn, taken_attribute)
        #end if

        if go_redirect:
            # On redirige sur la page d'édition du membre
            redirect("/edit/member/" + residence + "/" + member_uid)
        #end if
    #end def
#end def


""" Controller REST de gestion des ajouts de machines. """
class RoomChangeMemberController(AuthenticatedRestController):
    require_group = groups_enum.admin

    """ Gestion des requêtes post sur ce controller """
    @expose()
    def post(self, residence, member_uid, room_uid):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        member = Member.get_by_uid(self.user, residence_dn, member_uid)
        room = Room.get_by_uid(self.user, residence_dn, room_uid)

        if member is None and member_uid != "":
            raise Exception("member not found")
        #end if

        if member is not None:
            old_room_member = Room.get_by_member_dn(self.user, residence_dn, member.dn)
    
            # Si la machine existe effectivement, on la supprime
            if old_room_member is not None:
                raise Exception("le nouveau membre possèdait déjà une chambre. conflit")
            #end if
        #end if

        if room is None:
            raise Exception("room inconnue")

        if room.get("x-memberIn") is not None and room.get("x-memberIn").first() is not None:
            memberIn_attribute = Room.memberIn_attr(str(room.get("x-memberIn").first()))
            self.user.ldap_bind.delete_attr(room.dn, memberIn_attribute)
            BrieLogging.get().info("retrait de chambre pour le member "+room.get("x-memberIn").first() +" from "+ room_uid +" by "+self.user.attrs.dn)
        #end if

        if member is not None:
            memberIn_attribute = Room.memberIn_attr(str(member.dn))
            self.user.ldap_bind.add_attr(room.dn, memberIn_attribute)
            BrieLogging.get().info("ajout de chambre pour le member "+ member_uid +" to "+ room_uid +" by "+self.user.attrs.dn)
        #end if    

        # On redirige sur la page d'édition du membre
        redirect("/edit/room/index/" + residence + "/" + room_uid)
    #end def
#end def

""" Controller REST de gestion de la deconnexion globale. """
class AllMembersDisableController(AuthenticatedRestController):
    require_group = groups_enum.responsablereseau

    """ Gestion des requêtes post sur ce controller """
    @expose("brie.templates.index")
    def post(self, residence):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        members = Member.get_all(self.user, residence_dn)
        for member in members:
            if member is None:
                raise Exception('membre inconnu')
            #end if
            groups_of_user = Groupes.get_by_user_dn(self.user, residence_dn, member.dn)
            if "exemptdecoglobale" not in groups_of_user:
                dhcps = Machine.get_dhcps(self.user, member.dn)
            
                machine_membre_tag = "machine_membre" # FIXME move to config

                for dhcp_item in dhcps:
                    if dhcp_item.uid.first() == machine_membre_tag:
                        dhcp_item.uid.replace(machine_membre_tag, machine_membre_tag + "_disabled")
                        self.user.ldap_bind.save(dhcp_item)
                    #end if
                #end for
            #end if
        #end for

        # On redirige sur la page d'accueil
        redirect("/")
    #end def

""" Controller REST de gestion de la reconnexion globale. """
class AllMembersEnableController(AuthenticatedRestController):
    require_group = groups_enum.responsablereseau

    """ Gestion des requêtes post sur ce controller """
    @expose("brie.templates.index")
    def post(self, residence):
        residence_dn = Residences.get_dn_by_name(self.user, residence)

        # Récupération du membre et de la machine
        # Note : on cherche la machine seulement sur le membre (member.dn)
        members = Member.get_all(self.user, residence_dn)
        for member in members:
            if member is None:
                raise Exception('membre inconnu')
            #end if
            # On ne reconnecte que les membres ayant payé leur cotisation.
            if CotisationComputes.is_cotisation_paid(member.dn, self.user, residence_dn):
                dhcps = Machine.get_dhcps(self.user, member.dn)
            
                machine_membre_tag = "machine_membre" # FIXME move to config
                machine_membre_disabled = machine_membre_tag + "_disabled" # FIXME move to config

                for dhcp_item in dhcps:
                    if dhcp_item.uid.first() == machine_membre_disabled:
                        dhcp_item.uid.replace(machine_membre_disabled, machine_membre_tag)
                        self.user.ldap_bind.save(dhcp_item)
                    #end if
                #end for
            #end if
        #end for

        # On redirige sur la page d'accueil
        redirect("/")
    #end def

