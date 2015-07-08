# -*- coding: utf-8 -*-
from exception import *
from lib.ldap_helper import LdapEntry

class Residence(object):
    o = None

    def __init__(self, ldap_object):
        if ldap_object is None:
            raise BrieException(u"L'objet LDAP ne peut pas être nul")
        #end if
        if not isinstance(ldap_object, LdapEntry):
            raise BrieException(u"L'objet fourni n'est pas un objet LDAP")
        #end if

        self.o = ldap_object
    #end def

    def getName(self):
        return self.o.cn.first()

    def getDn(self):
        return self.o.uniqueMember.first()

    #@classmethod
    #def fromLdapObject(cls, o):
    #    residence = cls(o.cn.first())
    #
    #    if o is None:
    #        raise BrieException(u"L'objet LDAP ne peut pas être nul")
    #    if not isinstance(o, LdapEntry):
    #        raise BrieException(u"L'objet fourni n'est pas un objet LDAP")

    #    residence.o = ldap_object
    #    return residence
    ##end def

    @staticmethod
    def getResidenceByName(brie, residenceName):
        conn = brie.ldapconn()
        residence = conn.search_first(brie.PREFIX_RESIDENCES_LISTE_DN + brie.AURORE_DN, u"(cn=" + residenceName + u")")
        if residence is None:
            raise BrieException(u"La résidence spécifiée n'existe pas")
        else:
            return Residence(residence)
        #end if
    #end def

    @staticmethod
    def getResidenceByDN(brie, residenceDN):
        residence = brie.ldapconn().search_first(brie.AURORE_RESIDENCES_DN, u"(uniqueMember=" + residenceDN + u")")
        if residence is None:
            raise BrieException(u"La résidence spécifiée n'existe pas")
        else:
            return Residence(residence)
        #end if
    #end def

