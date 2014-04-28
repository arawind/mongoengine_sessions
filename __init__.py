# -*- coding: utf-8 -*-


from .compat import cPickle
from .session import MongoEngineSession, SessionDocument

import datetime

#from .connection import get_default_connection

from .util import (
    get_unique_session_id,
    _generate_session_id,
)

from pyramid.session import (
    signed_serialize,
    signed_deserialize,
)

def includeme(config):
    """
    This function is detected by Pyramid so that you can easily include
    `pyramid_mongoengine_sessions` in your `main` method like so::

        config.include('pyramid_mongoengine_sessions')

    Parameters:

    ``config``
    A Pyramid ``config.Configurator``
    """
    settings = config.registry.settings

    # special rule for converting dotted python paths to callables
    for option in ('client_callable', 'serialize', 'deserialize',
                   'id_generator'):
        key = 'mongoengine.sessions.%s' % option
        if key in settings:
            settings[key] = config.maybe_dotted(settings[key])

    session_factory = session_factory_from_settings(settings)
    config.set_session_factory(session_factory)

def session_factory_from_settings(settings):
    """
    Convenience method to construct a ``MongoEngineSessionFactory`` from Paste config
    settings. Only settings prefixed with "mongoengine.sessions" will be inspected
    and, if needed, coerced to their appropriate types (for example, casting
    the ``timeout`` value as an `int`).

    Parameters:

    ``settings``
    A dict of Pyramid application settings
    """
    from .util import _parse_settings
    options = _parse_settings(settings)
    return MongoEngineSessionFactory(**options)

def MongoEngineSessionFactory(
    secret,
    timeout=1200,
    cookie_name='session',
    cookie_max_age=None,
    cookie_path='/',
    cookie_domain=None,
    cookie_secure=False,
    cookie_httponly=True,
    cookie_on_exception=True,
    id_generator=_generate_session_id,
    ):
    """
    Constructs and returns a session factory that will provide session data
    from a Mongo server. The returned factory can be supplied as the
    ``session_factory`` argument of a :class:`pyramid.config.Configurator`
    constructor, or used as the ``session_factory`` argument of the
    :meth:`pyramid.config.Configurator.set_session_factory` method.

    Parameters:

    ``secret``
    A string which is used to sign the cookie.

    ``timeout``
    A number of seconds of inactivity before a session times out.

    ``cookie_name``
    The name of the cookie used for sessioning. Default: ``session``.

    ``cookie_max_age``
    The maximum age of the cookie used for sessioning (in seconds).
    Default: ``None`` (browser scope).

    ``cookie_path``
    The path used for the session cookie. Default: ``/``.

    ``cookie_domain``
    The domain used for the session cookie. Default: ``None`` (no domain).

    ``cookie_secure``
    The 'secure' flag of the session cookie. Default: ``False``.

    ``cookie_httponly``
    The 'httpOnly' flag of the session cookie. Default: ``False``.

    ``cookie_on_exception``
    If ``True``, set a session cookie even if an exception occurs
    while rendering a view. Default: ``True``.

    ``id_generator``
    A function to create a unique ID to be used as the session key when a
    session is first created.
    Default: private function that uses sha1 with the time and random elements
    to create a 40 character unique ID.

    The following arguments are also passed straight to the ``Strict``
    constructor and allow you to further configure the  client::

      socket_timeout
      connection_pool
      charset
      errors
      unix_socket_path
    """
    def factory(request, new_session_id=get_unique_session_id):

        # sets an add cookie callback on the request when called
        def add_cookie(session_key):
            def set_cookie_callback(request, response):
                """
                The set cookie callback will first check to see if we're in an
                exception. If we're in an exception and ``cookie_on_exception``
                is False, we return immediately before setting the cookie.

                For all other cases the cookie will be set normally.
                """
                exc = getattr(request, 'exception', None)
                # exit early if there's an exception and the user specified
                # to not set cookies on exception
                if exc is not None and not cookie_on_exception:
                    return
                cookieval = signed_serialize(session_key, secret)
                response.set_cookie(
                    cookie_name,
                    value=cookieval,
                    max_age=cookie_max_age,
                    domain=cookie_domain,
                    secure=cookie_secure,
                    httponly=cookie_httponly,
                    )
            request.add_response_callback(set_cookie_callback)
            return

        # sets a delete cookie callback on the request when called
        def delete_cookie():
            def set_cookie_callback(request, response):
                response.delete_cookie(cookie_name)
            request.add_response_callback(set_cookie_callback)
            return

        # attempt to retrieve a session_id from the cookie
        session_id = _session_id_from_cookie(request, cookie_name, secret)

        is_new_session = len(SessionDocument.objects(session_id=session_id)) is 0

        # if we couldn't find the session id in mongo, create a new one
        if is_new_session:
            session_id = new_session_id(timeout, generator=id_generator)
            session = MongoEngineSession(session_id, {}, datetime.datetime.now() + datetime.timedelta(seconds=timeout), timeout, delete_cookie)
            #session.delete_cookie = delete_cookie
        else:
            sessionDoc = SessionDocument.objects.get(session_id=session_id)
            session = MongoEngineSession(sessionDoc.session_id, dict(sessionDoc.managed_dict), sessionDoc.expires, sessionDoc.default_timeout, delete_cookie)
            #session.delete_cookie = delete_cookie()

        # flag new sessions as new and add a cookie with the session id
        if is_new_session:
            add_cookie(session_id)
            session._rs_new = True
            
        session.save()

        return session

    return factory


def _session_id_from_cookie(request, cookie_name, secret):
    """
    Attempts to retrieve and return a session ID from a session cookie in the
    current request. Returns None if the cookie isn't found or the signed secret
    is bad.
    """
    cookieval = request.cookies.get(cookie_name)

    if cookieval is not None:
        try:
            session_id = signed_deserialize(cookieval, secret)
            return session_id
        except ValueError:
            pass

    return None
