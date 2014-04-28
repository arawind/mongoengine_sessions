# -*- coding: utf-8 -*-

import os
import datetime


import binascii
from pyramid.compat import text_
from zope.interface import implementer

from mongoengine.document import Document
from mongoengine.fields import StringField, DictField, DateTimeField, IntField

from .compat import cPickle

from .util import (
    persist,
    refresh,
    to_unicode,
    )

from pyramid.interfaces import ISession

class SessionDocument(Document):
    session_id = StringField(primary_key=True)
    expires = DateTimeField()
    managed_dict = DictField()
    default_timeout = IntField()

@implementer(ISession)
class MongoEngineSession(object):
    """
    Implements the Pyramid ISession and IDict interfaces and is returned by
    the ``MongoEngineSessionFactory``.

    Methods that modify the ``dict`` (get, set, update, etc.) are decorated
    with ``@persist`` to update the persisted copy in Mongo and reset the
    timeout.

    Methods that are read-only (items, keys, values, etc.) are decorated
    with ``@refresh`` to reset the session's expire time in Mongo. Same as @persist

    Parameters:

    ``session_id``
    A unique string associated with the session. Used as a prefix for keys
    and hashes associated with the session.

    ``managed_dict``
    The dictionary to be loaded into the current session
    
    ``expires``
    The time after which a background service in python should remove the session entry
    The process has to be scheduled and written by the user, not provided in this package

    ``delete_cookie``
    A function that takes no arguments and returns nothing, but should have the
    side effect of deleting the session cookie from the ``response`` object.
    """
    
    def __init__(
        self,
        session_id,
        managed_dict,
        expires,
        default_timeout,
        delete_cookie
        ):
            
        
        self.session_id = session_id       
        
        self.delete_cookie = delete_cookie
        self.expires = expires
        self.managed_dict = managed_dict
        self.default_timeout = default_timeout

#TODO Remove serialize and deserialize operations

    @property
    def timeout(self):
        return self.managed_dict.get('_rs_timeout', self.default_timeout)
    
    # dict modifying methods decorated with @persist
    @persist
    def __delitem__(self, key):
        del self.managed_dict[key]

    @persist
    def __setitem__(self, key, value):
        self.managed_dict[key] = value

    @persist
    def setdefault(self, key, default=None):
        return self.managed_dict.setdefault(key, default)

    @persist
    def clear(self):
        return self.managed_dict.clear()

    @persist
    def pop(self, key, default=None):
        return self.managed_dict.pop(key, default)

    @persist
    def update(self, other):
        return self.managed_dict.update(other)

    @persist
    def popitem(self):
        return self.managed_dict.popitem()

    # dict read-only methods decorated with @refresh
    @refresh
    def __getitem__(self, key):
        return self.managed_dict[key]

    @refresh
    def __contains__(self, key):
        return key in self.managed_dict

    @refresh
    def keys(self):
        return self.managed_dict.keys()

    @refresh
    def items(self):
        return self.managed_dict.items()

    @refresh
    def get(self, key, default=None):
        return self.managed_dict.get(key, default)

    @refresh
    def __iter__(self):
        return self.managed_dict.__iter__()

    @refresh
    def has_key(self, key):
        return key in self.managed_dict

    @refresh
    def values(self):
        return self.managed_dict.values()

    @refresh
    def itervalues(self):
        try:
            values = self.managed_dict.itervalues()
        except AttributeError: # pragma: no cover
            values = self.managed_dict.values()
        return values

    @refresh
    def iteritems(self):
        try:
            items = self.managed_dict.iteritems()
        except AttributeError: # pragma: no cover
            items = self.managed_dict.items()
        return items

    @refresh
    def iterkeys(self):
        try:
            keys = self.managed_dict.iterkeys()
        except AttributeError: # pragma: no cover
            keys = self.managed_dict.keys()
        return keys

    @persist
    def changed(self):
        """ Persists the working dict immediately with ``@persist``."""
        pass

    # session methods persist or refresh using above dict methods
    @property
    def new(self):
        return getattr(self, '_rs_new', False)

    def invalidate(self):
        """ Delete all keys unique to this session and expire cookie."""
        self.clear()
        self.delete()
        self.delete_cookie()

    def new_csrf_token(self):
        token = text_(binascii.hexlify(os.urandom(20)))
        self['_csrft_'] = token
        return token

    def get_csrf_token(self):
        token = self.get('_csrft_', None)
        if token is None:
            token = self.new_csrf_token()
        else:
            token = to_unicode(token)
        return token

    def flash(self, msg, queue='', allow_duplicate=True):
        storage = self.setdefault('_f_' + queue, [])
        if allow_duplicate or (msg not in storage):
            storage.append(msg)
            self.changed()  # notify mongoengine of change to ``storage`` mutable

    def peek_flash(self, queue=''):
        storage = self.get('_f_' + queue, [])
        return storage

    def pop_flash(self, queue=''):
        storage = self.pop('_f_' + queue, [])
        return storage

    def adjust_timeout_for_session(self, timeout_seconds):
        """
        Permanently adjusts the timeout for this session to ``timeout_seconds``
        for as long as this session is active. Useful in situations where you
        want to change the expire time for a session dynamically.
        """
        self['_rs_timeout'] = timeout_seconds
        
    def save(self):
        sessionDoc = SessionDocument(
            session_id=self.session_id,
            expires=self.expires,
            managed_dict=dict(self.managed_dict),
            default_timeout=self.default_timeout
        )
        
        sessionDoc.save()
