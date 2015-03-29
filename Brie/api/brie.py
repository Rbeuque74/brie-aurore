# -*- coding: utf-8 -*-

import residence, exception
from lib.ldap_helper import Ldap

class Brie(object):
    ldapconn = None
    username = u""
    password = u""
    residence_name = u""
    residence = None
    admin = None
    __anon_bind = None

    LDAP_URI = "ldaps://localhost"

    PREFIX_MEMBRES_DN = "ou=membres,"
    PREFIX_CHAMBRES_DN = "ou=chambres,"
    PREFIX_GROUPES_DN = "ou=groupes,"
    PREFIX_PARAMETRES_DN = "ou=parametres,"
    PREFIX_MACHINES_MEMBRE_DN = "cn=machines,"
    PREFIX_COTISATIONS_MEMBRE_DN = "cn=cotisations,"
    PREFIX_POOL_IP_DN = "uid=pool_ip," + PREFIX_PARAMETRES_DN
    PREFIX_PLUGINS_DN = "uid=plugins," + PREFIX_PARAMETRES_DN
    PREFIX_COTISATIONS_PARAM_DN = "uid=cotisation," + PREFIX_PARAMETRES_DN
    PREFIX_COTISATIONS_ANNEE_PARAM_DN = "uid=annee," + PREFIX_COTISATIONS_PARAM_DN
    PREFIX_COTISATIONS_MOIS_PARAM_DN = "uid=mois," + PREFIX_COTISATIONS_PARAM_DN
    
    PREFIX_COTISATIONS_EXTRAS_PARAM_DN = "uid=paiements-extras," + PREFIX_PARAMETRES_DN
    PREFIX_RESIDENCES_LISTE_DN = "cn=residences," + PREFIX_PARAMETRES_DN
    AURORE_DN = "dc=aurore,dc=u-psud,dc=fr"


    def __init__(self, username, password, residence, ldap_uri = u""):
        self.username = username
        self.password = password
        self.__anon_bind = Ldap.connect("", "")
        self.residence_name = residence

        if ldap_uri != u"":
            self.LDAP_URI = ldap_uri
        #end if

        self.login()
    #end def

    def ldapconn(self):
        if self.ldapconn is not None:
            return self.ldapconn
        elif self.__anon_bind is not None:
            return self.__anon_bind
        else:
            raise BrieLdapConnectionException(u"La connexion au LDAP n'est pas disponible")
        #end if
    #end def


    def login(self):
        if __anon_bind is None:
            raise BrieLdapConnectionException()

        residence = Residence.getResidenceByName(self, residence_name)

        user_base_dn = PREFIX_MEMBRES_DN + residence.getDn()
        actual_user = self.ldapconn().search_first(user_base_dn, "(uid=" + self.username + ")")

        if actual_user is None:
            raise BrieConnectionException(u"L'utilisateur n'existe pas")

        username_dn = actual_user.getDn()
        self.ldapconn = Ldap.connect(username_dn, password, self.LDAP_URI)

        if self.ldapconn is None:
            raise BrieConnectionException(u"Impossible de se connecter avec la paire identifiant/mot de passe fourni.")

        #TODO : attribuer admin avec le login trouvé
    #end def

    def logout(self):
        if self.ldapconn is not None:
            self.ldapconn.close()
            self.ldapconn = None
        #end if

        self.admin = None
        self.username = u""
        self.password = u""
        self.residence_name = u""
    #end def

